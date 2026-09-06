from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.feeds.domain.cursor import FeedCursor
from news_platform.modules.feeds.domain.schemas import FeedKind, PublicFeedPage
from news_platform.modules.feeds.infrastructure.cache import FeedCache
from news_platform.modules.feeds.infrastructure.repository import (
    FeedRepository,
    RankedContentRecord,
)
from news_platform.modules.public_site.application.service import (
    PublicNotFoundError,
    PublicSiteService,
)
from news_platform.modules.taxonomy.domain.models import Category
from news_platform.modules.trending.domain.scoring import TrendingWeights


class FeedService:
    def __init__(
        self,
        session: AsyncSession,
        redis_client: Any,
        cache_ttl_seconds: int,
        now: datetime | None = None,
    ) -> None:
        self.public = PublicSiteService(session, now=now)
        self.repository = FeedRepository(session)
        self.cache = FeedCache(redis_client, cache_ttl_seconds)
        self.now = now or datetime.now(UTC)

    async def page(
        self,
        portal_slug: str,
        feed: FeedKind,
        *,
        language: str,
        limit: int,
        cursor_value: str | None,
        scope: str | None = None,
    ) -> PublicFeedPage:
        portal = await self.public.repository.get_portal(portal_slug)
        if portal is None:
            raise PublicNotFoundError("portal not found")
        if language not in portal.supported_languages:
            raise PublicNotFoundError("language not supported by portal")

        categories = await self.public.repository.portal_categories(portal)
        category: Category | None = None
        geography = None
        label = feed.value.title()
        path = f"/{feed.value}"
        normalized_scope = scope or "all"
        if feed is FeedKind.CATEGORY:
            category = next((item for item in categories if item.slug == scope), None)
            if category is None:
                raise PublicNotFoundError("category not found")
            label = category.name
            path = f"/{category.slug}"
        elif feed is FeedKind.LOCAL:
            geography = await self.repository.scoped_geography(portal, normalized_scope)
            if geography is None:
                raise PublicNotFoundError("geography not found in portal")
            label = geography.name
            path = f"/local/{geography.slug}"
        elif feed is FeedKind.HOME:
            path = ""

        cache_epoch = await self.cache.epoch()
        cursor = (
            FeedCursor.decode(
                cursor_value,
                feed=feed.value,
                scope=normalized_scope,
                language=language,
                generation=cache_epoch,
            )
            if cursor_value
            else None
        )
        identity = ":".join(
            (
                portal.slug,
                feed.value,
                normalized_scope,
                language,
                str(limit),
                cursor_value or "first",
            )
        )
        cached = await self.cache.get(identity, cache_epoch)
        if cached is not None and await self.repository.cached_items_are_current(
            portal,
            self.now,
            language=language,
            items=[(item.id, item.updated_at) for item in cached.items],
            category=category,
            geography=geography,
        ):
            return cached

        snapshot_at = cursor.snapshot_at if cursor is not None else self.now
        if feed is FeedKind.TRENDING:
            records, has_more = await self.repository.trending(
                portal,
                snapshot_at,
                language=language,
                limit=limit,
                cursor=cursor,
                weights=TrendingWeights.from_portal(portal.ranking_settings),
            )
        else:
            records, has_more = await self.repository.chronological(
                portal,
                snapshot_at,
                language=language,
                limit=limit,
                cursor=cursor,
                category=category,
                geography=geography,
            )
        next_cursor = self._next_cursor(
            feed,
            normalized_scope,
            language,
            cache_epoch,
            snapshot_at,
            records,
            has_more,
        )
        portal_view = self.public.portal_view(portal, categories)
        page = PublicFeedPage(
            portal=portal_view,
            feed=feed,
            scope=None if normalized_scope == "all" else normalized_scope,
            label=label,
            language=language,
            canonical_url=f"{portal_view.canonical_url}{path}",
            items=[self.public.story_summary(portal, item.record) for item in records],
            next_cursor=next_cursor,
        )
        await self.cache.set(identity, cache_epoch, page)
        return page

    @staticmethod
    def _next_cursor(
        feed: FeedKind,
        scope: str,
        language: str,
        generation: str,
        snapshot_at: datetime,
        records: list[RankedContentRecord],
        has_more: bool,
    ) -> str | None:
        if not has_more or not records:
            return None
        last = records[-1]
        published_at = last.record.content.site_published_at
        if published_at is None:
            raise RuntimeError("public eligibility invariant violated")
        return FeedCursor(
            feed=feed.value,
            scope=scope,
            language=language,
            generation=generation,
            snapshot_at=snapshot_at,
            published_at=published_at,
            content_id=last.record.content.id,
            score=last.score,
        ).encode()
