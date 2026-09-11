from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_phase_5_feeds import NOW, add_story, database, seed_domain  # noqa: F401

from news_platform.modules.content.domain.models import ContentStatus
from news_platform.modules.editorial.application.service import EditorialService
from news_platform.modules.editorial.domain.schemas import EditorialEdit
from news_platform.modules.feeds.infrastructure.repository import FeedRepository
from news_platform.modules.localization.application.service import (
    InvalidTranslationError,
    TranslationService,
)
from news_platform.modules.localization.domain.models import Translation, TranslationStatus
from news_platform.modules.localization.domain.schemas import TranslationCreate
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.public_site.application.service import (
    PublicNotFoundError,
    PublicSiteService,
)
from news_platform.modules.search.application.service import SearchService
from news_platform.modules.search.domain.models import SearchGeneration
from news_platform.modules.search.domain.schemas import SearchQuery
from news_platform.modules.search.infrastructure.postgres import PostgresSearchBackend
from news_platform.modules.trending.domain.scoring import TrendingWeights

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def add_translation(
    session: AsyncSession,
    portal: Portal,
    content_id: Any,
    *,
    title: str = "Conciertos y música en Austin",
    status: TranslationStatus = TranslationStatus.REVIEWED,
) -> Translation:
    translation = Translation(
        portal_id=portal.id,
        content_item_id=content_id,
        language="es",
        title=title,
        subtitle="Una historia de Texas",
        description="Noticias traducidas para lectores de Texas.",
        body="El texto completo en español.",
        translation_source="editorial",
        status=status,
        source_updated_at=NOW,
    )
    session.add(translation)
    await session.flush()
    return translation


async def setup_story(
    session: AsyncSession, identity: int = 1201
) -> tuple[dict[str, Any], Portal, Any]:
    domain = await seed_domain(session)
    portal = await session.scalar(select(Portal).where(Portal.slug == "texas"))
    assert portal is not None
    story = await add_story(
        session,
        domain,
        identity,
        published_at=NOW - timedelta(hours=1),
        title="Austin live music returns",
    )
    return domain, portal, story


async def test_translation_entity_persistence_and_portal_language_validation(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        _domain, portal, story = await setup_story(session)
        created = await TranslationService(session).create(
            TranslationCreate(
                portal_id=portal.id,
                content_item_id=story.id,
                language="ES",
                title="Música en Austin",
                description="Una traducción persistida.",
                body="Contenido en español.",
                translation_source="editorial",
                status=TranslationStatus.EDITORIAL,
                source_updated_at=NOW,
            )
        )
        assert created.language == "es"
        assert created.content_item_id == story.id
        with pytest.raises(InvalidTranslationError, match="not supported"):
            await TranslationService(session).create(
                TranslationCreate(
                    portal_id=portal.id,
                    content_item_id=story.id,
                    language="fr",
                    title="French",
                    translation_source="editorial",
                    status=TranslationStatus.EDITORIAL,
                    source_updated_at=NOW,
                )
            )


async def test_localized_story_routes_switch_and_hreflang_are_safe(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        _domain, portal, story = await setup_story(session)
        story.seo = {"title": "English SEO title", "description": "English SEO description"}
        public = PublicSiteService(session, now=NOW)
        english = await public.story("texas", story.slug)
        assert english.language == "en"
        assert english.seo["title"] == "English SEO title"
        assert english.url == f"/story/{story.slug}"
        assert english.alternates == {"en": english.canonical_url}
        with pytest.raises(PublicNotFoundError):
            await public.story("texas", story.slug, "es")

        await add_translation(session, portal, story.id)
        spanish = await public.story("texas", story.slug, "es")
        assert spanish.title == "Conciertos y música en Austin"
        assert spanish.body == "El texto completo en español."
        assert spanish.seo == {}
        assert english.id == spanish.id == story.id
        assert spanish.url == f"/es/story/{story.slug}"
        assert set(spanish.alternates) == {"en", "es"}
        assert spanish.alternates["en"] == english.canonical_url
        assert spanish.alternates["es"] == spanish.canonical_url
        with pytest.raises(PublicNotFoundError, match="language not supported"):
            await public.story("texas", story.slug, "fr")


@pytest.mark.parametrize(
    ("status", "upstream", "published_delta"),
    [
        (ContentStatus.UNPUBLISHED, ContentStatus.RECEIVED, -1),
        (ContentStatus.PUBLISHED, ContentStatus.RECEIVED, 1),
        (ContentStatus.PUBLISHED, ContentStatus.RETRACTED, -1),
        (ContentStatus.PUBLISHED, ContentStatus.DELETED, -1),
    ],
)
async def test_translation_never_bypasses_canonical_visibility(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
    status: ContentStatus,
    upstream: ContentStatus,
    published_delta: int,
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        identity = abs(hash((status, upstream, published_delta))) % 100000 + 2000
        _domain, portal, story = await setup_story(session, identity)
        story.status = status
        story.upstream_status = upstream
        story.site_published_at = NOW + timedelta(hours=published_delta)
        await add_translation(session, portal, story.id)
        with pytest.raises(PublicNotFoundError):
            await PublicSiteService(session, now=NOW).story("texas", story.slug, "es")


async def test_portal_and_geography_isolation_for_translation(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain, portal, story = await setup_story(session)
        sibling = Portal(
            slug="texas-two",
            name="Second Texas Portal",
            domain="two.texas.example",
            status=PortalStatus.ACTIVE,
            primary_geography_id=domain["texas"].id,
            default_language="en",
            supported_languages=["en", "es"],
            timezone="America/Chicago",
            branding={},
            category_settings={},
            ranking_settings={},
            ai_settings={},
            advertising_settings={},
            seo_settings={},
            feature_flags={},
        )
        session.add(sibling)
        await session.flush()
        await add_translation(session, portal, story.id)
        with pytest.raises(PublicNotFoundError):
            await PublicSiteService(session, now=NOW).story("texas-two", story.slug, "es")
        with pytest.raises(PublicNotFoundError):
            await PublicSiteService(session, now=NOW).story("oklahoma", story.slug, "en")


async def test_canonical_editorial_change_marks_translation_outdated(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        _domain, portal, story = await setup_story(session)
        translation = await add_translation(session, portal, story.id)
        await EditorialService(session).edit(
            story.id,
            "editor:test",
            EditorialEdit(title="Corrected canonical title", reason="Correction"),
        )
        assert translation.status is TranslationStatus.OUTDATED
        with pytest.raises(PublicNotFoundError):
            await PublicSiteService(session, now=NOW).story("texas", story.slug, "es")
        english = await PublicSiteService(session, now=NOW).story("texas", story.slug, "en")
        assert english.alternates == {"en": english.canonical_url}


@pytest.mark.parametrize("status", [TranslationStatus.OUTDATED, TranslationStatus.FAILED])
async def test_non_public_translation_statuses_are_never_rendered(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
    status: TranslationStatus,
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        _domain, portal, story = await setup_story(session)
        await add_translation(session, portal, story.id, status=status)
        with pytest.raises(PublicNotFoundError):
            await PublicSiteService(session, now=NOW).story("texas", story.slug, "es")


async def test_spanish_search_and_ranked_feeds_keep_canonical_identity(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        _domain, portal, story = await setup_story(session)
        await add_translation(session, portal, story.id)
        session.add(SearchGeneration(id=1, generation=0))
        await session.flush()

        public = PublicSiteService(session, now=NOW)
        page = await SearchService(public, PostgresSearchBackend(session)).page(
            "texas", SearchQuery(q="conciertos música", language="es")
        )
        assert [(item.id, item.language) for item in page.items] == [(story.id, "es")]
        assert page.items[0].title.startswith("Conciertos")

        feed = FeedRepository(session)
        chronological, more = await feed.chronological(
            portal, NOW, language="es", limit=10, cursor=None
        )
        trending, _ = await feed.trending(
            portal,
            NOW,
            language="es",
            limit=10,
            cursor=None,
            weights=TrendingWeights.from_portal(portal.ranking_settings),
        )
        assert not more
        assert [item.record.content.id for item in chronological] == [story.id]
        assert [item.record.content.id for item in trending] == [story.id]
        assert chronological[0].record.language == "es"
