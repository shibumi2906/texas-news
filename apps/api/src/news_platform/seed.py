from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.core.config import get_settings
from news_platform.infrastructure.database import create_db_engine, create_session_factory
from news_platform.modules.geography.domain.models import GeographyNode, GeographyType
from news_platform.modules.geography.infrastructure.repository import GeographyRepository
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
            "community": False,
            "ai_chat": False,
            "ai_search": False,
            "recommendations": False,
            "personalization": False,
            "shorts": False,
            "advertising": False,
            "notifications": False,
            "multilingual": False,
        }
        await portal_repository.add(
            Portal(
                slug="texas",
                name="Texas Entertainment Portal",
                domain="texas.localhost",
                status=PortalStatus.ACTIVE,
                primary_geography_id=texas.id,
                default_language="en",
                supported_languages=["en"],
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

    await session.commit()
    return SeedResult(
        portal_created=portal_created,
        geographies_created=geographies_created,
        categories_created=categories_created,
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
                f"categories_created={result.categories_created}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
