from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx

from news_platform.core.config import Settings


class NotificationGatewayError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DeliveryRequest:
    delivery_id: UUID
    destination: str
    configuration: dict[str, Any]
    title: str
    body: str
    url: str


class NotificationSender(Protocol):
    async def send(self, channel: str, request: DeliveryRequest) -> None: ...


class NotificationGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, channel: str, request: DeliveryRequest) -> None:
        payload: dict[str, Any]
        if channel == "email":
            url = self.settings.notification_email_gateway_url
            key = self.settings.notification_email_gateway_key
            payload = {
                "to": request.destination,
                "title": request.title,
                "body": request.body,
                "url": request.url,
            }
        elif channel == "web_push":
            url = self.settings.notification_web_push_gateway_url
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
        if not url or key is None:
            raise NotificationGatewayError("gateway_not_configured")
        headers = {
            "Authorization": f"Bearer {key.get_secret_value()}",
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
