from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.core.config import Settings
from news_platform.modules.setup.application.service import decrypt_secret
from news_platform.modules.setup.domain.models import PortalIntegration


class NotificationGatewayError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DeliveryRequest:
    delivery_id: UUID
    portal_id: UUID
    destination: str
    configuration: dict[str, Any]
    title: str
    body: str
    url: str


class NotificationSender(Protocol):
    async def send(self, channel: str, request: DeliveryRequest) -> None: ...


class NotificationGateway:
    def __init__(self, settings: Settings, session: AsyncSession | None = None) -> None:
        self.settings = settings
        self.session = session

    async def send(self, channel: str, request: DeliveryRequest) -> None:
        payload: dict[str, Any]
        dynamic_url, dynamic_key = await self._dynamic_configuration(channel, request.portal_id)
        if channel == "email":
            url = dynamic_url or self.settings.notification_email_gateway_url
            key_value = dynamic_key
            key = self.settings.notification_email_gateway_key
            payload = {
                "to": request.destination,
                "title": request.title,
                "body": request.body,
                "url": request.url,
            }
        elif channel == "web_push":
            url = dynamic_url or self.settings.notification_web_push_gateway_url
            key_value = dynamic_key
            key = self.settings.notification_web_push_gateway_key
            payload = {
                "subscription": {
                    "endpoint": request.destination,
                    "p256dh": request.configuration["p256dh"],
                    "auth": request.configuration["auth"],
                },
                "notification": {
                    "title": request.title,
                    "body": request.body,
                    "url": request.url,
                },
            }
        else:
            raise NotificationGatewayError("unsupported_channel")
        if key_value is None and key is not None:
            key_value = key.get_secret_value()
        if not url or key_value is None:
            raise NotificationGatewayError("gateway_not_configured")
        headers = {
            "Authorization": f"Bearer {key_value}",
            "Idempotency-Key": str(request.delivery_id),
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.notification_gateway_timeout_seconds
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise NotificationGatewayError("gateway_timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise NotificationGatewayError(f"gateway_http_{exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise NotificationGatewayError("gateway_unavailable") from exc

    async def _dynamic_configuration(
        self, channel: str, portal_id: UUID
    ) -> tuple[str | None, str | None]:
        if self.session is None:
            return None, None
        kind = "email" if channel == "email" else "web_push"
        record = await self.session.scalar(
            select(PortalIntegration).where(
                PortalIntegration.portal_id == portal_id,
                PortalIntegration.kind == kind,
                PortalIntegration.enabled.is_(True),
                PortalIntegration.verified.is_(True),
            )
        )
        if record is None:
            return None, None
        endpoint = record.configuration.get("endpoint")
        return (
            endpoint if isinstance(endpoint, str) else None,
            decrypt_secret(self.settings, record.secret_ciphertext),
        )
