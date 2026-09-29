from __future__ import annotations

import asyncio
import os
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
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from news_platform.infrastructure.database import Base
from news_platform.infrastructure.redis import create_redis_client
from news_platform.modules import models as platform_models  # noqa: F401
from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentGeography,
    ContentGeographyRelationship,
    ContentItem,
    ContentStatus,
    ContentType,
)
from news_platform.modules.editorial.api.router import router as editorial_router
from news_platform.modules.engagement.api.router import router as engagement_router
from news_platform.modules.engagement.application.service import (
    EngagementCounterService,
    EngagementIdempotencyConflictError,
)
from news_platform.modules.engagement.domain.models import (
    ContentEngagementCounter,
    EngagementMetric,
)
from news_platform.modules.feeds.api.router import router as feeds_router
from news_platform.modules.feeds.infrastructure.cache import (
    CACHE_EPOCH_KEY,
    invalidate_public_feed_cache,
)
from news_platform.modules.feeds.infrastructure.repository import FeedRepository
from news_platform.modules.geography.domain.models import GeographyNode, GeographyType
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.public_site.api.router import router as public_site_router
from news_platform.modules.taxonomy.domain.models import Category

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest_asyncio.fixture
async def database() -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        pytest.skip("POSTGRES_TEST_URL is required for PostgreSQL integration tests")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield engine, factory
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client = create_redis_client(os.getenv("REDIS_TEST_URL", "redis://localhost:6379/15"))
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip("REDIS_TEST_URL must point to a real Redis instance")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


async def seed_domain(session: AsyncSession) -> dict[str, Any]:
    texas = GeographyNode(
        type=GeographyType.STATE_OR_PROVINCE,
        name="Texas",
        slug="texas",
        country_code="US",
        metadata_={},
    )
    oklahoma = GeographyNode(
        type=GeographyType.STATE_OR_PROVINCE,
        name="Oklahoma",
        slug="oklahoma",
        country_code="US",
        metadata_={},
    )
    session.add_all([texas, oklahoma])
    await session.flush()
    austin = GeographyNode(
        type=GeographyType.CITY,
        name="Austin",
        slug="austin",
        country_code="US",
        parent_id=texas.id,
        metadata_={},
    )
    dallas = GeographyNode(
        type=GeographyType.CITY,
        name="Dallas",
        slug="dallas",
        country_code="US",
        parent_id=texas.id,
        metadata_={},
    )
    sports = Category(name="Sports", slug="sports", sort_order=0)
    music = Category(name="Music", slug="music", sort_order=1)
    session.add_all([austin, dallas, sports, music])
    await session.flush()
    portal = Portal(
        slug="texas",
        name="Texas Entertainment Daily",
        domain="texas.example",
        status=PortalStatus.ACTIVE,
        primary_geography_id=texas.id,
        default_language="en",
        supported_languages=["en", "es"],
        timezone="America/Chicago",
        branding={},
        category_settings={"enabled": ["sports", "music"]},
        ranking_settings={"trending": {"views": 2.0, "freshness_half_life_hours": 24}},
        ai_settings={},
        advertising_settings={},
        seo_settings={},
        feature_flags={},
    )
    session.add(portal)
    session.add(
        Portal(
            slug="oklahoma",
            name="Oklahoma Entertainment Daily",
            domain="oklahoma.example",
            status=PortalStatus.ACTIVE,
            primary_geography_id=oklahoma.id,
            default_language="en",
            supported_languages=["en"],
            timezone="America/Chicago",
            branding={},
            category_settings={"enabled": ["sports"]},
            ranking_settings={},
            ai_settings={},
            advertising_settings={},
            seo_settings={},
            feature_flags={},
        )
    )
    await session.flush()
    return {
        "texas": texas,
        "oklahoma": oklahoma,
        "austin": austin,
        "dallas": dallas,
        "sports": sports,
        "music": music,
    }


async def add_story(
    session: AsyncSession,
    domain: dict[str, Any],
    identity: int,
    *,
    published_at: datetime,
    geography: str = "austin",
    category: str = "sports",
    status: ContentStatus = ContentStatus.PUBLISHED,
    upstream_status: ContentStatus = ContentStatus.RECEIVED,
    language: str = "en",
    title: str | None = None,
) -> ContentItem:
    item = ContentItem(
        id=UUID(int=identity),
        slug=f"feed-story-{identity}",
        content_type=ContentType.ARTICLE,
        status=status,
        upstream_status=upstream_status,
        original_language=language,
        primary_language=language,
        title=title or f"Feed story {identity}",
        description=f"Description {identity}",
        body=f"Body {identity}",
        site_published_at=published_at,
        has_editorial_override=bool(title),
        metadata_={},
        seo={},
    )
    session.add(item)
    await session.flush()
    session.add_all(
        [
            ContentCategory(content_item_id=item.id, category_id=domain[category].id),
            ContentGeography(
                content_item_id=item.id,
                geography_id=domain[geography].id,
                relationship_type=ContentGeographyRelationship.PRIMARY,
                source="test",
            ),
        ]
    )
    await session.flush()
    return item


async def make_client(
    factory: async_sessionmaker[AsyncSession], redis_client: Redis
) -> httpx.AsyncClient:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.db_session_factory = factory
    app.state.redis = redis_client
    app.state.settings = SimpleNamespace(feed_cache_ttl_seconds=30)
    app.include_router(feeds_router)
    app.include_router(engagement_router)
    app.include_router(editorial_router)
    app.include_router(public_site_router)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_cursor_feeds_enforce_visibility_language_and_scopes(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]], redis_client: Redis
) -> None:
    _engine, factory = database
    tied = NOW - timedelta(hours=1)
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        await add_story(session, domain, 1, published_at=tied)
        await add_story(session, domain, 2, published_at=tied)
        await add_story(
            session, domain, 3, published_at=tied - timedelta(minutes=1), category="music"
        )
        await add_story(session, domain, 4, published_at=tied, geography="dallas")
        await add_story(session, domain, 5, published_at=tied, language="es")
        await add_story(session, domain, 6, published_at=tied, geography="oklahoma")
        await add_story(session, domain, 7, published_at=tied, status=ContentStatus.UNPUBLISHED)
        await add_story(
            session, domain, 8, published_at=tied, upstream_status=ContentStatus.RETRACTED
        )
        await add_story(session, domain, 9, published_at=tied, status=ContentStatus.SCHEDULED)
        await add_story(
            session, domain, 10, published_at=tied, upstream_status=ContentStatus.DELETED
        )

    async with await make_client(factory, redis_client) as client:
        assert (await client.get("/api/v1/portals/texas/feeds/latest")).status_code == 422
        first = await client.get("/api/v1/portals/texas/feeds/latest?language=en&limit=2")
        assert first.status_code == 200
        assert [item["id"] for item in first.json()["items"]] == [
            str(UUID(int=4)),
            str(UUID(int=2)),
        ]
        cursor = first.json()["next_cursor"]
        second = await client.get(
            "/api/v1/portals/texas/feeds/latest",
            params={"language": "en", "limit": 2, "cursor": cursor},
        )
        assert [item["id"] for item in second.json()["items"]] == [
            str(UUID(int=1)),
            str(UUID(int=3)),
        ]
        assert second.json()["next_cursor"] is None
        assert (
            await client.get(
                "/api/v1/portals/texas/feeds/home",
                params={"language": "en", "limit": 2, "cursor": cursor},
            )
        ).status_code == 400

        home = await client.get("/api/v1/portals/texas/feeds/home?language=en&limit=10")
        assert [item["id"] for item in home.json()["items"]] == [
            str(UUID(int=4)),
            str(UUID(int=2)),
            str(UUID(int=1)),
            str(UUID(int=3)),
        ]
        category = await client.get(
            "/api/v1/portals/texas/feeds/categories/music?language=en&limit=10"
        )
        assert [item["id"] for item in category.json()["items"]] == [str(UUID(int=3))]
        local = await client.get("/api/v1/portals/texas/feeds/local/austin?language=en&limit=10")
        assert [item["id"] for item in local.json()["items"]] == [
            str(UUID(int=2)),
            str(UUID(int=1)),
            str(UUID(int=3)),
        ]
        spanish = await client.get("/api/v1/portals/texas/feeds/latest?language=es&limit=10")
        assert [item["id"] for item in spanish.json()["items"]] == [str(UUID(int=5))]
        neighboring = await client.get("/api/v1/portals/oklahoma/feeds/latest?language=en&limit=10")
        assert [item["id"] for item in neighboring.json()["items"]] == [str(UUID(int=6))]
        assert (
            await client.get("/api/v1/portals/texas/feeds/local/oklahoma?language=en&limit=10")
        ).status_code == 404
        assert (
            await client.get("/api/v1/portals/texas/feeds/latest?language=en&limit=10&cursor=bad")
        ).status_code == 400
        assert (
            await client.get("/api/v1/portals/texas/feeds/latest?language=fr&limit=10")
        ).status_code == 404


async def test_engagement_is_atomic_idempotent_and_drives_deterministic_trending(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]], redis_client: Redis
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        await add_story(session, domain, 11, published_at=NOW - timedelta(hours=3))
        await add_story(session, domain, 12, published_at=NOW - timedelta(hours=1))
        await add_story(session, domain, 13, published_at=NOW - timedelta(hours=1))

    async with await make_client(factory, redis_client) as client:
        update = {"content_id": str(UUID(int=11)), "metric": "views", "amount": 100}
        applied = await client.post(
            "/internal/v1/engagement/counters",
            headers={"Idempotency-Key": "view-batch-11"},
            json=update,
        )
        replay = await client.post(
            "/internal/v1/engagement/counters",
            headers={"Idempotency-Key": "view-batch-11"},
            json=update,
        )
        conflict = await client.post(
            "/internal/v1/engagement/counters",
            headers={"Idempotency-Key": "view-batch-11"},
            json={**update, "amount": 2},
        )
        assert applied.json()["applied"] is True and applied.json()["value"] == 100
        assert replay.json()["applied"] is False and replay.json()["value"] == 100
        assert conflict.status_code == 409

        trending = await client.get("/api/v1/portals/texas/feeds/trending?language=en&limit=2")
        assert [item["id"] for item in trending.json()["items"]] == [
            str(UUID(int=11)),
            str(UUID(int=13)),
        ]
        next_page = await client.get(
            "/api/v1/portals/texas/feeds/trending",
            params={
                "language": "en",
                "limit": 2,
                "cursor": trending.json()["next_cursor"],
            },
        )
        assert [item["id"] for item in next_page.json()["items"]] == [str(UUID(int=12))]
        homepage = await client.get("/api/v1/portals/texas/home")
        assert [item["id"] for item in homepage.json()["trending"]][:1] == [str(UUID(int=11))]

    async def increment(key: str) -> bool:
        async with factory() as session, session.begin():
            receipt = await EngagementCounterService(session).increment(
                content_id=UUID(int=12),
                metric=EngagementMetric.CLICKS,
                amount=1,
                idempotency_key=key,
            )
            return receipt.applied

    assert all(await asyncio.gather(increment("click-1"), increment("click-2")))
    async with factory() as session:
        counter = await session.get(ContentEngagementCounter, UUID(int=12))
        assert counter is not None and counter.clicks == 2


async def test_real_redis_cache_has_ttl_and_editorial_invalidation(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]], redis_client: Redis
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        story = await add_story(session, domain, 21, published_at=NOW - timedelta(minutes=5))

    async with await make_client(factory, redis_client) as client:
        url = "/api/v1/portals/texas/feeds/latest?language=en&limit=10"
        assert [item["id"] for item in (await client.get(url)).json()["items"]] == [str(story.id)]
        keys = [key async for key in redis_client.scan_iter(match="public-feeds:*")]
        response_keys = [key for key in keys if key != CACHE_EPOCH_KEY]
        assert len(response_keys) == 1
        assert 0 < await redis_client.ttl(response_keys[0]) <= 30

        async with factory() as session, session.begin():
            current = await session.get(ContentItem, story.id)
            assert current is not None
            current.title = "Fresh title after a missed cache invalidation"
        refreshed = await client.get(url)
        assert refreshed.json()["items"][0]["title"] == (
            "Fresh title after a missed cache invalidation"
        )

        unpublish = await client.post(
            f"/api/v1/admin/content/{story.id}/unpublish",
            headers={"X-Editorial-Actor": "editor:phase-five"},
            json={"reason": "cache invalidation regression"},
        )
        assert unpublish.status_code == 200
        assert int(await redis_client.get(CACHE_EPOCH_KEY) or 0) == 1
        assert (await client.get(url)).json()["items"] == []


async def test_cache_epoch_changes_and_empty_feed_is_cacheable(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]], redis_client: Redis
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        await seed_domain(session)
    async with await make_client(factory, redis_client) as client:
        response = await client.get("/api/v1/portals/texas/feeds/latest?language=en&limit=10")
        assert response.status_code == 200
        assert response.json()["items"] == [] and response.json()["next_cursor"] is None
    await invalidate_public_feed_cache(redis_client)
    assert int(await redis_client.get(CACHE_EPOCH_KEY) or 0) == 1


async def test_trending_cursor_is_rejected_after_ranking_generation_changes(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]], redis_client: Redis
) -> None:
    _engine, factory = database
    published_at = NOW - timedelta(hours=1)
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        for identity in range(31, 35):
            await add_story(session, domain, identity, published_at=published_at)
        await EngagementCounterService(session).increment(
            content_id=UUID(int=31),
            metric=EngagementMetric.VIEWS,
            amount=100,
            idempotency_key="trending-cursor-initial-rank",
        )

    async with await make_client(factory, redis_client) as client:
        url = "/api/v1/portals/texas/feeds/trending"
        first = await client.get(url, params={"language": "en", "limit": 2})
        assert first.status_code == 200
        first_ids = [item["id"] for item in first.json()["items"]]
        assert first_ids == [str(UUID(int=31)), str(UUID(int=34))]
        old_cursor = first.json()["next_cursor"]
        assert old_cursor is not None

        changed = await client.post(
            "/internal/v1/engagement/counters",
            headers={"Idempotency-Key": "trending-cursor-new-rank"},
            json={"content_id": str(UUID(int=32)), "metric": "views", "amount": 200},
        )
        assert changed.status_code == 200 and changed.json()["applied"] is True

        old_second = await client.get(
            url,
            params={"language": "en", "limit": 2, "cursor": old_cursor},
        )
        assert old_second.status_code == 400
        assert old_second.json()["detail"]["code"] == "INVALID_FEED_CURSOR"

        traversed: list[str] = []
        cursor: str | None = None
        while True:
            params = {"language": "en", "limit": 2}
            if cursor is not None:
                params["cursor"] = cursor
            page = await client.get(url, params=params)
            assert page.status_code == 200
            traversed.extend(item["id"] for item in page.json()["items"])
            cursor = page.json()["next_cursor"]
            if cursor is None:
                break
        assert traversed == [
            str(UUID(int=32)),
            str(UUID(int=31)),
            str(UUID(int=34)),
            str(UUID(int=33)),
        ]
        assert len(traversed) == len(set(traversed)) == 4


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", ContentStatus.UNPUBLISHED),
        ("upstream_status", ContentStatus.RETRACTED),
        ("upstream_status", ContentStatus.DELETED),
    ],
)
async def test_real_redis_stale_visibility_write_stays_in_old_generation(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: ContentStatus,
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        story = await add_story(session, domain, 41, published_at=NOW - timedelta(minutes=5))

    query_finished = asyncio.Event()
    release_old_request = asyncio.Event()
    original = FeedRepository.chronological

    async def delayed_chronological(self: FeedRepository, *args: Any, **kwargs: Any) -> Any:
        result = await original(self, *args, **kwargs)
        query_finished.set()
        await release_old_request.wait()
        return result

    monkeypatch.setattr(FeedRepository, "chronological", delayed_chronological)
    url = "/api/v1/portals/texas/feeds/latest?language=en&limit=10"
    async with await make_client(factory, redis_client) as client:
        old_request = asyncio.create_task(client.get(url))
        await asyncio.wait_for(query_finished.wait(), timeout=5)
        async with factory() as session, session.begin():
            current = await session.get(ContentItem, story.id)
            assert current is not None
            setattr(current, field, value)
        await invalidate_public_feed_cache(redis_client)
        assert await redis_client.get(CACHE_EPOCH_KEY) == "1"
        release_old_request.set()
        stale_response = await old_request
        assert [item["id"] for item in stale_response.json()["items"]] == [str(story.id)]

        old_keys = [key async for key in redis_client.scan_iter(match="public-feeds:0:*")]
        assert len(old_keys) == 1
        assert [key async for key in redis_client.scan_iter(match="public-feeds:1:*")] == []

        current_response = await client.get(url)
        assert current_response.status_code == 200
        assert current_response.json()["items"] == []


async def test_real_redis_stale_trending_write_cannot_cross_engagement_generation(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        for identity in range(51, 54):
            await add_story(
                session,
                domain,
                identity,
                published_at=NOW - timedelta(hours=1),
            )

    query_finished = asyncio.Event()
    release_old_request = asyncio.Event()
    original = FeedRepository.trending

    async def delayed_trending(self: FeedRepository, *args: Any, **kwargs: Any) -> Any:
        result = await original(self, *args, **kwargs)
        query_finished.set()
        await release_old_request.wait()
        return result

    monkeypatch.setattr(FeedRepository, "trending", delayed_trending)
    url = "/api/v1/portals/texas/feeds/trending?language=en&limit=3"
    async with await make_client(factory, redis_client) as client:
        old_request = asyncio.create_task(client.get(url))
        await asyncio.wait_for(query_finished.wait(), timeout=5)
        changed = await client.post(
            "/internal/v1/engagement/counters",
            headers={"Idempotency-Key": "trending-cache-race"},
            json={"content_id": str(UUID(int=51)), "metric": "views", "amount": 100},
        )
        assert changed.status_code == 200 and changed.json()["applied"] is True
        assert await redis_client.get(CACHE_EPOCH_KEY) == "1"
        release_old_request.set()
        stale_response = await old_request
        assert [item["id"] for item in stale_response.json()["items"]] == [
            str(UUID(int=53)),
            str(UUID(int=52)),
            str(UUID(int=51)),
        ]
        assert len([key async for key in redis_client.scan_iter(match="public-feeds:0:*")]) == 1

        current_response = await client.get(url)
        assert [item["id"] for item in current_response.json()["items"]] == [
            str(UUID(int=51)),
            str(UUID(int=53)),
            str(UUID(int=52)),
        ]


async def test_idempotency_request_identity_and_postgresql_concurrency(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]], redis_client: Redis
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        await add_story(session, domain, 61, published_at=NOW - timedelta(hours=1))
        await add_story(session, domain, 62, published_at=NOW - timedelta(hours=1))

    async def increment(
        key: str,
        *,
        content_id: UUID | None = None,
        metric: EngagementMetric = EngagementMetric.VIEWS,
        amount: int = 1,
    ) -> Any:
        async with factory() as session, session.begin():
            return await EngagementCounterService(session).increment(
                content_id=content_id or UUID(int=61),
                metric=metric,
                amount=amount,
                idempotency_key=key,
            )

    first = await increment("same-request", amount=3)
    replay = await increment("same-request", amount=3)
    assert first.applied is True and replay.applied is False

    await increment("different-content")
    with pytest.raises(EngagementIdempotencyConflictError):
        await increment("different-content", content_id=UUID(int=62))

    await increment("different-metric")
    with pytest.raises(EngagementIdempotencyConflictError):
        await increment("different-metric", metric=EngagementMetric.CLICKS)

    await increment("different-amount")
    with pytest.raises(EngagementIdempotencyConflictError):
        await increment("different-amount", amount=2)

    identical = await asyncio.gather(
        increment("concurrent-identical", amount=5),
        increment("concurrent-identical", amount=5),
    )
    assert sorted(receipt.applied for receipt in identical) == [False, True]

    conflicting = await asyncio.gather(
        increment("concurrent-conflict", content_id=UUID(int=61), amount=7),
        increment(
            "concurrent-conflict",
            content_id=UUID(int=62),
            metric=EngagementMetric.CLICKS,
            amount=11,
        ),
        return_exceptions=True,
    )
    receipts = [result for result in conflicting if not isinstance(result, BaseException)]
    errors = [result for result in conflicting if isinstance(result, BaseException)]
    assert len(receipts) == 1 and receipts[0].applied is True
    assert len(errors) == 1 and isinstance(errors[0], EngagementIdempotencyConflictError)

    async with factory() as session:
        first_counter = await session.get(ContentEngagementCounter, UUID(int=61))
        second_counter = await session.get(ContentEngagementCounter, UUID(int=62))
        assert first_counter is not None
        assert first_counter.views in {18, 11}
        if first_counter.views == 18:
            assert second_counter is None or second_counter.clicks == 0
        else:
            assert second_counter is not None and second_counter.clicks == 11
