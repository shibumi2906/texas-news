from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from news_platform.infrastructure.database import Base
from news_platform.modules import models as phase_1_models  # noqa: F401
from news_platform.modules.content.application.service import ContentService, SourceService
from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentItem,
    ContentStatus,
    ContentTopic,
    ContentType,
    ContentVersion,
)
from news_platform.modules.content.domain.schemas import (
    ContentEntityAssociation,
    ContentGeographyAssociation,
    ContentItemCreate,
    ContentVersionCreate,
    SourceCreate,
)
from news_platform.modules.content.infrastructure.repository import (
    ContentRepository,
    SourceRepository,
)
from news_platform.modules.entities.application.service import EntityService
from news_platform.modules.entities.domain.models import EntityType
from news_platform.modules.entities.domain.schemas import EntityCreate
from news_platform.modules.entities.infrastructure.repository import EntityRepository
from news_platform.modules.geography.application.service import GeographyService
from news_platform.modules.geography.domain.models import GeographyType
from news_platform.modules.geography.domain.schemas import GeographyNodeCreate
from news_platform.modules.geography.infrastructure.repository import GeographyRepository
from news_platform.modules.media.domain.models import MediaAsset, MediaStatus, MediaType
from news_platform.modules.portals.application.service import PortalService
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.portals.domain.schemas import PortalCreate
from news_platform.modules.portals.infrastructure.repository import PortalRepository
from news_platform.modules.taxonomy.application.service import TaxonomyService
from news_platform.modules.taxonomy.domain.models import Category, Topic
from news_platform.modules.taxonomy.domain.schemas import CategoryCreate, TopicCreate
from news_platform.modules.taxonomy.infrastructure.repository import TaxonomyRepository
from news_platform.seed import INITIAL_CATEGORIES, seed_texas

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    database_url = os.getenv("POSTGRES_TEST_URL")
    if not database_url:
        pytest.skip("POSTGRES_TEST_URL is required for PostgreSQL integration tests")

    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as test_session:
        yield test_session

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def content_service(session: AsyncSession) -> ContentService:
    return ContentService(
        ContentRepository(session),
        TaxonomyRepository(session),
        EntityRepository(session),
        GeographyRepository(session),
    )


async def create_content(session: AsyncSession, title: str = "Texas story") -> ContentItem:
    return await content_service(session).create(
        ContentItemCreate(
            external_id="site-external-1",
            content_type=ContentType.ARTICLE,
            status=ContentStatus.RECEIVED,
            original_url="https://example.com/story",
            original_language="en",
            primary_language="en",
            title=title,
        )
    )


async def test_portal_creation_and_unique_slug_domain(session: AsyncSession) -> None:
    geography = await GeographyService(GeographyRepository(session)).create(
        GeographyNodeCreate(type=GeographyType.STATE_OR_PROVINCE, name="Texas", slug="texas")
    )
    service = PortalService(PortalRepository(session))
    portal = await service.create(
        PortalCreate(
            slug="texas",
            name="Texas Entertainment Portal",
            domain="texas.example.com",
            status=PortalStatus.ACTIVE,
            primary_geography_id=geography.id,
            timezone="America/Chicago",
        )
    )
    await session.commit()

    assert (await service.get_by_slug("texas")) == portal
    session.add(
        Portal(
            slug="texas",
            name="Duplicate",
            domain="other.example.com",
            status=PortalStatus.DRAFT,
            default_language="en",
            supported_languages=["en"],
            timezone="UTC",
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    session.add(
        Portal(
            slug="texas-two",
            name="Duplicate domain",
            domain="texas.example.com",
            status=PortalStatus.DRAFT,
            default_language="en",
            supported_languages=["en"],
            timezone="UTC",
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_geography_hierarchy_and_retrieval(session: AsyncSession) -> None:
    service = GeographyService(GeographyRepository(session))
    world = await service.create(
        GeographyNodeCreate(type=GeographyType.WORLD, name="World", slug="world")
    )
    country = await service.create(
        GeographyNodeCreate(
            type=GeographyType.COUNTRY,
            name="United States",
            slug="united-states",
            country_code="us",
            parent_id=world.id,
        )
    )

    retrieved = await service.get_by_slug("united-states")
    assert retrieved is not None
    assert retrieved.parent_id == world.id
    assert retrieved.country_code == "US"
    assert (await service.get(country.id)) == country


async def test_content_source_creation_retrieval_and_state_persistence(
    session: AsyncSession,
) -> None:
    source = await SourceService(SourceRepository(session)).create(
        SourceCreate(
            external_id="source-1",
            name="Example Source",
            slug="example-source",
            canonical_url="https://example.com",
        )
    )
    service = content_service(session)
    content = await service.create(
        ContentItemCreate(
            content_type=ContentType.VIDEO,
            status=ContentStatus.READY,
            source_id=source.id,
            original_language="en",
            primary_language="en",
            title="Video story",
            first_seen_at=datetime.now(UTC),
        )
    )
    await session.commit()

    retrieved = await service.get(content.id)
    assert retrieved is not None
    assert retrieved.content_type is ContentType.VIDEO
    assert retrieved.status is ContentStatus.READY
    assert retrieved.source_id == source.id


async def test_content_versions_are_independent_and_unique_per_item(
    session: AsyncSession,
) -> None:
    service = content_service(session)
    content = await create_content(session, "Current title")
    first = await service.create_version(
        ContentVersionCreate(
            content_item_id=content.id,
            version_number=1,
            title="First title",
            body="First body",
        )
    )
    second = await service.create_version(
        ContentVersionCreate(
            content_item_id=content.id,
            version_number=2,
            title="Second title",
            body="Second body",
        )
    )
    content.title = "Changed current title"
    await session.commit()

    assert first.title == "First title"
    assert second.title == "Second title"
    session.add(
        ContentVersion(
            content_item_id=content.id,
            version_number=2,
            title="Duplicate version",
            metadata_={},
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_content_relationships_and_duplicate_associations(session: AsyncSession) -> None:
    taxonomy = TaxonomyService(TaxonomyRepository(session))
    category = await taxonomy.create_category(CategoryCreate(name="Sports", slug="sports"))
    topic = await taxonomy.create_topic(TopicCreate(name="NBA", slug="nba"))
    entity = await EntityService(EntityRepository(session)).create(
        EntityCreate(
            type=EntityType.SPORTS_TEAM,
            canonical_name="Dallas Mavericks",
            slug="dallas-mavericks",
        )
    )
    geography = await GeographyService(GeographyRepository(session)).create(
        GeographyNodeCreate(type=GeographyType.CITY, name="Dallas", slug="dallas")
    )
    service = content_service(session)
    content = await create_content(session)

    first_category = await service.associate_category(content.id, category.id)
    second_category = await service.associate_category(content.id, category.id)
    await service.associate_topic(content.id, topic.id)
    await service.associate_topic(content.id, topic.id)
    await service.associate_entity(
        content.id,
        ContentEntityAssociation(entity_id=entity.id, confidence=0.9, source="editorial"),
    )
    await service.associate_entity(
        content.id,
        ContentEntityAssociation(entity_id=entity.id, confidence=0.4, source="duplicate"),
    )
    await service.associate_geography(
        content.id,
        ContentGeographyAssociation(
            geography_id=geography.id,
            relationship_type="primary",
            confidence=1.0,
            source="editorial",
        ),
    )
    await service.associate_geography(
        content.id,
        ContentGeographyAssociation(
            geography_id=geography.id,
            relationship_type="primary",
            confidence=0.5,
            source="duplicate",
        ),
    )
    await session.commit()

    assert first_category is second_category
    for model in (ContentCategory, ContentTopic, ContentEntity, ContentGeography):
        count = await session.scalar(select(func.count()).select_from(model))
        assert count == 1


async def test_media_asset_persistence(session: AsyncSession) -> None:
    content = await create_content(session)
    media = MediaAsset(
        content_item_id=content.id,
        type=MediaType.IMAGE,
        source_url="https://example.com/image.jpg",
        mime_type="image/jpeg",
        width=1200,
        height=800,
        status=MediaStatus.READY,
        metadata_={},
    )
    session.add(media)
    await session.commit()

    stored = await session.get(MediaAsset, media.id)
    assert stored is not None
    assert stored.type is MediaType.IMAGE


async def test_texas_seed_is_complete_and_idempotent(session: AsyncSession) -> None:
    first = await seed_texas(session)
    second = await seed_texas(session)

    assert first.portal_created is True
    assert first.geographies_created == 3
    assert first.categories_created == len(INITIAL_CATEGORIES)
    assert second.portal_created is False
    assert second.geographies_created == 0
    assert second.categories_created == 0
    assert await session.scalar(select(func.count()).select_from(Portal)) == 1
    assert await session.scalar(select(func.count()).select_from(Category)) == len(
        INITIAL_CATEGORIES
    )
    assert await session.scalar(select(func.count()).select_from(Topic)) == 0

    texas = await GeographyRepository(session).get_by_slug("texas")
    portal = await PortalRepository(session).get_by_slug("texas")
    assert texas is not None
    assert portal is not None
    assert portal.primary_geography_id == texas.id
    assert portal.supported_languages == ["en"]
