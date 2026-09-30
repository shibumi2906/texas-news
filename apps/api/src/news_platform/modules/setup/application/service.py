from __future__ import annotations

import base64
import hashlib
from typing import Any, cast

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.core.config import Settings
from news_platform.modules.editorial.domain.models import EditorialAuditLog
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.setup.domain.models import PortalIntegration
from news_platform.modules.setup.domain.schemas import (
    ConnectionTestResult,
    FeatureSettings,
    InfrastructureStatus,
    IntegrationKind,
    IntegrationView,
    IntegrationWrite,
    PublisherSettings,
    SetupOverview,
)

KINDS: tuple[IntegrationKind, ...] = ("ai_gateway", "email", "web_push")


class SetupNotFoundError(Exception):
    pass


class SetupValidationError(Exception):
    pass


def _fernet(settings: Settings) -> Fernet | None:
    if settings.setup_master_key is None:
        return None
    raw = settings.setup_master_key.get_secret_value().encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def decrypt_secret(settings: Settings, ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    cipher = _fernet(settings)
    if cipher is None:
        return None
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None


class SetupService:
    def __init__(self, session: AsyncSession, settings: Settings, redis: Any) -> None:
        self.session = session
        self.settings = settings
        self.redis = redis

    async def portal(self, slug: str) -> Portal:
        portal = await self.session.scalar(select(Portal).where(Portal.slug == slug))
        if portal is None:
            raise SetupNotFoundError
        return portal

    async def status(self, slug: str) -> tuple[Portal, bool]:
        portal = await self.portal(slug)
        complete = portal.branding.get("setup_completed") is True
        return portal, complete

    async def infrastructure(self) -> InfrastructureStatus:
        database = False
        redis = False
        try:
            database = (await self.session.scalar(text("SELECT 1"))) == 1
        except Exception:
            database = False
        try:
            redis = bool(await self.redis.ping())
        except Exception:
            redis = False
        return InfrastructureStatus(
            database=database,
            redis=redis,
            secrets_encryption=_fernet(self.settings) is not None,
        )

    async def overview(self, slug: str) -> SetupOverview:
        portal, completed = await self.status(slug)
        records = {
            item.kind: item
            for item in (
                await self.session.scalars(
                    select(PortalIntegration).where(PortalIntegration.portal_id == portal.id)
                )
            ).all()
        }
        publisher: PublisherSettings | None = None
        data = portal.branding.get("publisher")
        canonical = portal.seo_settings.get("canonical_base_url")
        if isinstance(data, dict) and canonical:
            try:
                publisher = PublisherSettings(canonical_base_url=canonical, **data)
            except ValueError:
                publisher = None
        integrations = [self._view(kind, records.get(kind)) for kind in KINDS]
        return SetupOverview(
            portal_slug=portal.slug,
            completed=completed,
            infrastructure=await self.infrastructure(),
            publisher=publisher,
            features=FeatureSettings(
                **{
                    key: portal.feature_flags.get(key, default)
                    for key, default in FeatureSettings().model_dump().items()
                }
            ),
            integrations=integrations,
        )

    async def save_features(self, slug: str, payload: FeatureSettings, actor: str) -> SetupOverview:
        portal = await self.portal(slug)
        before = {
            key: portal.feature_flags.get(key)
            for key in payload.model_fields_set or payload.model_dump().keys()
        }
        portal.feature_flags = {**portal.feature_flags, **payload.model_dump()}
        portal.advertising_settings = {
            **portal.advertising_settings,
            "enabled": payload.advertising,
        }
        self._audit(
            actor,
            "setup_features_update",
            portal,
            before,
            payload.model_dump(),
        )
        await self.session.flush()
        return await self.overview(slug)

    async def save_publisher(
        self, slug: str, payload: PublisherSettings, actor: str
    ) -> SetupOverview:
        portal = await self.portal(slug)
        before = {
            "publisher": portal.branding.get("publisher"),
            "canonical_base_url": portal.seo_settings.get("canonical_base_url"),
        }
        publisher = payload.model_dump(mode="json", exclude={"canonical_base_url", "logo_url"})
        if payload.logo_url is not None:
            publisher["logo_url"] = str(payload.logo_url)
            portal.logo = str(payload.logo_url)
        portal.branding = {**portal.branding, "publisher": publisher}
        portal.name = payload.publisher_name
        portal.seo_settings = {
            **portal.seo_settings,
            "canonical_base_url": str(payload.canonical_base_url).rstrip("/"),
        }
        await self.session.flush()
        self._audit(
            actor,
            "setup_publisher_update",
            portal,
            before,
            {
                "publisher": publisher,
                "canonical_base_url": portal.seo_settings["canonical_base_url"],
            },
        )
        return await self.overview(slug)

    async def save_integration(
        self, slug: str, kind: IntegrationKind, payload: IntegrationWrite, actor: str
    ) -> SetupOverview:
        portal = await self.portal(slug)
        if payload.enabled and payload.endpoint is None:
            raise SetupValidationError("An endpoint is required when the integration is enabled.")
        record = await self.session.scalar(
            select(PortalIntegration).where(
                PortalIntegration.portal_id == portal.id,
                PortalIntegration.kind == kind,
            )
        )
        before = self._safe_record(record)
        if record is None:
            record = PortalIntegration(portal_id=portal.id, kind=kind)
            self.session.add(record)
        if payload.secret:
            cipher = _fernet(self.settings)
            if cipher is None:
                raise SetupValidationError("Secret encryption is not configured.")
            record.secret_ciphertext = cipher.encrypt(payload.secret.encode()).decode()
            record.secret_hint = f"••••{payload.secret[-4:]}"
        if payload.enabled and not (payload.secret or record.secret_ciphertext):
            raise SetupValidationError("A credential is required when the integration is enabled.")
        record.enabled = payload.enabled
        record.configuration = {
            "endpoint": str(payload.endpoint).rstrip("/") if payload.endpoint else None,
            "provider_name": payload.provider_name,
        }
        record.verified = False
        record.last_error = None
        await self.session.flush()
        self._audit(
            actor,
            "setup_integration_update",
            portal,
            before,
            self._safe_record(record),
            reason=kind,
        )
        return await self.overview(slug)

    async def test_integration(
        self, slug: str, kind: IntegrationKind, actor: str
    ) -> ConnectionTestResult:
        portal = await self.portal(slug)
        record = await self.session.scalar(
            select(PortalIntegration).where(
                PortalIntegration.portal_id == portal.id,
                PortalIntegration.kind == kind,
            )
        )
        if record is None or not record.enabled:
            raise SetupValidationError("Save and enable the integration before testing it.")
        endpoint = record.configuration.get("endpoint")
        secret = decrypt_secret(self.settings, record.secret_ciphertext)
        if not isinstance(endpoint, str) or not secret:
            raise SetupValidationError("The integration configuration is incomplete.")
        url = f"{endpoint.rstrip('/')}/models" if kind == "ai_gateway" else endpoint
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                if kind == "ai_gateway":
                    response = await client.get(url, headers={"Authorization": f"Bearer {secret}"})
                else:
                    response = await client.head(url, headers={"Authorization": f"Bearer {secret}"})
            ok = response.status_code < 400 or (
                kind != "ai_gateway" and response.status_code in {404, 405}
            )
            code = "connected" if ok else f"http_{response.status_code}"
        except (httpx.TimeoutException, httpx.RequestError):
            ok = False
            code = "unreachable"
        record.verified = ok
        record.last_error = None if ok else code
        self._audit(
            actor,
            "setup_integration_test",
            portal,
            {},
            {"kind": kind, "ok": ok, "code": code},
        )
        return ConnectionTestResult(ok=ok, code=code)

    async def complete(self, slug: str, actor: str) -> SetupOverview:
        portal = await self.portal(slug)
        overview = await self.overview(slug)
        if not overview.infrastructure.database or not overview.infrastructure.redis:
            raise SetupValidationError("Database and Redis must be healthy.")
        if overview.publisher is None:
            raise SetupValidationError("Publisher settings must be completed.")
        unverified = [
            item.kind for item in overview.integrations if item.enabled and not item.verified
        ]
        if unverified:
            raise SetupValidationError("Enabled integrations must pass their connection test.")
        before = {"setup_completed": portal.branding.get("setup_completed")}
        portal.branding = {**portal.branding, "setup_completed": True}
        self._audit(
            actor,
            "setup_complete",
            portal,
            before,
            {"setup_completed": True},
        )
        await self.session.flush()
        return await self.overview(slug)

    @staticmethod
    def _view(kind: IntegrationKind, record: PortalIntegration | None) -> IntegrationView:
        config = record.configuration if record else {}
        return IntegrationView(
            kind=kind,
            enabled=bool(record and record.enabled),
            endpoint=cast(str | None, config.get("endpoint")),
            provider_name=cast(str | None, config.get("provider_name")),
            secret_configured=bool(record and record.secret_ciphertext),
            secret_hint=record.secret_hint if record else None,
            verified=bool(record and record.verified),
            last_error=record.last_error if record else None,
        )

    @staticmethod
    def _safe_record(record: PortalIntegration | None) -> dict[str, Any]:
        if record is None:
            return {}
        return {
            "kind": record.kind,
            "enabled": record.enabled,
            "configuration": record.configuration,
            "secret_configured": bool(record.secret_ciphertext),
            "verified": record.verified,
        }

    def _audit(
        self,
        actor: str,
        action: str,
        portal: Portal,
        before: dict[str, Any],
        after: dict[str, Any],
        reason: str | None = None,
    ) -> None:
        self.session.add(
            EditorialAuditLog(
                actor=actor,
                action=action,
                entity_type="portal_setup",
                entity_id=portal.id,
                before=before,
                after=after,
                reason=reason,
            )
        )
