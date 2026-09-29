from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_phase_5_feeds import NOW, add_story, database, seed_domain  # noqa: F401

from news_platform.modules.advertising.api.router import admin_router as advertising_admin_router
from news_platform.modules.advertising.api.router import router as advertising_router
from news_platform.modules.advertising.domain.models import AdClick, AdImpression
from news_platform.modules.editorial.domain.models import EditorialAuditLog
from news_platform.modules.notifications.api.router import (
    admin_router as notifications_admin_router,
)
from news_platform.modules.notifications.api.router import router as notifications_router
from news_platform.modules.notifications.application.service import NotificationDeliveryService
from news_platform.modules.notifications.domain.models import (
    NotificationDelivery,
    NotificationSubscription,
)
from news_platform.modules.notifications.infrastructure.gateways import NotificationGatewayError
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.users.api.router import router as users_router
from news_platform.modules.users.domain.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def runtime(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], dict[str, Any]]]:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        portal = await session.scalar(select(Portal).where(Portal.slug == "texas"))
        assert portal is not None
        portal.feature_flags = {"advertising": True, "notifications": True}
        story = await add_story(session, domain, 1501, published_at=NOW - timedelta(hours=1))
        domain.update(portal=portal, story=story)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.db_session_factory = factory
    app.state.redis = SimpleNamespace()
    app.state.settings = SimpleNamespace(
        environment="test",
        auth_session_hours=168,
        auth_login_rate_limit=0,
        auth_rate_limit_window_seconds=60,
        auth_allowed_origins="http://test",
    )
    app.include_router(users_router)
    app.include_router(advertising_router)
    app.include_router(advertising_admin_router)
    app.include_router(notifications_router)
    app.include_router(notifications_admin_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory, domain


async def register(client: httpx.AsyncClient, email: str) -> str:
    result = await client.post(
        "/api/v1/portals/texas/auth/register",
        json={
            "email": email,
            "password": "correct horse battery",
            "display_name": "Phase Fifteen",
        },
    )
    assert result.status_code == 201, result.text
    return str(result.json()["csrf_token"])


def csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token, "Origin": "http://test"}


async def make_admin(factory: async_sessionmaker[AsyncSession], email: str) -> None:
    async with factory() as session, session.begin():
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        user.role = "admin"


async def test_ad_admin_rbac_portal_isolation_determinism_and_idempotent_tracking(
    runtime: Any,
) -> None:
    client, factory, domain = runtime
    admin_root = "/api/v1/portals/texas/admin/advertising"
    assert (await client.get(admin_root)).status_code == 401
    token = await register(client, "ads-admin@example.com")
    assert (await client.get(admin_root)).status_code == 403
    await make_admin(factory, "ads-admin@example.com")
    missing_csrf = await client.post(
        f"{admin_root}/placements",
        json={
            "code": "blocked-placement",
            "name": "Blocked placement",
            "allowed_content_types": [],
            "active": True,
        },
    )
    assert missing_csrf.status_code == 403

    placement = await client.post(
        f"{admin_root}/placements",
        headers=csrf(token),
        json={
            "code": "story-inline",
            "name": "Story inline",
            "allowed_content_types": ["article"],
            "active": True,
        },
    )
    assert placement.status_code == 201, placement.text
    campaign = await client.post(
        f"{admin_root}/campaigns",
        headers=csrf(token),
        json={
            "name": "Austin launch",
            "status": "active",
            "priority": 100,
            "starts_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            "ends_at": None,
            "targeting": {
                "placement_codes": ["story-inline"],
                "geography_ids": [str(domain["austin"].id)],
                "languages": ["en"],
                "category_ids": [str(domain["sports"].id)],
                "content_types": ["article"],
            },
            "creatives": [
                {
                    "name": "Launch creative",
                    "format": "image",
                    "asset_url": "https://cdn.example/ad.jpg",
                    "click_url": "https://advertiser.example/launch",
                    "alt_text": "Austin launch",
                    "active": True,
                }
            ],
        },
    )
    assert campaign.status_code == 201, campaign.text
    params = {
        "identity_key": "stable-reader-123",
        "language": "en",
        "content_id": str(domain["story"].id),
        "geography_id": str(domain["austin"].id),
        "category_id": str(domain["sports"].id),
    }
    path = "/api/v1/portals/texas/ads/placements/story-inline"
    first = await client.get(path, params=params)
    second = await client.get(path, params=params)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    derived = await client.get(
        path,
        params={
            "identity_key": "stable-reader-123",
            "language": "en",
            "content_id": str(domain["story"].id),
        },
    )
    assert derived.json() == first.json()

    impression_id = uuid4()
    impression = {
        "id": str(impression_id),
        "placement_id": first.json()["placement_id"],
        "campaign_id": first.json()["campaign_id"],
        "creative_id": first.json()["creative_id"],
        "content_id": str(domain["story"].id),
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    impression_results = await asyncio.gather(
        client.post("/api/v1/portals/texas/ads/impressions", json=impression),
        client.post("/api/v1/portals/texas/ads/impressions", json=impression),
    )
    conflict = await client.post(
        "/api/v1/portals/texas/ads/impressions",
        json={**impression, "creative_id": str(uuid4())},
    )
    assert sorted(result.json()["status"] for result in impression_results) == [
        "accepted",
        "duplicate",
    ]
    assert conflict.status_code == 409
    click_id = uuid4()
    click = {
        "id": str(click_id),
        "impression_id": str(impression_id),
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    click_results = await asyncio.gather(
        client.post("/api/v1/portals/texas/ads/clicks", json=click),
        client.post("/api/v1/portals/texas/ads/clicks", json=click),
    )
    assert sorted(result.json()["status"] for result in click_results) == [
        "accepted",
        "duplicate",
    ]
    assert (
        await client.get(
            "/api/v1/portals/oklahoma/ads/placements/story-inline",
            params={"identity_key": "stable-reader-123"},
        )
    ).status_code == 404
    assert (await client.get("/api/v1/portals/oklahoma/admin/advertising")).status_code == 401

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AdImpression)) == 1
        assert await session.scalar(select(func.count()).select_from(AdClick)) == 1
        actions = set(
            (
                await session.scalars(
                    select(EditorialAuditLog.action).where(
                        EditorialAuditLog.entity_type == "advertising"
                    )
                )
            ).all()
        )
        assert actions == {"ad_placement_create", "ad_campaign_create"}


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def send(self, channel: str, request: Any) -> None:
        self.calls.append((channel, request))


class FlakyGateway:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.delivery_ids: list[Any] = []

    async def send(self, _channel: str, request: Any) -> None:
        self.delivery_ids.append(request.delivery_id)
        if len(self.delivery_ids) <= self.failures:
            raise NotificationGatewayError("gateway_timeout")


async def test_notification_ownership_privacy_admin_audit_and_exactly_once_claim(
    runtime: Any,
) -> None:
    client, factory, _domain = runtime
    token = await register(client, "subscriber@example.com")
    subscription = await client.put(
        "/api/v1/portals/texas/notifications/subscriptions",
        headers=csrf(token),
        json={
            "channel": "web_push",
            "endpoint": "https://push.example/subscriber-token",
            "p256dh": "0123456789abcdef",
            "auth": "abcdefgh",
            "enabled": True,
        },
    )
    assert subscription.status_code == 200, subscription.text
    assert subscription.json()["status"] == "created"
    assert "subscriber-token" not in subscription.text
    assert "0123456789abcdef" not in subscription.text
    replay = await client.put(
        "/api/v1/portals/texas/notifications/subscriptions",
        headers=csrf(token),
        json={
            "channel": "web_push",
            "endpoint": "https://push.example/subscriber-token",
            "p256dh": "0123456789abcdef",
            "auth": "abcdefgh",
            "enabled": True,
        },
    )
    assert replay.json()["status"] == "unchanged"

    await make_admin(factory, "subscriber@example.com")
    overview = await client.get("/api/v1/portals/texas/admin/notifications")
    assert overview.status_code == 200
    assert overview.json()["subscriptions"] == {"web_push": 1}
    assert "subscriber-token" not in overview.text
    queued = await client.post(
        "/api/v1/portals/texas/admin/notifications/messages",
        headers=csrf(token),
        json={
            "title": "Tonight in Austin",
            "body": "A concise portal update.",
            "url": "/latest",
            "content_id": None,
            "channels": ["web_push"],
        },
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["queued"] == 1

    gateway = RecordingGateway()
    async with factory() as session, session.begin():
        sent, failed = await NotificationDeliveryService(session, gateway).deliver_batch(10)
        assert (sent, failed) == (1, 0)
    async with factory() as session, session.begin():
        repeated = await NotificationDeliveryService(session, gateway).deliver_batch(10)
        assert repeated == (0, 0)
    assert len(gateway.calls) == 1
    assert gateway.calls[0][1].delivery_id is not None

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(NotificationSubscription)) == 1
        delivery = await session.scalar(select(NotificationDelivery))
        assert delivery is not None and delivery.status == "sent" and delivery.attempts == 1
        audit = await session.scalar(
            select(EditorialAuditLog).where(EditorialAuditLog.action == "notification_send")
        )
        assert audit is not None and audit.after["queued"] == 1

    subscription_id = subscription.json()["subscription"]["id"]
    assert (
        await client.delete(
            f"/api/v1/portals/texas/notifications/subscriptions/{subscription_id}",
            headers=csrf(token),
        )
    ).status_code == 204
    async with factory() as session:
        revoked = await session.get(NotificationSubscription, subscription_id)
        assert revoked is not None
        assert revoked.enabled is False
        assert revoked.destination == "revoked"
        assert revoked.configuration == {}
        assert await session.scalar(select(func.count()).select_from(NotificationDelivery)) == 1


async def test_notification_retry_schedule_and_provider_idempotency(runtime: Any) -> None:
    client, factory, _domain = runtime
    token = await register(client, "retry@example.com")
    subscribed = await client.put(
        "/api/v1/portals/texas/notifications/subscriptions",
        headers=csrf(token),
        json={"channel": "email", "enabled": True},
    )
    assert subscribed.status_code == 200
    await make_admin(factory, "retry@example.com")
    queued = await client.post(
        "/api/v1/portals/texas/admin/notifications/messages",
        headers=csrf(token),
        json={
            "title": "Retry delivery",
            "body": "Durable delivery body.",
            "url": "/latest",
            "content_id": None,
            "channels": ["email"],
        },
    )
    assert queued.status_code == 202 and queued.json()["queued"] == 1

    started_at = datetime.now(UTC)
    gateway = FlakyGateway(failures=1)
    async with factory() as session, session.begin():
        result = await NotificationDeliveryService(session, gateway, now=started_at).deliver_batch(
            10
        )
        assert result == (0, 0)
    async with factory() as session:
        delivery = await session.scalar(select(NotificationDelivery))
        assert delivery is not None
        delivery_id = delivery.id
        assert delivery.status == "pending"
        assert delivery.attempts == 1
        assert delivery.error_code == "gateway_timeout"
        assert delivery.next_attempt_at == started_at + timedelta(minutes=1)

    async with factory() as session, session.begin():
        too_early = await NotificationDeliveryService(
            session, gateway, now=started_at + timedelta(seconds=59)
        ).deliver_batch(10)
        assert too_early == (0, 0)
    async with factory() as session, session.begin():
        recovered = await NotificationDeliveryService(
            session, gateway, now=started_at + timedelta(minutes=1)
        ).deliver_batch(10)
        assert recovered == (1, 0)
    assert gateway.delivery_ids == [delivery_id, delivery_id]
    async with factory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        assert delivery is not None
        assert delivery.status == "sent"
        assert delivery.attempts == 2
        assert delivery.error_code is None

    second = await client.post(
        "/api/v1/portals/texas/admin/notifications/messages",
        headers=csrf(token),
        json={
            "title": "Final retry",
            "body": "This delivery reaches the retry limit.",
            "url": "/latest",
            "content_id": None,
            "channels": ["email"],
        },
    )
    assert second.status_code == 202 and second.json()["queued"] == 1
    async with factory() as session, session.begin():
        final_delivery = await session.scalar(
            select(NotificationDelivery).where(NotificationDelivery.status == "pending")
        )
        assert final_delivery is not None
        final_delivery.attempts = 4
        final_delivery.next_attempt_at = started_at
        final_id = final_delivery.id
    always_failing = FlakyGateway(failures=10)
    async with factory() as session, session.begin():
        exhausted = await NotificationDeliveryService(
            session, always_failing, now=started_at
        ).deliver_batch(10)
        assert exhausted == (0, 1)
    async with factory() as session:
        final_delivery = await session.get(NotificationDelivery, final_id)
        assert final_delivery is not None
        assert final_delivery.status == "failed"
        assert final_delivery.attempts == 5
        assert final_delivery.error_code == "gateway_timeout"
