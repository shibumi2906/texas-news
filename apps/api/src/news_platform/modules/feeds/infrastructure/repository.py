from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import Numeric, and_, case, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentGeography,
    ContentItem,
    ContentType,
)
from news_platform.modules.engagement.domain.models import ContentEngagementCounter
from news_platform.modules.feeds.domain.cursor import FeedCursor
from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.localization.domain.models import (
    PUBLIC_TRANSLATION_STATUSES,
    Translation,
)
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.public_site.infrastructure.repository import (
    PublicContentRecord,
    PublicSiteRepository,
)
from news_platform.modules.taxonomy.domain.models import Category
from news_platform.modules.trending.domain.scoring import TrendingWeights


@dataclass(frozen=True)
class RankedContentRecord:
    record: PublicContentRecord
    score: Decimal | None = None


class FeedRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.public = PublicSiteRepository(session)

    async def scoped_geography(self, portal: Portal, slug: str) -> GeographyNode | None:
        if portal.primary_geography_id is None:
            return None
        portal_geography = (
            select(GeographyNode.id)
            .where(GeographyNode.id == portal.primary_geography_id)
            .cte(name="feed_portal_geography", recursive=True)
        )
        portal_geography = portal_geography.union_all(
            select(GeographyNode.id).join(
                portal_geography, GeographyNode.parent_id == portal_geography.c.id
            )
        )
        return cast(
            GeographyNode | None,
            await self.session.scalar(
                select(GeographyNode).where(
                    GeographyNode.slug == slug,
                    GeographyNode.id.in_(select(portal_geography.c.id)),
                )
            ),
        )

    async def chronological(
        self,
        portal: Portal,
        now: datetime,
        *,
        language: str,
        limit: int,
        cursor: FeedCursor | None,
        category: Category | None = None,
        geography: GeographyNode | None = None,
        content_types: set[ContentType] | None = None,
    ) -> tuple[list[RankedContentRecord], bool]:
        statement = self.public.eligible_statement(portal, now).where(
            self.public.representation_available(portal, language)
        )
        if category is not None:
            statement = statement.where(
                select(ContentCategory.content_item_id)
                .where(
                    ContentCategory.content_item_id == ContentItem.id,
                    ContentCategory.category_id == category.id,
                )
                .exists()
            )
        if content_types:
            statement = statement.where(ContentItem.content_type.in_(content_types))
        if geography is not None:
            geography_scope = (
                select(GeographyNode.id)
                .where(GeographyNode.id == geography.id)
                .cte(name="feed_local_geography", recursive=True)
            )
            geography_scope = geography_scope.union_all(
                select(GeographyNode.id).join(
                    geography_scope, GeographyNode.parent_id == geography_scope.c.id
                )
            )
            statement = statement.where(
                select(ContentGeography.content_item_id)
                .where(
                    ContentGeography.content_item_id == ContentItem.id,
                    ContentGeography.geography_id.in_(select(geography_scope.c.id)),
                )
                .exists()
            )
        if cursor is not None:
            statement = statement.where(
                or_(
                    ContentItem.site_published_at < cursor.published_at,
                    and_(
                        ContentItem.site_published_at == cursor.published_at,
                        ContentItem.id < cursor.content_id,
                    ),
                )
            )
        contents = list(
            (
                await self.session.scalars(
                    statement.order_by(
                        ContentItem.site_published_at.desc(), ContentItem.id.desc()
                    ).limit(limit + 1)
                )
            ).all()
        )
        has_more = len(contents) > limit
        records = await self.public.hydrate(contents[:limit], portal, language)
        return [RankedContentRecord(record) for record in records], has_more

    async def cached_items_are_current(
        self,
        portal: Portal,
        now: datetime,
        *,
        language: str,
        items: list[tuple[UUID, datetime]],
        category: Category | None = None,
        geography: GeographyNode | None = None,
        content_types: set[ContentType] | None = None,
    ) -> bool:
        if not items:
            return True
        identities = [item[0] for item in items]
        effective_updated_at = func.coalesce(Translation.updated_at, ContentItem.updated_at).label(
            "effective_updated_at"
        )
        statement = (
            self.public.eligible_statement(portal, now)
            .outerjoin(
                Translation,
                and_(
                    Translation.content_item_id == ContentItem.id,
                    Translation.portal_id == portal.id,
                    Translation.language == language,
                    Translation.status.in_(PUBLIC_TRANSLATION_STATUSES),
                ),
            )
            .where(
                ContentItem.id.in_(identities),
                self.public.representation_available(portal, language),
            )
        )
        if category is not None:
            statement = statement.where(
                select(ContentCategory.content_item_id)
                .where(
                    ContentCategory.content_item_id == ContentItem.id,
                    ContentCategory.category_id == category.id,
                )
                .exists()
            )
        if content_types:
            statement = statement.where(ContentItem.content_type.in_(content_types))
        if geography is not None:
            geography_scope = (
                select(GeographyNode.id)
                .where(GeographyNode.id == geography.id)
                .cte(name="cached_local_geography", recursive=True)
            )
            geography_scope = geography_scope.union_all(
                select(GeographyNode.id).join(
                    geography_scope, GeographyNode.parent_id == geography_scope.c.id
                )
            )
            statement = statement.where(
                select(ContentGeography.content_item_id)
                .where(
                    ContentGeography.content_item_id == ContentItem.id,
                    ContentGeography.geography_id.in_(select(geography_scope.c.id)),
                )
                .exists()
            )
        rows = (
            await self.session.execute(
                statement.with_only_columns(ContentItem.id, effective_updated_at)
            )
        ).all()
        return {(row.id, row.effective_updated_at) for row in rows} == set(items)

    async def trending(
        self,
        portal: Portal,
        now: datetime,
        *,
        language: str,
        limit: int,
        cursor: FeedCursor | None,
        weights: TrendingWeights,
    ) -> tuple[list[RankedContentRecord], bool]:
        counters = ContentEngagementCounter
        zero = 0
        impressions = func.coalesce(counters.impressions, zero)
        clicks = func.coalesce(counters.clicks, zero)
        views = func.coalesce(counters.views, zero)
        age_hours = func.greatest(
            func.extract("epoch", now - ContentItem.site_published_at) / 3600.0, 0.0
        )
        ctr = case((impressions > 0, clicks * 1.0 / impressions), else_=0.0)
        velocity = views * 1.0 / func.greatest(age_hours, 1.0)
        engagement = (
            impressions * weights.impressions
            + clicks * weights.clicks
            + ctr * weights.ctr
            + views * weights.views
            + velocity * weights.view_growth
            + func.coalesce(counters.comments, zero) * weights.comments
            + func.coalesce(counters.likes, zero) * weights.likes
            + func.coalesce(counters.shares, zero) * weights.shares
            + func.coalesce(counters.saves, zero) * weights.saves
            + func.coalesce(counters.watch_time_seconds, zero) * weights.watch_time_seconds
            + func.coalesce(counters.completions, zero) * weights.completions
        )
        freshness = 1.0 / (1.0 + age_hours / weights.freshness_half_life_hours)
        score = func.round(
            sql_cast(
                engagement * freshness * weights.local_relevance * weights.content_quality,
                Numeric,
            ),
            6,
        ).label("trend_score")
        statement = (
            self.public.eligible_statement(portal, now)
            .with_only_columns(ContentItem, score)
            .outerjoin(counters, counters.content_item_id == ContentItem.id)
            .where(self.public.representation_available(portal, language))
        )
        if cursor is not None:
            if cursor.score is None:
                raise ValueError("trending cursor requires a score")
            statement = statement.where(
                or_(
                    score < cursor.score,
                    and_(
                        score == cursor.score,
                        or_(
                            ContentItem.site_published_at < cursor.published_at,
                            and_(
                                ContentItem.site_published_at == cursor.published_at,
                                ContentItem.id < cursor.content_id,
                            ),
                        ),
                    ),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(
                    score.desc(), ContentItem.site_published_at.desc(), ContentItem.id.desc()
                ).limit(limit + 1)
            )
        ).all()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        records = await self.public.hydrate([row[0] for row in page_rows], portal, language)
        return [
            RankedContentRecord(record=record, score=Decimal(str(row[1])))
            for record, row in zip(records, page_rows, strict=True)
        ], has_more
