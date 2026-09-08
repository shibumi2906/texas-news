from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_phase_5_feeds import (  # noqa: F401
    NOW,
    add_story,
    database,
    redis_client,
    seed_domain,
)

from news_platform.core.logging import RequestLoggingMiddleware
from news_platform.modules.analytics.api.router import router as analytics_router
from news_platform.modules.analytics.application.service import (
    AnalyticsAggregationService,
    AnalyticsIngestionService,
    process_analytics_once,
)
from news_platform.modules.analytics.domain.models import BehaviorEvent, BehaviorEventAggregation
from news_platform.modules.analytics.domain.schemas import BehaviorEventCreate
from news_platform.modules.content.domain.models import ContentStatus
from news_platform.modules.engagement.application.service import EngagementCounterService
from news_platform.modules.engagement.domain.models import (
    ContentEngagementCounter,
    EngagementCounterUpdate,
)
from news_platform.modules.feeds.api.router import router as feeds_router
from news_platform.modules.feeds.infrastructure.cache import CACHE_EPOCH_KEY

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def runtime(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
    redis_client: Redis,  # noqa: F811
) -> AsyncIterator[
    tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]]
]:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        story = await add_story(session, domain, 701, published_at=NOW - timedelta(hours=1))
    domain["story"] = story

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.db_session_factory = factory
    app.state.redis = redis_client
    app.state.settings = SimpleNamespace(
        analytics_event_max_age_days=7,
        analytics_future_skew_seconds=300,
        feed_cache_ttl_seconds=30,
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(analytics_router)
    app.include_router(feeds_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory, redis_client, domain


def event_payload(
    identity: int,
    event_type: str,
    *,
    content_id: UUID | None,
    properties: dict[str, Any] | None = None,
    timestamp: datetime = NOW,
) -> dict[str, Any]:
    return {
        "id": str(UUID(int=identity)),
        "anonymous_id": "anonymous-browser-1",
        "session_id": "session-1",
        "event_type": event_type,
        "content_id": str(content_id) if content_id else None,
        "timestamp": timestamp.isoformat(),
        "properties": properties or {},
    }


async def test_behavior_event_persists_only_spec_fields(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    engine, _factory = database

    def column_names(connection: Any) -> set[str]:
        return {
            str(column["name"]) for column in inspect(connection).get_columns("behavior_events")
        }

    async with engine.connect() as connection:
        actual = await connection.run_sync(column_names)
    assert actual == {
        "id",
        "portal_id",
        "user_id",
        "anonymous_id",
        "session_id",
        "event_type",
        "content_id",
        "entity_id",
        "geography_id",
        "timestamp",
        "properties",
    }


@pytest.mark.parametrize(
    ("event_type", "properties"),
    [
        ("impression", {"surface": "home", "position": 1}),
        ("click", {"surface": "home", "position": 1}),
        ("content_open", {"surface": "story"}),
        ("scroll", {"percent": 50}),
        ("video_start", {"offset_seconds": 0}),
        ("watch_time", {"seconds": 12}),
        ("completion", {}),
        ("share", {"channel": "copy_link"}),
        ("search", {"result_count": 4}),
    ],
)
async def test_collects_each_phase_7_event_type(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
    event_type: str,
    properties: dict[str, Any],
) -> None:
    client, factory, _redis, domain = runtime
    content_id = None if event_type == "search" else domain["story"].id
    response = await client.post(
        "/api/v1/portals/texas/analytics/events",
        json=event_payload(710, event_type, content_id=content_id, properties=properties),
    )
    assert response.status_code == 201
    assert response.json() == {"id": str(UUID(int=710)), "status": "accepted"}
    async with factory() as session:
        stored = await session.get(BehaviorEvent, UUID(int=710))
        assert stored is not None
        assert stored.event_type == event_type and stored.properties == properties


async def test_event_replay_is_idempotent_and_conflicting_reuse_is_rejected(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    client, factory, _redis, domain = runtime
    payload = event_payload(720, "content_open", content_id=domain["story"].id)
    accepted = await client.post("/api/v1/portals/texas/analytics/events", json=payload)
    duplicate = await client.post("/api/v1/portals/texas/analytics/events", json=payload)
    conflict = await client.post(
        "/api/v1/portals/texas/analytics/events",
        json={**payload, "event_type": "click"},
    )
    assert accepted.status_code == 201
    assert duplicate.status_code == 200 and duplicate.json()["status"] == "duplicate"
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "EVENT_ID_CONFLICT"
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(BehaviorEvent)) == 1


async def test_concurrent_duplicate_delivery_is_exactly_once(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    _client, factory, _redis, domain = runtime
    payload = BehaviorEventCreate.model_validate(
        event_payload(721, "click", content_id=domain["story"].id)
    )

    async def collect() -> str:
        async with factory() as session, session.begin():
            return (
                await AnalyticsIngestionService(session, now=NOW).collect("texas", payload)
            ).status

    assert sorted(await asyncio.gather(collect(), collect())) == ["accepted", "duplicate"]


@pytest.mark.parametrize(
    "change",
    [
        {"event_type": "unsupported"},
        {"anonymous_id": None},
        {"content_id": None},
        {"properties": {"email": "private@example.com"}},
        {"timestamp": "2026-09-05T12:00:00"},
    ],
)
async def test_rejects_malformed_or_privacy_unsafe_events(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
    change: dict[str, Any],
) -> None:
    client, _factory, _redis, domain = runtime
    payload = event_payload(730, "impression", content_id=domain["story"].id)
    response = await client.post(
        "/api/v1/portals/texas/analytics/events", json={**payload, **change}
    )
    assert response.status_code == 422


async def test_privacy_values_are_neither_stored_logged_nor_echoed(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, factory, _redis, _domain = runtime
    sensitive = "private-person@example.com"
    caplog.set_level("INFO", logger="news_platform.request")
    rejected = await client.post(
        "/api/v1/portals/texas/analytics/events",
        headers={"User-Agent": sensitive, "X-Forwarded-For": "203.0.113.99"},
        json={
            **event_payload(735, "search", content_id=None),
            "properties": {"query": sensitive},
        },
    )
    assert rejected.status_code == 422
    assert rejected.json() == {"detail": {"code": "INVALID_BEHAVIOR_EVENT"}}
    assert sensitive not in rejected.text and "203.0.113.99" not in rejected.text
    assert sensitive not in caplog.text and "203.0.113.99" not in caplog.text

    accepted = await client.post(
        "/api/v1/portals/texas/analytics/events",
        headers={"User-Agent": sensitive, "X-Forwarded-For": "203.0.113.99"},
        json=event_payload(
            736,
            "search",
            content_id=None,
            properties={"result_count": 3},
        ),
    )
    assert accepted.status_code == 201
    async with factory() as session:
        stored = await session.get(BehaviorEvent, UUID(int=736))
        assert stored is not None and stored.properties == {"result_count": 3}
        serialized = repr(stored.__dict__)
        assert sensitive not in serialized and "203.0.113.99" not in serialized


@pytest.mark.parametrize(
    ("event_type", "properties"),
    [
        ("watch_time", {"seconds": -1}),
        ("watch_time", {"seconds": 0}),
        ("watch_time", {"seconds": 86_401}),
        ("watch_time", {"seconds": 1.5}),
        ("scroll", {}),
        ("scroll", {"percent": -1}),
        ("scroll", {"percent": 101}),
        ("scroll", {"percent": 10.5}),
        ("completion", {"percent": 100}),
        ("search", {"query": "private terms"}),
        ("search", {"surface": "private terms"}),
    ],
)
async def test_event_specific_values_are_bounded(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
    event_type: str,
    properties: dict[str, Any],
) -> None:
    client, _factory, _redis, domain = runtime
    content_id = None if event_type == "search" else domain["story"].id
    response = await client.post(
        "/api/v1/portals/texas/analytics/events",
        json=event_payload(737, event_type, content_id=content_id, properties=properties),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "INVALID_BEHAVIOR_EVENT"}}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_non_finite_watch_time_and_scroll_values_are_rejected(value: float) -> None:
    for event_type, property_name in (("watch_time", "seconds"), ("scroll", "percent")):
        with pytest.raises(ValidationError):
            BehaviorEventCreate.model_validate(
                event_payload(
                    738,
                    event_type,
                    content_id=UUID(int=701),
                    properties={property_name: value},
                )
            )


async def test_validates_timestamp_public_content_and_portal_scope(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    client, factory, _redis, domain = runtime
    story_id = domain["story"].id
    too_old = await client.post(
        "/api/v1/portals/texas/analytics/events",
        json=event_payload(
            740,
            "click",
            content_id=story_id,
            timestamp=datetime.now(UTC) - timedelta(days=8),
        ),
    )
    too_future = await client.post(
        "/api/v1/portals/texas/analytics/events",
        json=event_payload(
            741,
            "click",
            content_id=story_id,
            timestamp=datetime.now(UTC) + timedelta(seconds=301),
        ),
    )
    wrong_portal = await client.post(
        "/api/v1/portals/oklahoma/analytics/events",
        json=event_payload(742, "click", content_id=story_id),
    )
    in_scope_geography = await client.post(
        "/api/v1/portals/texas/analytics/events",
        json={
            **event_payload(744, "search", content_id=None),
            "geography_id": str(domain["dallas"].id),
        },
    )
    out_of_scope_geography = await client.post(
        "/api/v1/portals/texas/analytics/events",
        json={
            **event_payload(745, "search", content_id=None),
            "geography_id": str(domain["oklahoma"].id),
        },
    )
    async with factory() as session, session.begin():
        story = await session.get(type(domain["story"]), story_id)
        assert story is not None
        story.status = ContentStatus.UNPUBLISHED
    not_public = await client.post(
        "/api/v1/portals/texas/analytics/events",
        json=event_payload(743, "click", content_id=story_id),
    )
    assert too_old.status_code == 422 and too_future.status_code == 422
    assert wrong_portal.status_code == 404 and not_public.status_code == 404
    assert in_scope_geography.status_code == 201
    assert out_of_scope_geography.status_code == 404


async def test_aggregation_maps_events_once_and_invalidates_trending(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    _client, factory, redis, domain = runtime
    story_id = domain["story"].id
    events = [
        (750, "impression", {}),
        (751, "click", {}),
        (752, "content_open", {}),
        (753, "watch_time", {"seconds": 19}),
        (754, "completion", {}),
        (755, "share", {}),
        (756, "scroll", {"percent": 75}),
        (757, "video_start", {}),
        (758, "search", {}),
    ]
    async with factory() as session, session.begin():
        service = AnalyticsIngestionService(session, now=NOW)
        for identity, event_type, properties in events:
            await service.collect(
                "texas",
                BehaviorEventCreate.model_validate(
                    event_payload(
                        identity,
                        event_type,
                        content_id=None if event_type == "search" else story_id,
                        properties=properties,
                    )
                ),
            )

    aggregated, invalidated = await process_analytics_once(factory, redis, 100)
    replayed, repeated_invalidation = await process_analytics_once(factory, redis, 100)
    assert aggregated.processed == 9 and aggregated.ranking_updates == 6
    assert invalidated.delivered == 6
    assert replayed.processed == repeated_invalidation.delivered == 0
    assert await redis.get(CACHE_EPOCH_KEY) == "1"
    async with factory() as session:
        counter = await session.get(ContentEngagementCounter, story_id)
        assert counter is not None
        assert (
            counter.impressions,
            counter.clicks,
            counter.views,
            counter.comments,
            counter.likes,
            counter.shares,
            counter.saves,
            counter.watch_time_seconds,
            counter.completions,
        ) == (1, 1, 1, 0, 0, 1, 0, 19, 1)
        assert await session.scalar(select(func.count()).select_from(EngagementCounterUpdate)) == 6
        assert await session.scalar(
            select(func.count()).select_from(BehaviorEventAggregation)
        ) == len(events)


async def test_aggregation_rolls_back_and_retries_without_double_counting(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    _client, factory, redis, domain = runtime
    payload = BehaviorEventCreate.model_validate(
        event_payload(760, "content_open", content_id=domain["story"].id)
    )
    async with factory() as session, session.begin():
        await AnalyticsIngestionService(session, now=NOW).collect("texas", payload)

    class FailingRedis:
        async def incr(self, _key: str) -> None:
            raise ConnectionError("redis unavailable")

    with pytest.raises(ConnectionError, match="redis unavailable"):
        await process_analytics_once(factory, FailingRedis(), 100)
    async with factory() as session:
        counter = await session.get(ContentEngagementCounter, domain["story"].id)
        receipt = await session.get(BehaviorEventAggregation, UUID(int=760))
        assert counter is not None and counter.views == 1
        assert receipt is not None and receipt.feed_invalidated_at is None

    aggregated, invalidated = await process_analytics_once(factory, redis, 100)
    assert aggregated.processed == 0 and invalidated.delivered == 1
    async with factory() as session:
        counter = await session.get(ContentEngagementCounter, domain["story"].id)
        assert counter is not None and counter.views == 1


async def test_aggregation_batch_is_transactional_on_mid_batch_failure(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _client, factory, redis, domain = runtime
    async with factory() as session, session.begin():
        service = AnalyticsIngestionService(session, now=NOW)
        for identity in (765, 766):
            await service.collect(
                "texas",
                BehaviorEventCreate.model_validate(
                    event_payload(identity, "click", content_id=domain["story"].id)
                ),
            )

    original_increment = EngagementCounterService.increment
    calls = 0

    async def fail_second_increment(self: EngagementCounterService, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated aggregate failure")
        return await original_increment(self, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(EngagementCounterService, "increment", fail_second_increment)
        with pytest.raises(RuntimeError, match="simulated aggregate failure"):
            async with factory() as session, session.begin():
                await AnalyticsAggregationService(session).aggregate_batch(100)

    async with factory() as session:
        assert await session.get(ContentEngagementCounter, domain["story"].id) is None
        assert await session.scalar(select(func.count()).select_from(BehaviorEventAggregation)) == 0

    aggregated, invalidated = await process_analytics_once(factory, redis, 100)
    assert aggregated.processed == aggregated.ranking_updates == 2
    assert invalidated.delivered == 2
    async with factory() as session:
        counter = await session.get(ContentEngagementCounter, domain["story"].id)
        assert counter is not None and counter.clicks == 2


async def test_failure_after_receipt_flush_but_before_commit_is_reprocessable(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    _client, factory, redis, domain = runtime
    async with factory() as session, session.begin():
        await AnalyticsIngestionService(session, now=NOW).collect(
            "texas",
            BehaviorEventCreate.model_validate(
                event_payload(767, "share", content_id=domain["story"].id)
            ),
        )

    with pytest.raises(RuntimeError, match="simulated pre-commit crash"):
        async with factory() as session, session.begin():
            result = await AnalyticsAggregationService(session).aggregate_batch(1)
            assert result.processed == result.ranking_updates == 1
            raise RuntimeError("simulated pre-commit crash")

    async with factory() as session:
        assert await session.get(ContentEngagementCounter, domain["story"].id) is None
        assert await session.get(BehaviorEventAggregation, UUID(int=767)) is None
        assert await session.scalar(select(func.count()).select_from(EngagementCounterUpdate)) == 0

    aggregated, invalidated = await process_analytics_once(factory, redis, 1)
    assert aggregated.processed == aggregated.ranking_updates == 1
    assert invalidated.delivered == 1


async def test_counter_overflow_rolls_back_without_losing_event(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    _client, factory, _redis, domain = runtime
    story_id = domain["story"].id
    async with factory() as session, session.begin():
        await AnalyticsIngestionService(session, now=NOW).collect(
            "texas",
            BehaviorEventCreate.model_validate(event_payload(768, "click", content_id=story_id)),
        )
        session.add(ContentEngagementCounter(content_item_id=story_id, clicks=2**63 - 1))

    with pytest.raises(DBAPIError):
        async with factory() as session, session.begin():
            await AnalyticsAggregationService(session).aggregate_batch(1)

    async with factory() as session:
        counter = await session.get(ContentEngagementCounter, story_id)
        assert counter is not None and counter.clicks == 2**63 - 1
        assert await session.get(BehaviorEventAggregation, UUID(int=768)) is None
        assert await session.scalar(select(func.count()).select_from(EngagementCounterUpdate)) == 0


async def test_uncertain_redis_ack_retries_without_losing_invalidation(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    _client, factory, redis, domain = runtime
    async with factory() as session, session.begin():
        await AnalyticsIngestionService(session, now=NOW).collect(
            "texas",
            BehaviorEventCreate.model_validate(
                event_payload(769, "impression", content_id=domain["story"].id)
            ),
        )

    class UncertainRedis:
        async def incr(self, key: str) -> None:
            await redis.incr(key)
            raise ConnectionError("acknowledgement lost")

    with pytest.raises(ConnectionError, match="acknowledgement lost"):
        await process_analytics_once(factory, UncertainRedis(), 100)
    assert await redis.get(CACHE_EPOCH_KEY) == "1"
    async with factory() as session:
        receipt = await session.get(BehaviorEventAggregation, UUID(int=769))
        counter = await session.get(ContentEngagementCounter, domain["story"].id)
        assert receipt is not None and receipt.feed_invalidated_at is None
        assert counter is not None and counter.impressions == 1

    aggregated, invalidated = await process_analytics_once(factory, redis, 100)
    assert aggregated.processed == 0 and invalidated.delivered == 1
    assert await redis.get(CACHE_EPOCH_KEY) == "2"
    async with factory() as session:
        receipt = await session.get(BehaviorEventAggregation, UUID(int=769))
        counter = await session.get(ContentEngagementCounter, domain["story"].id)
        assert receipt is not None and receipt.feed_invalidated_at is not None
        assert counter is not None and counter.impressions == 1


async def test_worker_concurrency_does_not_double_count(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    _client, factory, redis, domain = runtime
    async with factory() as session, session.begin():
        service = AnalyticsIngestionService(session, now=NOW)
        for identity in range(770, 780):
            await service.collect(
                "texas",
                BehaviorEventCreate.model_validate(
                    event_payload(identity, "impression", content_id=domain["story"].id)
                ),
            )
    await asyncio.gather(
        process_analytics_once(factory, redis, 5),
        process_analytics_once(factory, redis, 5),
    )
    async with factory() as session:
        counter = await session.get(ContentEngagementCounter, domain["story"].id)
        assert counter is not None and counter.impressions == 10
        assert (
            await session.scalar(select(func.count()).select_from(BehaviorEventAggregation)) == 10
        )


async def test_concurrent_duplicate_delivery_and_workers_apply_once(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    _client, factory, redis, domain = runtime
    payload = BehaviorEventCreate.model_validate(
        event_payload(780, "content_open", content_id=domain["story"].id)
    )
    start = asyncio.Event()

    async def collect() -> str:
        await start.wait()
        async with factory() as session, session.begin():
            return (
                await AnalyticsIngestionService(session, now=NOW).collect("texas", payload)
            ).status

    async def work() -> None:
        await start.wait()
        await process_analytics_once(factory, redis, 1)

    tasks = [
        asyncio.create_task(collect()),
        asyncio.create_task(collect()),
        asyncio.create_task(work()),
        asyncio.create_task(work()),
    ]
    start.set()
    results = await asyncio.gather(*tasks)
    assert sorted(result for result in results if isinstance(result, str)) == [
        "accepted",
        "duplicate",
    ]
    await process_analytics_once(factory, redis, 1)

    async with factory() as session:
        counter = await session.get(ContentEngagementCounter, domain["story"].id)
        assert counter is not None and counter.views == 1
        assert await session.scalar(select(func.count()).select_from(BehaviorEvent)) == 1
        assert await session.scalar(select(func.count()).select_from(BehaviorEventAggregation)) == 1
        assert await session.scalar(select(func.count()).select_from(EngagementCounterUpdate)) == 1


async def test_aggregation_invalidates_existing_trending_cursor(
    runtime: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], Redis, dict[str, Any]],
) -> None:
    client, factory, redis, domain = runtime
    async with factory() as session, session.begin():
        for identity in range(781, 784):
            await add_story(session, domain, identity, published_at=NOW - timedelta(hours=1))
    first = await client.get(
        "/api/v1/portals/texas/feeds/trending", params={"language": "en", "limit": 2}
    )
    assert first.status_code == 200 and first.json()["next_cursor"] is not None
    event = event_payload(790, "click", content_id=domain["story"].id)
    assert (
        await client.post("/api/v1/portals/texas/analytics/events", json=event)
    ).status_code == 201
    await process_analytics_once(factory, redis, 100)
    stale = await client.get(
        "/api/v1/portals/texas/feeds/trending",
        params={
            "language": "en",
            "limit": 2,
            "cursor": first.json()["next_cursor"],
        },
    )
    assert stale.status_code == 400
    assert stale.json()["detail"]["code"] == "INVALID_FEED_CURSOR"
