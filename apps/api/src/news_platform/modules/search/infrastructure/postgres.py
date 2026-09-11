from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import Numeric, Text, and_, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentItem,
)
from news_platform.modules.entities.domain.models import Entity
from news_platform.modules.feeds.infrastructure.repository import (
    FeedRepository,
)
from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.localization.domain.models import (
    PUBLIC_TRANSLATION_STATUSES,
    Translation,
)
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.public_site.application.service import PublicNotFoundError
from news_platform.modules.public_site.infrastructure.repository import PublicSiteRepository
from news_platform.modules.search.application.port import SearchRecord
from news_platform.modules.search.domain.models import SearchGeneration
from news_platform.modules.search.domain.schemas import SearchCursor, SearchQuery


class PostgresSearchBackend:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.public = PublicSiteRepository(session)

    async def generation(self) -> int:
        # Hold a shared lock until the request transaction ends. Trigger updates
        # serialize commits against this read, including association and scope changes.
        value = await self.session.scalar(
            select(SearchGeneration.generation)
            .where(SearchGeneration.id == 1)
            .with_for_update(read=True)
        )
        if value is None:
            raise RuntimeError("search migration has not been applied")
        return value

    async def search(
        self, portal: Portal, query: SearchQuery, snapshot_at: datetime, cursor: SearchCursor | None
    ) -> tuple[list[SearchRecord], bool]:
        config = {"en": "english", "es": "spanish"}.get(query.language.split("-")[0], "simple")
        terms = func.plainto_tsquery(config, query.q)
        active_vector = func.coalesce(Translation.search_vector, ContentItem.search_vector)
        score = (
            func.round(cast(func.ts_rank_cd(active_vector, terms), Numeric), 6)
            if query.q
            else cast(literal(0), Numeric)
        ).label("search_score")
        statement = (
            self.public.eligible_statement(portal, snapshot_at)
            .outerjoin(
                Translation,
                and_(
                    Translation.content_item_id == ContentItem.id,
                    Translation.portal_id == portal.id,
                    Translation.language == query.language,
                    Translation.status.in_(PUBLIC_TRANSLATION_STATUSES),
                ),
            )
            .where(self.public.representation_available(portal, query.language))
            .with_only_columns(ContentItem, score)
        )
        if query.q:
            statement = statement.where(active_vector.bool_op("@@")(terms))
        if query.entity:
            # Entity is a separate AND condition, supporting exact slug or words
            # in canonical names / aliases. It never exposes an entity directory.
            entity_terms = func.plainto_tsquery("simple", query.entity)
            entity_vector = func.to_tsvector(
                "simple", Entity.canonical_name + " " + cast(Entity.aliases, Text)
            )
            statement = statement.where(
                select(ContentEntity.content_item_id)
                .join(Entity, Entity.id == ContentEntity.entity_id)
                .where(
                    ContentEntity.content_item_id == ContentItem.id,
                    or_(Entity.slug == query.entity, entity_vector.bool_op("@@")(entity_terms)),
                )
                .exists()
            )
        if query.category:
            categories = await self.public.portal_categories(portal)
            category = next((c for c in categories if c.slug == query.category), None)
            if category is None:
                raise PublicNotFoundError("category not found")
            statement = statement.where(
                select(ContentCategory.content_item_id)
                .where(
                    ContentCategory.content_item_id == ContentItem.id,
                    ContentCategory.category_id == category.id,
                )
                .exists()
            )
        if query.geography:
            geography = await FeedRepository(self.session).scoped_geography(portal, query.geography)
            if geography is None:
                raise PublicNotFoundError("geography not found in portal")
            scope = (
                select(GeographyNode.id)
                .where(GeographyNode.id == geography.id)
                .cte("search_geography", recursive=True)
            )
            scope = scope.union_all(
                select(GeographyNode.id).join(scope, GeographyNode.parent_id == scope.c.id)
            )
            statement = statement.where(
                select(ContentGeography.content_item_id)
                .where(
                    ContentGeography.content_item_id == ContentItem.id,
                    ContentGeography.geography_id.in_(select(scope.c.id)),
                )
                .exists()
            )
        if query.date_from:
            statement = statement.where(
                ContentItem.site_published_at >= datetime.combine(query.date_from, time.min, UTC)
            )
        if query.date_to:
            statement = statement.where(
                ContentItem.site_published_at
                < datetime.combine(query.date_to + timedelta(days=1), time.min, UTC)
            )
        if cursor:
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
                ).limit(query.limit + 1)
            )
        ).all()
        records = await self.public.hydrate(
            [row[0] for row in rows[: query.limit]], portal, query.language
        )
        return [
            SearchRecord(record, Decimal(str(row[1])))
            for record, row in zip(records, rows[: query.limit], strict=True)
        ], len(rows) > query.limit
