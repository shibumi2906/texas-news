from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from news_platform.infrastructure.database import Base
from news_platform.modules import models as platform_models  # noqa: F401
from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentGeography,
    ContentGeographyRelationship,
    ContentItem,
    ContentStatus,
    ContentType,
    Source,
)
from news_platform.modules.geography.domain.models import GeographyNode, GeographyType
from news_platform.modules.media.domain.models import MediaAsset, MediaStatus, MediaType
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.public_site.api.router import router
from news_platform.modules.public_site.application.service import PublicSiteService
from news_platform.modules.taxonomy.domain.models import Category

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def database() -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[Any]]]:
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


async def seed_public_domain(session: AsyncSession) -> dict[str, Any]:
    texas = GeographyNode(
        type=GeographyType.STATE_OR_PROVINCE,
        name="Texas",
        slug="texas",
        country_code="US",
        timezone="America/Chicago",
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
        timezone="America/Chicago",
        metadata_={},
    )
    session.add(austin)
    sports = Category(name="Sports", slug="sports", sort_order=0)
    music = Category(name="Music", slug="music", sort_order=1)
    source = Source(name="Texas Wire", slug="texas-wire", canonical_url="https://wire.test")
    session.add_all([sports, music, source])
    await session.flush()
    portal = Portal(
        slug="texas",
        name="Texas Entertainment Daily",
        domain="texas.example",
        status=PortalStatus.ACTIVE,
        primary_geography_id=texas.id,
        default_language="en",
        supported_languages=["en"],
        timezone="America/Chicago",
        branding={"tagline": "The Texas entertainment beat"},
        category_settings={"enabled": ["sports", "music"]},
        ranking_settings={},
        ai_settings={},
        advertising_settings={"enabled": False},
        seo_settings={"canonical_base_url": "https://news.texas.example"},
        feature_flags={},
    )
    session.add(portal)
    await session.flush()
    return {
        "portal": portal,
        "texas": texas,
        "austin": austin,
        "oklahoma": oklahoma,
        "sports": sports,
        "music": music,
        "source": source,
    }


async def add_story(
    session: AsyncSession,
    domain: dict[str, Any],
    *,
    identity: int,
    title: str,
    status: ContentStatus = ContentStatus.PUBLISHED,
    upstream_status: ContentStatus = ContentStatus.RECEIVED,
    geography: str = "texas",
    category: str = "sports",
    published_at: datetime | None = None,
    content_type: ContentType = ContentType.ARTICLE,
) -> ContentItem:
    content = ContentItem(
        id=UUID(int=identity),
        slug=f"story-{identity}",
        content_type=content_type,
        status=status,
        upstream_status=upstream_status,
        source_id=domain["source"].id,
        original_url=f"https://wire.test/story-{identity}",
        original_language="en",
        primary_language="en",
        title=title,
        subtitle=f"Subtitle for {title}",
        description=f"Description for {title}",
        body=f"Body for {title}\n\nSecond paragraph.",
        site_published_at=published_at or NOW - timedelta(hours=1),
        has_editorial_override=title.startswith("Editorial"),
        metadata_={},
        seo={"description": f"SEO for {title}"},
    )
    session.add(content)
    await session.flush()
    session.add_all(
        [
            ContentCategory(content_item_id=content.id, category_id=domain[category].id),
            ContentGeography(
                content_item_id=content.id,
                geography_id=domain[geography].id,
                relationship_type=ContentGeographyRelationship.PRIMARY,
                source="test",
            ),
        ]
    )
    if identity == 1:
        session.add(
            MediaAsset(
                content_item_id=content.id,
                type=MediaType.IMAGE,
                source_url="https://images.test/hero.jpg",
                width=1600,
                height=900,
                attribution="Texas Wire",
                metadata_={},
                status=MediaStatus.READY,
            )
        )
    await session.flush()
    return content


async def test_public_visibility_portal_scope_override_and_deterministic_order(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_public_domain(session)
        first = await add_story(session, domain, identity=1, title="Editorial headline")
        second = await add_story(session, domain, identity=2, title="Second headline")
        await add_story(
            session,
            domain,
            identity=3,
            title="Future publish",
            published_at=NOW + timedelta(hours=1),
        )
        await add_story(
            session, domain, identity=4, title="Scheduled", status=ContentStatus.SCHEDULED
        )
        await add_story(
            session, domain, identity=5, title="Unpublished", status=ContentStatus.UNPUBLISHED
        )
        await add_story(
            session, domain, identity=6, title="Archived", status=ContentStatus.ARCHIVED
        )
        await add_story(
            session,
            domain,
            identity=7,
            title="Retracted upstream",
            upstream_status=ContentStatus.RETRACTED,
        )
        await add_story(
            session,
            domain,
            identity=8,
            title="Deleted upstream",
            upstream_status=ContentStatus.DELETED,
        )
        await add_story(session, domain, identity=9, title="Other portal", geography="oklahoma")

    async with factory() as session:
        homepage = await PublicSiteService(session, now=NOW).homepage("texas")
        assert homepage.hero is not None
        assert homepage.hero.id == first.id
        assert homepage.hero.title == "Editorial headline"
        assert homepage.hero.media[0].url == "https://images.test/hero.jpg"
        assert homepage.hero.canonical_url == "https://news.texas.example/story/story-1"
        assert [homepage.hero.id, *(item.id for item in homepage.trending)] == [
            first.id,
            second.id,
        ]
        sports = next(
            section for section in homepage.category_sections if section.category.slug == "sports"
        )
        assert [item.id for item in sports.items] == [first.id, second.id]


async def test_category_story_and_descendant_geography_api(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_public_domain(session)
        austin_story = await add_story(
            session,
            domain,
            identity=11,
            title="Austin live music",
            geography="austin",
            category="music",
            published_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        await add_story(
            session,
            domain,
            identity=12,
            title="Related music",
            category="music",
            published_at=datetime.now(UTC) - timedelta(minutes=20),
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.db_session_factory = factory
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        category = await client.get("/api/v1/portals/texas/categories/music?limit=1")
        assert category.status_code == 200
        assert category.json()["total"] == 2
        assert category.json()["items"][0]["id"] == str(austin_story.id)

        story = await client.get("/api/v1/portals/texas/stories/story-11")
        assert story.status_code == 200
        payload = story.json()
        assert payload["body"].startswith("Body for Austin live music")
        assert payload["source"]["name"] == "Texas Wire"
        assert payload["geography"][0]["slug"] == "austin"
        assert [item["slug"] for item in payload["related"]] == ["story-12"]

        assert (await client.get("/api/v1/portals/texas/stories/missing")).status_code == 404
        assert (await client.get("/api/v1/portals/texas/categories/not-enabled")).status_code == 404


async def test_canonical_urls_follow_each_portal_configuration(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_public_domain(session)
        texas_story = await add_story(session, domain, identity=21, title="Configured Texas URL")
        oklahoma_story = await add_story(
            session,
            domain,
            identity=22,
            title="Neighboring portal URL",
            geography="oklahoma",
        )
        session.add(
            Portal(
                slug="oklahoma",
                name="Oklahoma Entertainment Daily",
                domain="oklahoma.example",
                status=PortalStatus.ACTIVE,
                primary_geography_id=domain["oklahoma"].id,
                default_language="en",
                supported_languages=["en"],
                timezone="America/Chicago",
                branding={},
                category_settings={"enabled": ["sports"]},
                ranking_settings={},
                ai_settings={},
                advertising_settings={"enabled": False},
                seo_settings={},
                feature_flags={},
            )
        )

    async with factory() as session:
        service = PublicSiteService(session, now=NOW)
        texas = await service.story("texas", texas_story.slug)
        oklahoma = await service.story("oklahoma", oklahoma_story.slug)
        assert texas.canonical_url == "https://news.texas.example/story/story-21"
        assert oklahoma.canonical_url == "https://oklahoma.example/story/story-22"
        assert texas.portal.slug == "texas"
        assert oklahoma.portal.slug == "oklahoma"
