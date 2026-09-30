from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.core.config import Settings
from news_platform.modules.ai.infrastructure.providers import (
    GatewayAdapter,
    LocalSummaryAdapter,
    ProviderRegistry,
)
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.setup.application.service import decrypt_secret
from news_platform.modules.setup.domain.models import PortalIntegration


async def provider_registry_for_portal(
    session: AsyncSession,
    portal_slug: str,
    settings: Settings,
    fallback: ProviderRegistry,
) -> ProviderRegistry:
    record = await session.scalar(
        select(PortalIntegration)
        .join(Portal, Portal.id == PortalIntegration.portal_id)
        .where(
            Portal.slug == portal_slug,
            PortalIntegration.kind == "ai_gateway",
            PortalIntegration.enabled.is_(True),
            PortalIntegration.verified.is_(True),
        )
    )
    if record is None:
        return fallback
    endpoint = record.configuration.get("endpoint")
    secret = decrypt_secret(settings, record.secret_ciphertext)
    if not isinstance(endpoint, str) or not secret:
        return fallback
    name = record.configuration.get("provider_name")
    return ProviderRegistry(
        [
            LocalSummaryAdapter(settings.ai_local_stub_response_mode),
            GatewayAdapter(endpoint, secret, str(name or "external-gateway")),
        ]
    )
