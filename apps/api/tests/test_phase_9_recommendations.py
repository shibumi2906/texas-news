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
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_phase_5_feeds import NOW, add_story, database, redis_client, seed_domain  # noqa: F401
from test_phase_8_users_community import csrf, register

from news_platform.modules.analytics.api.router import router as analytics_router
from news_platform.modules.analytics.domain.models import BehaviorEvent
from news_platform.modules.community.api.router import router as community_router
from news_platform.modules.community.application import service as community_service_module
from news_platform.modules.community.domain.models import Follow
from news_platform.modules.content.domain.models import ContentEntity, ContentStatus
from news_platform.modules.entities.domain.models import Entity, EntityType
from news_platform.modules.recommendations.api.router import feed_router, router
from news_platform.modules.recommendations.application import (
    service as recommendation_service_module,
)
from news_platform.modules.recommendations.application.service import (
    RecommendationFeedService,
    decayed_affinity_score,
    process_affinities_once,
)
from news_platform.modules.recommendations.domain.cursor import RecommendationCursor
from news_platform.modules.recommendations.domain.models import (
    RecommendationGeneration,
    RecommendationSignalReceipt,
    UserAffinity,
    UserInterest,
)
from news_platform.modules.users.api.router import router as users_router
from news_platform.modules.users.domain.models import AuthSession, User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_affinity_decay_uses_configured_half_life() -> None:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    assert decayed_affinity_score(20.0, now - timedelta(days=30), now, 30.0) == 10.0


@pytest_asyncio.fixture
async def runtime(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
    redis_client: Redis,  # noqa: F811
) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], dict[str, Any]]]:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        sports_new = await add_story(
            session, domain, 901, published_at=NOW - timedelta(hours=1), category="sports"
        )
        music_old = await add_story(
            session, domain, 902, published_at=NOW - timedelta(hours=8), category="music"
        )
        music_older = await add_story(
            session, domain, 903, published_at=NOW - timedelta(hours=12), category="music"
        )
        artist = Entity(
            type=EntityType.ARTIST,
            canonical_name="Phase Nine Artist",
            slug="phase-nine-artist",
            aliases=[],
            external_ids={},
            metadata_={},
        )
        session.add(artist)
        await session.flush()
        session.add_all(
            [
                ContentEntity(content_item_id=music_old.id, entity_id=artist.id),
                ContentEntity(content_item_id=music_older.id, entity_id=artist.id),
            ]
        )
        domain.update(
            sports_new=sports_new,
            music_old=music_old,
            music_older=music_older,
            artist=artist,
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.db_session_factory = factory
    app.state.redis = redis_client
    app.state.settings = SimpleNamespace(
        environment="test",
        auth_session_hours=168,
        auth_login_rate_limit=20,
        auth_rate_limit_window_seconds=60,
        auth_allowed_origins="http://test",
        community_rate_limit=50,
        community_rate_limit_window_seconds=60,
        analytics_event_max_age_days=7,
        analytics_future_skew_seconds=300,
    )
    app.include_router(users_router)
    app.include_router(community_router)
    app.include_router(analytics_router)
    app.include_router(router)
    app.include_router(feed_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory, domain


def feed_path(kind: str) -> str:
    return f"/api/v1/portals/texas/feeds/{kind}"


async def test_personalized_feeds_require_durable_portal_session(runtime: Any) -> None:
    client, _factory, _domain = runtime
    assert (
        await client.get(feed_path("for-you"), params={"language": "en", "limit": 10})
    ).status_code == 401
    await register(client)
    assert (
        await client.get(
            feed_path("for-you"),
            params={"language": "en", "limit": 10},
            headers={"X-User-Id": str(uuid4()), "X-Role": "admin"},
        )
    ).status_code == 200
    assert (
        await client.get(
            "/api/v1/portals/oklahoma/feeds/for-you", params={"language": "en", "limit": 10}
        )
    ).status_code == 401


async def test_cold_start_is_deterministic_and_interests_change_ranking(runtime: Any) -> None:
    client, factory, domain = runtime
    token = await register(client)
    first = await client.get(feed_path("for-you"), params={"language": "en", "limit": 10})
    repeat = await client.get(feed_path("for-you"), params={"language": "en", "limit": 10})
    assert first.json()["items"] == repeat.json()["items"]
    assert first.json()["items"][0]["id"] == str(domain["sports_new"].id)

    updated = await client.put(
        "/api/v1/portals/texas/recommendations/me/interests",
        headers=csrf(token),
        json={
            "items": [
                {"target_type": "category", "target_id": str(domain["music"].id), "weight": 5}
            ]
        },
    )
    assert updated.status_code == 200
    personalized = await client.get(feed_path("for-you"), params={"language": "en", "limit": 10})
    assert personalized.json()["items"][0]["id"] == str(domain["music_old"].id)
    async with factory() as session:
        assert await session.scalar(select(RecommendationGeneration.generation)) == 1


async def test_following_cursor_is_user_bound_and_invalidated_by_follow_change(
    runtime: Any,
) -> None:
    client, _factory, domain = runtime
    token = await register(client)
    for_you_before_follow = await client.get(
        feed_path("for-you"), params={"language": "en", "limit": 1}
    )
    for_you_cursor = for_you_before_follow.json()["next_cursor"]
    assert for_you_cursor
    follow = f"/api/v1/portals/texas/community/follows/entity/{domain['artist'].id}"
    assert (await client.put(follow, headers=csrf(token))).status_code == 200
    assert (
        await client.get(
            feed_path("for-you"),
            params={"language": "en", "limit": 1, "cursor": for_you_cursor},
        )
    ).status_code == 400
    first = await client.get(feed_path("following"), params={"language": "en", "limit": 1})
    assert first.status_code == 200
    cursor = first.json()["next_cursor"]
    assert cursor
    second = await client.get(
        feed_path("following"), params={"language": "en", "limit": 1, "cursor": cursor}
    )
    assert second.json()["items"][0]["id"] == str(domain["music_older"].id)

    other = httpx.AsyncClient(transport=client._transport, base_url="http://test")
    try:
        await register(other, "other-nine@example.com", "Other Nine")
        assert (
            await other.get(feed_path("following"), params={"language": "en", "limit": 10})
        ).json()["items"] == []
        assert (
            await other.get(
                feed_path("following"), params={"language": "en", "limit": 1, "cursor": cursor}
            )
        ).status_code == 400
    finally:
        await other.aclose()

    for_you_before_unfollow = await client.get(
        feed_path("for-you"), params={"language": "en", "limit": 1}
    )
    for_you_cursor = for_you_before_unfollow.json()["next_cursor"]
    assert for_you_cursor
    await client.delete(follow, headers=csrf(token))
    stale = await client.get(
        feed_path("following"), params={"language": "en", "limit": 1, "cursor": cursor}
    )
    assert stale.status_code == 400
    assert (
        await client.get(
            feed_path("for-you"),
            params={"language": "en", "limit": 1, "cursor": for_you_cursor},
        )
    ).status_code == 400


async def test_authenticated_behavior_is_private_idempotent_and_builds_affinity(
    runtime: Any,
) -> None:
    client, factory, domain = runtime
    token = await register(client)
    event_id = uuid4()
    payload = {
        "id": str(event_id),
        "event_type": "content_open",
        "content_id": str(domain["music_old"].id),
        "timestamp": NOW.isoformat(),
        "properties": {"surface": "story"},
    }
    injected = dict(payload, user_id=str(uuid4()), role="admin", anonymous_id="old-browser")
    assert (
        await client.post(
            "/api/v1/portals/texas/analytics/me/events", headers=csrf(token), json=injected
        )
    ).status_code == 422
    accepted = await client.post(
        "/api/v1/portals/texas/analytics/me/events", headers=csrf(token), json=payload
    )
    duplicate = await client.post(
        "/api/v1/portals/texas/analytics/me/events", headers=csrf(token), json=payload
    )
    assert accepted.status_code == 201 and duplicate.status_code == 200

    first_page = await client.get(feed_path("for-you"), params={"language": "en", "limit": 1})
    cursor = first_page.json()["next_cursor"]
    assert cursor

    results = await asyncio.gather(
        process_affinities_once(factory, 100), process_affinities_once(factory, 100)
    )
    assert sum(result.processed for result in results) == 1
    async with factory() as session:
        event = await session.get(BehaviorEvent, event_id)
        assert event is not None and event.user_id is not None and event.anonymous_id is None
        assert (
            await session.scalar(select(func.count()).select_from(RecommendationSignalReceipt)) == 1
        )
        kinds = set((await session.scalars(select(UserAffinity.target_type))).all())
        assert kinds == {"category", "entity", "geography"}
    stale = await client.get(
        feed_path("for-you"),
        params={"language": "en", "limit": 1, "cursor": cursor},
    )
    assert stale.status_code == 400
    assert stale.json() == {
        "detail": {
            "code": "INVALID_RECOMMENDATION_CURSOR",
            "message": "invalid, stale, or mismatched recommendation cursor",
        }
    }
    fresh = await client.get(feed_path("for-you"), params={"language": "en", "limit": 10})
    serialized = str(fresh.json()).lower()
    assert "affinity" not in serialized
    assert "interest" not in serialized
    assert "weight" not in serialized


async def test_non_public_content_never_appears_or_updates_affinity(runtime: Any) -> None:
    client, factory, domain = runtime
    token = await register(client)
    await client.put(
        f"/api/v1/portals/texas/community/follows/entity/{domain['artist'].id}", headers=csrf(token)
    )
    async with factory() as session, session.begin():
        story = await session.get(type(domain["music_old"]), domain["music_old"].id)
        assert story is not None
        story.status = ContentStatus.UNPUBLISHED
    following = await client.get(feed_path("following"), params={"language": "en", "limit": 10})
    assert str(domain["music_old"].id) not in {item["id"] for item in following.json()["items"]}


async def test_private_or_moderatable_community_events_do_not_affect_recommendations(
    runtime: Any,
) -> None:
    client, factory, domain = runtime
    token = await register(client)
    story = domain["music_old"]
    assert (
        await client.put(
            f"/api/v1/portals/texas/community/stories/{story.slug}/save",
            headers=csrf(token),
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/portals/texas/community/stories/{story.slug}/comments",
            headers=csrf(token),
            json={"id": str(uuid4()), "body": "This may later be moderated."},
        )
    ).status_code == 201

    result = await process_affinities_once(factory, 100)
    assert (result.processed, result.applied) == (2, 0)
    async with factory() as session:
        receipts = list((await session.scalars(select(RecommendationSignalReceipt))).all())
        assert len(receipts) == 2 and all(not receipt.applied for receipt in receipts)
        assert await session.scalar(select(func.count()).select_from(UserAffinity)) == 0
        assert await session.scalar(select(func.count()).select_from(RecommendationGeneration)) == 0


async def test_interest_state_is_portal_and_user_private(runtime: Any) -> None:
    client, _factory, domain = runtime
    token = await register(client)
    path = "/api/v1/portals/texas/recommendations/me/interests"
    await client.put(
        path,
        headers=csrf(token),
        json={
            "items": [
                {"target_type": "category", "target_id": str(domain["sports"].id), "weight": 4}
            ]
        },
    )
    cross_portal_interest = await client.put(
        path,
        headers=csrf(token),
        json={
            "items": [
                {
                    "target_type": "geography",
                    "target_id": str(domain["oklahoma"].id),
                    "weight": 5,
                }
            ]
        },
    )
    assert cross_portal_interest.status_code == 404
    assert (
        await client.put(
            f"/api/v1/portals/texas/community/follows/geography/{domain['oklahoma'].id}",
            headers=csrf(token),
        )
    ).status_code == 404
    other = httpx.AsyncClient(transport=client._transport, base_url="http://test")
    try:
        await register(other, "private-nine@example.com", "Private Nine")
        assert (await other.get(path)).json() == {"items": []}
    finally:
        await other.aclose()


async def test_behavior_event_identity_is_immutable_across_anonymous_and_authenticated_routes(
    runtime: Any,
) -> None:
    client, factory, _domain = runtime
    token = await register(client)
    event_id = uuid4()
    timestamp = NOW.isoformat()
    anonymous = {
        "id": str(event_id),
        "anonymous_id": "phase9-anonymous",
        "session_id": "phase9-browser-session",
        "event_type": "search",
        "timestamp": timestamp,
        "properties": {"result_count": 1},
    }
    authenticated = {
        "id": str(event_id),
        "event_type": "search",
        "timestamp": timestamp,
        "properties": {"result_count": 1},
    }
    assert (
        await client.post("/api/v1/portals/texas/analytics/events", json=anonymous)
    ).status_code == 201
    conflict = await client.post(
        "/api/v1/portals/texas/analytics/me/events",
        headers=csrf(token),
        json=authenticated,
    )
    assert conflict.status_code == 409

    async with factory() as session:
        stored = await session.get(BehaviorEvent, event_id)
        assert stored is not None
        assert stored.user_id is None
        assert stored.anonymous_id == "phase9-anonymous"
        original_session_id = stored.session_id

    await client.post("/api/v1/portals/texas/auth/logout", headers=csrf(token))
    async with factory() as session:
        stored = await session.get(BehaviorEvent, event_id)
        assert stored is not None
        assert stored.user_id is None
        assert stored.session_id == original_session_id

    reverse_id = uuid4()
    authenticated["id"] = str(reverse_id)
    second_token = await register(client, "identity-two@example.com", "Identity Two")
    assert (
        await client.post(
            "/api/v1/portals/texas/analytics/me/events",
            headers=csrf(second_token),
            json=authenticated,
        )
    ).status_code == 201
    anonymous["id"] = str(reverse_id)
    assert (
        await client.post("/api/v1/portals/texas/analytics/events", json=anonymous)
    ).status_code == 409
    async with factory() as session:
        stored = await session.get(BehaviorEvent, reverse_id)
        assert stored is not None and stored.user_id is not None
        assert stored.anonymous_id is None
        authenticated_user_id = stored.user_id
        authenticated_session_id = stored.session_id

    assert (
        await client.post("/api/v1/portals/texas/auth/logout", headers=csrf(second_token))
    ).status_code == 200
    async with factory() as session:
        stored = await session.get(BehaviorEvent, reverse_id)
        assert stored is not None
        assert stored.user_id == authenticated_user_id
        assert stored.session_id == authenticated_session_id


async def test_for_you_cursor_reuses_snapshot_and_rejects_all_context_mismatches(
    runtime: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, factory, domain = runtime
    token = await register(client)
    first = await client.get(feed_path("for-you"), params={"language": "en", "limit": 1})
    cursor = first.json()["next_cursor"]
    assert cursor

    async with factory() as session:
        user = await session.scalar(select(User).where(User.email == "reader@example.com"))
        assert user is not None
        portal_id = await session.scalar(
            select(AuthSession.portal_id).where(AuthSession.user_id == user.id)
        )
        assert portal_id is not None
        generation = await session.scalar(
            select(RecommendationGeneration.generation).where(
                RecommendationGeneration.portal_id == portal_id,
                RecommendationGeneration.user_id == user.id,
            )
        )
    decoded = RecommendationCursor.decode(
        cursor,
        portal_id=portal_id,
        user_id=user.id,
        feed="for_you",
        language="en",
        generation=int(generation or 0),
    )
    observed: list[datetime] = []
    original_for_you = RecommendationFeedService._for_you

    async def capture_snapshot(self: Any, *args: Any, **kwargs: Any) -> Any:
        observed.append(args[-1])
        return await original_for_you(self, *args, **kwargs)

    class LaterDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> LaterDateTime:
            value = decoded.snapshot_at + timedelta(days=90)
            return cls.fromtimestamp(value.timestamp(), tz)

    monkeypatch.setattr(RecommendationFeedService, "_for_you", capture_snapshot)
    monkeypatch.setattr(recommendation_service_module, "datetime", LaterDateTime)
    second = await client.get(
        feed_path("for-you"), params={"language": "en", "limit": 1, "cursor": cursor}
    )
    assert second.status_code == 200
    assert observed == [decoded.snapshot_at]

    assert (
        await client.get(
            feed_path("following"), params={"language": "en", "limit": 1, "cursor": cursor}
        )
    ).status_code == 400
    assert (
        await client.get(
            feed_path("for-you"), params={"language": "es", "limit": 1, "cursor": cursor}
        )
    ).status_code == 400

    other = httpx.AsyncClient(transport=client._transport, base_url="http://test")
    try:
        await register(other, "cursor-other@example.com", "Cursor Other")
        assert (
            await other.get(
                feed_path("for-you"), params={"language": "en", "limit": 1, "cursor": cursor}
            )
        ).status_code == 400
    finally:
        await other.aclose()

    changed = await client.put(
        "/api/v1/portals/texas/recommendations/me/interests",
        headers=csrf(token),
        json={
            "items": [
                {"target_type": "category", "target_id": str(domain["music"].id), "weight": 5}
            ]
        },
    )
    assert changed.status_code == 200
    assert (
        await client.get(
            feed_path("for-you"), params={"language": "en", "limit": 1, "cursor": cursor}
        )
    ).status_code == 400


async def test_interest_and_follow_generation_changes_are_atomic_on_failure(
    runtime: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, factory, domain = runtime
    token = await register(client)

    async def fail_generation(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("forced generation failure")

    original_recommendation_bump = recommendation_service_module.bump_recommendation_generation
    monkeypatch.setattr(
        recommendation_service_module, "bump_recommendation_generation", fail_generation
    )
    with pytest.raises(RuntimeError, match="forced generation failure"):
        await client.put(
            "/api/v1/portals/texas/recommendations/me/interests",
            headers=csrf(token),
            json={
                "items": [
                    {
                        "target_type": "category",
                        "target_id": str(domain["music"].id),
                        "weight": 5,
                    }
                ]
            },
        )
    monkeypatch.setattr(
        recommendation_service_module,
        "bump_recommendation_generation",
        original_recommendation_bump,
    )
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(UserInterest)) == 0
        assert await session.scalar(select(func.count()).select_from(RecommendationGeneration)) == 0

    original_community_bump = community_service_module.bump_recommendation_generation
    monkeypatch.setattr(community_service_module, "bump_recommendation_generation", fail_generation)
    follow_path = f"/api/v1/portals/texas/community/follows/entity/{domain['artist'].id}"
    with pytest.raises(RuntimeError, match="forced generation failure"):
        await client.put(follow_path, headers=csrf(token))
    monkeypatch.setattr(
        community_service_module, "bump_recommendation_generation", original_community_bump
    )
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Follow)) == 0
        assert await session.scalar(select(func.count()).select_from(RecommendationGeneration)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BehaviorEvent)
                .where(BehaviorEvent.event_type == "follow")
            )
            == 0
        )


async def test_affinity_receipt_and_generation_are_atomic_and_retry_safe(
    runtime: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, factory, domain = runtime
    token = await register(client)
    event_id = uuid4()
    assert (
        await client.post(
            "/api/v1/portals/texas/analytics/me/events",
            headers=csrf(token),
            json={
                "id": str(event_id),
                "event_type": "content_open",
                "content_id": str(domain["music_old"].id),
                "timestamp": NOW.isoformat(),
                "properties": {"surface": "story"},
            },
        )
    ).status_code == 201

    original_bump = recommendation_service_module.bump_recommendation_generation

    async def fail_generation(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("forced affinity generation failure")

    monkeypatch.setattr(
        recommendation_service_module, "bump_recommendation_generation", fail_generation
    )
    with pytest.raises(RuntimeError, match="forced affinity generation failure"):
        await process_affinities_once(factory, 100)
    monkeypatch.setattr(
        recommendation_service_module, "bump_recommendation_generation", original_bump
    )

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(UserAffinity)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(RecommendationSignalReceipt)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(RecommendationGeneration)) == 0

    applied = await process_affinities_once(factory, 100)
    duplicate = await process_affinities_once(factory, 100)
    assert (applied.processed, applied.applied) == (1, 1)
    assert (duplicate.processed, duplicate.applied) == (0, 0)
    async with factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(RecommendationSignalReceipt)) == 1
        )
        assert await session.scalar(select(func.count()).select_from(UserAffinity)) == 3
        assert await session.scalar(select(RecommendationGeneration.generation)) == 1
