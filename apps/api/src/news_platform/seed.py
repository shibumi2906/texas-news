from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.core.config import get_settings
from news_platform.infrastructure.database import create_db_engine, create_session_factory
from news_platform.modules import models as _domain_models  # noqa: F401
from news_platform.modules.content.domain.models import (
    ContentGeographyRelationship,
    ContentItem,
    ContentStatus,
    ContentType,
    Source,
)
from news_platform.modules.content.infrastructure.repository import ContentRepository
from news_platform.modules.geography.domain.models import GeographyNode, GeographyType
from news_platform.modules.geography.infrastructure.repository import GeographyRepository
from news_platform.modules.localization.domain.models import Translation, TranslationStatus
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.portals.infrastructure.repository import PortalRepository
from news_platform.modules.taxonomy.domain.models import Category, TaxonomyStatus
from news_platform.modules.taxonomy.infrastructure.repository import TaxonomyRepository

INITIAL_CATEGORIES = (
    ("Sports", "sports"),
    ("Movies & TV", "movies-tv"),
    ("Celebrity", "celebrity"),
    ("Music", "music"),
    ("Gaming", "gaming"),
    ("Viral", "viral"),
    ("Travel", "travel"),
    ("Food", "food"),
    ("Lifestyle", "lifestyle"),
    ("Events", "events"),
    ("Local", "local"),
)


@dataclass(frozen=True)
class SeedResult:
    portal_created: bool
    geographies_created: int
    categories_created: int
    sample_content_created: bool
    sample_translation_created: bool


async def seed_texas(session: AsyncSession) -> SeedResult:
    geography_repository = GeographyRepository(session)
    portal_repository = PortalRepository(session)
    taxonomy_repository = TaxonomyRepository(session)
    geographies_created = 0
    categories_created = 0

    world = await geography_repository.get_by_slug("world")
    if world is None:
        world = await geography_repository.add(
            GeographyNode(
                type=GeographyType.WORLD,
                name="World",
                slug="world",
                metadata_={},
            )
        )
        geographies_created += 1

    united_states = await geography_repository.get_by_slug("united-states")
    if united_states is None:
        united_states = await geography_repository.add(
            GeographyNode(
                type=GeographyType.COUNTRY,
                name="United States",
                slug="united-states",
                country_code="US",
                parent_id=world.id,
                metadata_={},
            )
        )
        geographies_created += 1

    texas = await geography_repository.get_by_slug("texas")
    if texas is None:
        texas = await geography_repository.add(
            GeographyNode(
                type=GeographyType.STATE_OR_PROVINCE,
                name="Texas",
                slug="texas",
                country_code="US",
                parent_id=united_states.id,
                timezone="America/Chicago",
                metadata_={},
            )
        )
        geographies_created += 1

    category_slugs: list[str] = []
    for sort_order, (name, slug) in enumerate(INITIAL_CATEGORIES):
        category_slugs.append(slug)
        if await taxonomy_repository.get_category_by_slug(slug) is None:
            await taxonomy_repository.add_category(
                Category(
                    name=name,
                    slug=slug,
                    status=TaxonomyStatus.ACTIVE,
                    sort_order=sort_order,
                )
            )
            categories_created += 1

    portal = await portal_repository.get_by_slug("texas")
    portal_created = portal is None
    if portal is None:
        feature_flags: dict[str, Any] = {
            "community": True,
            "ai_chat": True,
            "ai_search": True,
            "recommendations": True,
            "personalization": True,
            "shorts": False,
            "advertising": False,
            "notifications": False,
            "multilingual": True,
        }
        portal = await portal_repository.add(
            Portal(
                slug="texas",
                name="Texas Entertainment Portal",
                domain="texas.localhost",
                status=PortalStatus.ACTIVE,
                primary_geography_id=texas.id,
                default_language="en",
                supported_languages=["en", "es"],
                timezone="America/Chicago",
                branding={},
                category_settings={"enabled": category_slugs},
                ranking_settings={},
                ai_settings={},
                advertising_settings={"enabled": False},
                seo_settings={},
                feature_flags=feature_flags,
            )
        )
    else:
        portal.supported_languages = list(dict.fromkeys([*portal.supported_languages, "en", "es"]))
        portal.feature_flags = {**portal.feature_flags, "multilingual": True}

    # Keep one small, idempotent bilingual story in the development seed so every
    # Phase 12 public surface can be exercised without simulating the Integrator.
    sample_source = await session.scalar(select(Source).where(Source.slug == "texas-demo"))
    if sample_source is None:
        sample_source = Source(
            external_id="seed:texas-demo",
            name="Texas Demo Desk",
            slug="texas-demo",
            canonical_url="https://example.com/texas-demo",
            metadata_={"seed": True},
        )
        session.add(sample_source)
        await session.flush()

    sample_story = await session.scalar(
        select(ContentItem).where(ContentItem.slug == "austin-summer-music-series")
    )
    sample_content_created = sample_story is None
    if sample_story is None:
        published_at = datetime(2026, 6, 1, 15, 0, tzinfo=UTC)
        sample_story = ContentItem(
            external_id="seed:texas:austin-summer-music-series",
            slug="austin-summer-music-series",
            content_type=ContentType.ARTICLE,
            status=ContentStatus.PUBLISHED,
            upstream_status=ContentStatus.PUBLISHED,
            source_id=sample_source.id,
            original_url="https://example.com/texas-demo/austin-summer-music-series",
            original_language="en",
            primary_language="en",
            title="Austin summer music series returns downtown",
            subtitle="Free concerts bring Texas artists to the city center",
            description="Austin's summer music series returns with a new lineup of Texas artists.",
            body="The downtown concert series returns this summer with free weekly performances.",
            publication_time=published_at,
            original_publication_time=published_at,
            site_published_at=published_at,
            author="Texas Demo Desk",
            metadata_={"seed": True},
            seo={},
        )
        session.add(sample_story)
        await session.flush()

    content_repository = ContentRepository(session)
    music = await taxonomy_repository.get_category_by_slug("music")
    assert music is not None
    await content_repository.associate_category(sample_story.id, music.id)
    await content_repository.associate_geography(
        sample_story.id,
        texas.id,
        ContentGeographyRelationship.PRIMARY,
        1.0,
        "seed",
    )

    sample_translation = await session.scalar(
        select(Translation).where(
            Translation.portal_id == portal.id,
            Translation.content_item_id == sample_story.id,
            Translation.language == "es",
        )
    )
    sample_translation_created = sample_translation is None
    if sample_translation is None:
        session.add(
            Translation(
                portal_id=portal.id,
                content_item_id=sample_story.id,
                language="es",
                title="La serie musical de verano de Austin vuelve al centro",
                subtitle="Conciertos gratuitos llevan artistas de Texas al centro de la ciudad",
                description="La serie musical de verano de Austin regresa con artistas de Texas.",
                body="La serie vuelve este verano con conciertos gratuitos semanales.",
                translation_source="editorial-seed",
                status=TranslationStatus.EDITORIAL,
                source_updated_at=sample_story.updated_at,
            )
        )

    await session.commit()
    return SeedResult(
        portal_created=portal_created,
        geographies_created=geographies_created,
        categories_created=categories_created,
        sample_content_created=sample_content_created,
        sample_translation_created=sample_translation_created,
    )


async def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            result = await seed_texas(session)
            print(
                "Texas seed complete: "
                f"portal_created={result.portal_created}, "
                f"geographies_created={result.geographies_created}, "
                f"categories_created={result.categories_created}, "
                f"sample_content_created={result.sample_content_created}, "
                f"sample_translation_created={result.sample_translation_created}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
