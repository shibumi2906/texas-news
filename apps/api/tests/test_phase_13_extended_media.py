from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_phase_5_feeds import (  # noqa: F401
    NOW,
    database,
    redis_client,
    seed_domain,
)

from news_platform.modules.analytics.application.service import AnalyticsIngestionService
from news_platform.modules.analytics.domain.models import BehaviorEvent
from news_platform.modules.analytics.domain.schemas import BehaviorEventCreate
from news_platform.modules.community.application.service import CommunityService
from news_platform.modules.community.domain.models import Comment, Reaction, ReactionType, Save
from news_platform.modules.community.domain.schemas import CommentCreate, ReactionUpdate
from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentGeography,
    ContentGeographyRelationship,
    ContentItem,
    ContentStatus,
    ContentType,
)
from news_platform.modules.feeds.application.service import FeedService
from news_platform.modules.feeds.domain.schemas import FeedKind
from news_platform.modules.localization.domain.models import Translation, TranslationStatus
from news_platform.modules.media.domain.models import MediaAsset, MediaStatus, MediaType
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.public_site.application.service import (
    PublicNotFoundError,
    PublicSiteService,
)
from news_platform.modules.users.application.service import AuthenticatedUser
from news_platform.modules.users.domain.models import AuthSession, User, UserProfile

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def add_media_content(
    session: AsyncSession,
    domain: dict[str, Any],
    identity: int,
    content_type: ContentType,
    *,
    status: ContentStatus = ContentStatus.PUBLISHED,
    geography: str = "austin",
    spanish: bool = True,
    media_count: int = 1,
) -> ContentItem:
    item = ContentItem(
        id=UUID(int=identity),
        slug=f"media-{content_type.value}-{identity}",
        content_type=content_type,
        status=status,
        upstream_status=ContentStatus.PUBLISHED,
        original_language="en",
        primary_language="en",
        title=f"{content_type.value.title()} {identity}",
        description=f"Public {content_type.value} experience",
        body="Canonical body",
        site_published_at=NOW - timedelta(hours=identity % 10 + 1),
        metadata_={},
        seo={},
    )
    session.add(item)
    await session.flush()
    session.add_all(
        [
            ContentCategory(content_item_id=item.id, category_id=domain["music"].id),
            ContentGeography(
                content_item_id=item.id,
                geography_id=domain[geography].id,
                relationship_type=ContentGeographyRelationship.PRIMARY,
                source="test",
            ),
        ]
    )
    for position in reversed(range(media_count)):
        media_type = (
            MediaType.VIDEO
            if content_type in {ContentType.SHORT, ContentType.LIVE}
            else MediaType.IMAGE
        )
        session.add(
            MediaAsset(
                id=UUID(int=identity * 100 + position + 1),
                content_item_id=item.id,
                position=position,
                type=media_type,
                source_url=f"https://media.example/{identity}/{position}",
                mime_type="video/mp4" if media_type is MediaType.VIDEO else "image/jpeg",
                duration=30 if media_type is MediaType.VIDEO else None,
                attribution=f"Caption {position}",
                metadata_={},
                status=MediaStatus.READY,
            )
        )
    if spanish:
        portal = await session.scalar(select(Portal).where(Portal.slug == "texas"))
        assert portal is not None
        session.add(
            Translation(
                portal_id=portal.id,
                content_item_id=item.id,
                language="es",
                title=f"ES {content_type.value} {identity}",
                subtitle=None,
                description="Representación pública",
                body="Cuerpo canónico traducido",
                translation_source="test",
                status=TranslationStatus.EDITORIAL,
                source_updated_at=NOW,
            )
        )
    await session.flush()
    return item


async def test_all_media_types_render_with_ordered_canonical_data_and_languages(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        portal = await session.scalar(select(Portal).where(Portal.slug == "texas"))
        assert portal is not None
        portal.feature_flags = {**portal.feature_flags, "shorts": True}
        oklahoma_portal = await session.scalar(select(Portal).where(Portal.slug == "oklahoma"))
        assert oklahoma_portal is not None
        oklahoma_portal.feature_flags = {**oklahoma_portal.feature_flags, "shorts": True}
        items = {
            content_type: await add_media_content(
                session,
                domain,
                1300 + index,
                content_type,
                media_count=3 if content_type is ContentType.GALLERY else 1,
            )
            for index, content_type in enumerate(
                (
                    ContentType.GALLERY,
                    ContentType.MEME,
                    ContentType.SHORT,
                    ContentType.EVENT,
                    ContentType.LIVE,
                )
            )
        }
        missing_spanish = await add_media_content(
            session, domain, 1310, ContentType.SHORT, spanish=False
        )
        hidden = await add_media_content(
            session,
            domain,
            1311,
            ContentType.SHORT,
            status=ContentStatus.UNPUBLISHED,
        )
        outside = await add_media_content(
            session, domain, 1312, ContentType.SHORT, geography="oklahoma"
        )

    async with factory() as session:
        service = PublicSiteService(session, now=NOW)
        for content_type, item in items.items():
            english = await service.story("texas", item.slug, "en")
            spanish = await service.story("texas", item.slug, "es")
            assert english.id == item.id == spanish.id
            assert english.content_type is content_type
            assert spanish.language == "es" and spanish.title.startswith("ES ")
            assert english.canonical_url.endswith(f"/story/{item.slug}")
        gallery = await service.story("texas", items[ContentType.GALLERY].slug, "en")
        assert [media.position for media in gallery.media] == [0, 1, 2]
        assert [media.attribution for media in gallery.media] == [
            "Caption 0",
            "Caption 1",
            "Caption 2",
        ]
        for item in (missing_spanish, hidden, outside):
            with pytest.raises(PublicNotFoundError):
                await service.story("texas", item.slug, "es" if item is missing_spanish else "en")
        oklahoma_story = await service.story("oklahoma", outside.slug, "en")
        assert oklahoma_story.id == outside.id
        with pytest.raises(PublicNotFoundError):
            await service.story("oklahoma", items[ContentType.SHORT].slug, "en")


async def test_shorts_feed_and_related_keep_one_ranking_identity(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
    redis_client: Redis,  # noqa: F811
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        portal = await session.scalar(select(Portal).where(Portal.slug == "texas"))
        assert portal is not None
        portal.feature_flags = {**portal.feature_flags, "shorts": True}
        oklahoma_portal = await session.scalar(select(Portal).where(Portal.slug == "oklahoma"))
        assert oklahoma_portal is not None
        oklahoma_portal.feature_flags = {**oklahoma_portal.feature_flags, "shorts": True}
        first = await add_media_content(session, domain, 1320, ContentType.SHORT)
        second = await add_media_content(session, domain, 1321, ContentType.SHORT)
        oklahoma_short = await add_media_content(
            session, domain, 1323, ContentType.SHORT, geography="oklahoma"
        )
        await add_media_content(session, domain, 1322, ContentType.MEME)

    async with factory() as session:
        feed = await FeedService(session, redis_client, 30, now=NOW).page(
            "texas",
            FeedKind.SHORTS,
            language="en",
            limit=20,
            cursor_value=None,
        )
        assert {item.id for item in feed.items} == {first.id, second.id}
        assert len({item.id for item in feed.items}) == len(feed.items)
        story = await PublicSiteService(session, now=NOW).story("texas", first.slug, "en")
        assert [item.id for item in story.related] == [second.id]
        assert all(item.content_type is ContentType.SHORT for item in story.related)
        oklahoma_feed = await FeedService(session, redis_client, 30, now=NOW).page(
            "oklahoma",
            FeedKind.SHORTS,
            language="en",
            limit=20,
            cursor_value=None,
        )
        assert [item.id for item in oklahoma_feed.items] == [oklahoma_short.id]
        oklahoma_story = await PublicSiteService(session, now=NOW).story(
            "oklahoma", oklahoma_short.slug, "en"
        )
        assert oklahoma_story.related == []
        portal = await session.scalar(select(Portal).where(Portal.slug == "texas"))
        assert portal is not None
        portal.feature_flags = {**portal.feature_flags, "shorts": False}
        await session.flush()
        with pytest.raises(PublicNotFoundError):
            await FeedService(session, redis_client, 30, now=NOW).page(
                "texas",
                FeedKind.SHORTS,
                language="en",
                limit=20,
                cursor_value=None,
            )
        with pytest.raises(PublicNotFoundError):
            await PublicSiteService(session, now=NOW).story("texas", first.slug, "en")


async def test_short_reuses_analytics_comments_reactions_and_saves(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        short = await add_media_content(session, domain, 1330, ContentType.SHORT)
        portal = await session.scalar(select(Portal).where(Portal.slug == "texas"))
        assert portal is not None
        portal.feature_flags = {**portal.feature_flags, "community": True, "shorts": True}
        user = User(email="shorts@example.com", role="user", status="active")
        session.add(user)
        await session.flush()
        profile = UserProfile(user_id=user.id, display_name="Short Fan", preferred_language="en")
        auth_session = AuthSession(
            user_id=user.id,
            portal_id=portal.id,
            token_hash="a" * 64,
            csrf_hash="b" * 64,
            created_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
        session.add_all([profile, auth_session])
        await session.flush()
        auth = AuthenticatedUser(user=user, profile=profile, portal=portal, session=auth_session)
        community = CommunityService(session, now=NOW)
        comment, created = await community.create_comment(
            auth, short.slug, CommentCreate(id=UUID(int=133001), body="Canonical comment")
        )
        reaction = await community.react(
            auth, short.slug, ReactionUpdate(reaction_type=ReactionType.LOVE)
        )
        saved = await community.toggle_save(auth, short.slug, True)
        assert created and comment.content_id == short.id
        assert reaction.active and saved.active

        analytics = AnalyticsIngestionService(session, now=NOW)
        for offset, (event_type, properties) in enumerate(
            (
                ("video_start", {"offset_seconds": 0}),
                ("watch_time", {"seconds": 12}),
                ("completion", {}),
            )
        ):
            await analytics.collect(
                "texas",
                BehaviorEventCreate.model_validate(
                    {
                        "id": UUID(int=133100 + offset),
                        "anonymous_id": "short-viewer",
                        "session_id": "short-session",
                        "event_type": event_type,
                        "content_id": short.id,
                        "timestamp": NOW,
                        "properties": properties,
                    }
                ),
            )

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Comment)) == 1
        assert await session.scalar(select(func.count()).select_from(Reaction)) == 1
        assert await session.scalar(select(func.count()).select_from(Save)) == 1
        events = list((await session.scalars(select(BehaviorEvent))).all())
        assert {event.event_type for event in events}.issuperset(
            {"video_start", "watch_time", "completion", "reaction", "save", "comment"}
        )
        assert {event.content_id for event in events} == {short.id}
