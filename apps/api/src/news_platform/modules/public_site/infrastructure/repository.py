from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import case, exists, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentItem,
    ContentType,
    Source,
)
from news_platform.modules.entities.domain.models import Entity
from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.media.domain.models import MediaAsset, MediaStatus, MediaType
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.public_site.domain.policy import public_content_predicates
from news_platform.modules.taxonomy.domain.models import Category, TaxonomyStatus


@dataclass
class PublicContentRecord:
    content: ContentItem
    source: Source | None = None
    categories: list[Category] = field(default_factory=list)
    geographies: list[GeographyNode] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    media: list[MediaAsset] = field(default_factory=list)


class PublicSiteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_portal(self, slug: str) -> Portal | None:
        return cast(
            Portal | None,
            await self.session.scalar(
                select(Portal).where(Portal.slug == slug, Portal.status == PortalStatus.ACTIVE)
            ),
        )

    async def portal_categories(self, portal: Portal) -> list[Category]:
        enabled = portal.category_settings.get("enabled", [])
        statement = select(Category).where(Category.status == TaxonomyStatus.ACTIVE)
        if isinstance(enabled, list) and enabled:
            statement = statement.where(Category.slug.in_([str(value) for value in enabled]))
        return list(
            (
                await self.session.scalars(
                    statement.order_by(Category.sort_order, Category.name, Category.id)
                )
            ).all()
        )

    async def get_category(self, slug: str) -> Category | None:
        return cast(
            Category | None,
            await self.session.scalar(
                select(Category).where(
                    Category.slug == slug, Category.status == TaxonomyStatus.ACTIVE
                )
            ),
        )

    def _portal_scope(self, portal: Portal) -> Any:
        if portal.primary_geography_id is None:
            return false()
        geography_scope = (
            select(GeographyNode.id)
            .where(GeographyNode.id == portal.primary_geography_id)
            .cte(name="portal_geography", recursive=True)
        )
        geography_scope = geography_scope.union_all(
            select(GeographyNode.id).join(
                geography_scope, GeographyNode.parent_id == geography_scope.c.id
            )
        )
        return exists(
            select(ContentGeography.content_item_id).where(
                ContentGeography.content_item_id == ContentItem.id,
                ContentGeography.geography_id.in_(select(geography_scope.c.id)),
            )
        )

    def _eligible_statement(self, portal: Portal, now: datetime) -> Any:
        return select(ContentItem).where(
            *public_content_predicates(now), self._portal_scope(portal)
        )

    async def list_content(
        self,
        portal: Portal,
        now: datetime,
        *,
        category_id: UUID | None = None,
        content_types: set[ContentType] | None = None,
        exclude_id: UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PublicContentRecord], int]:
        statement = self._eligible_statement(portal, now)
        if category_id is not None:
            statement = statement.where(
                exists(
                    select(ContentCategory.content_item_id).where(
                        ContentCategory.content_item_id == ContentItem.id,
                        ContentCategory.category_id == category_id,
                    )
                )
            )
        if content_types:
            statement = statement.where(ContentItem.content_type.in_(content_types))
        if exclude_id is not None:
            statement = statement.where(ContentItem.id != exclude_id)
        total = await self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        items = list(
            (
                await self.session.scalars(
                    statement.order_by(ContentItem.site_published_at.desc(), ContentItem.id)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )
        return await self._hydrate(items), total or 0

    async def get_story(
        self, portal: Portal, slug: str, now: datetime
    ) -> PublicContentRecord | None:
        content = await self.session.scalar(
            self._eligible_statement(portal, now).where(ContentItem.slug == slug)
        )
        if content is None:
            return None
        return (await self._hydrate([content]))[0]

    async def category_section_content(
        self,
        portal: Portal,
        categories: list[Category],
        now: datetime,
        per_category: int,
    ) -> dict[UUID, list[PublicContentRecord]]:
        if not categories:
            return {}
        category_ids = [category.id for category in categories]
        ranked = (
            select(
                ContentCategory.category_id.label("category_id"),
                ContentItem.id.label("content_id"),
                func.row_number()
                .over(
                    partition_by=ContentCategory.category_id,
                    order_by=(ContentItem.site_published_at.desc(), ContentItem.id),
                )
                .label("position"),
            )
            .join(ContentItem, ContentItem.id == ContentCategory.content_item_id)
            .where(
                ContentCategory.category_id.in_(category_ids),
                *public_content_predicates(now),
                self._portal_scope(portal),
            )
            .subquery()
        )
        rows = (
            await self.session.execute(
                select(ranked.c.category_id, ranked.c.content_id)
                .where(ranked.c.position <= per_category)
                .order_by(ranked.c.category_id, ranked.c.position)
            )
        ).all()
        content_ids = list(dict.fromkeys(row.content_id for row in rows))
        if not content_ids:
            return {category_id: [] for category_id in category_ids}
        contents = list(
            (
                await self.session.scalars(
                    select(ContentItem).where(ContentItem.id.in_(content_ids))
                )
            ).all()
        )
        records = {record.content.id: record for record in await self._hydrate(contents)}
        result: dict[UUID, list[PublicContentRecord]] = {
            category_id: [] for category_id in category_ids
        }
        for row in rows:
            result[row.category_id].append(records[row.content_id])
        return result

    async def _hydrate(self, contents: list[ContentItem]) -> list[PublicContentRecord]:
        if not contents:
            return []
        content_ids = [content.id for content in contents]
        records = {content.id: PublicContentRecord(content=content) for content in contents}

        source_ids = [content.source_id for content in contents if content.source_id is not None]
        if source_ids:
            sources = list(
                (await self.session.scalars(select(Source).where(Source.id.in_(source_ids)))).all()
            )
            source_map = {source.id: source for source in sources}
            for record in records.values():
                if record.content.source_id is not None:
                    record.source = source_map.get(record.content.source_id)

        category_rows = (
            await self.session.execute(
                select(ContentCategory.content_item_id, Category)
                .join(Category, Category.id == ContentCategory.category_id)
                .where(ContentCategory.content_item_id.in_(content_ids))
                .order_by(Category.sort_order, Category.name, Category.id)
            )
        ).all()
        for content_id, category in category_rows:
            records[content_id].categories.append(category)

        geography_rows = (
            await self.session.execute(
                select(ContentGeography.content_item_id, GeographyNode)
                .join(GeographyNode, GeographyNode.id == ContentGeography.geography_id)
                .where(ContentGeography.content_item_id.in_(content_ids))
                .order_by(ContentGeography.relationship_type, GeographyNode.name, GeographyNode.id)
            )
        ).all()
        for content_id, geography in geography_rows:
            records[content_id].geographies.append(geography)

        entity_rows = (
            await self.session.execute(
                select(ContentEntity.content_item_id, Entity)
                .join(Entity, Entity.id == ContentEntity.entity_id)
                .where(ContentEntity.content_item_id.in_(content_ids))
                .order_by(Entity.canonical_name, Entity.id)
            )
        ).all()
        for content_id, entity in entity_rows:
            records[content_id].entities.append(entity)

        media_rows = (
            await self.session.execute(
                select(MediaAsset)
                .where(
                    MediaAsset.content_item_id.in_(content_ids),
                    MediaAsset.status == MediaStatus.READY,
                    (MediaAsset.storage_url.is_not(None) | MediaAsset.source_url.is_not(None)),
                )
                .order_by(
                    MediaAsset.content_item_id,
                    case((MediaAsset.type == MediaType.IMAGE, 0), else_=1),
                    MediaAsset.id,
                )
            )
        ).scalars()
        for media in media_rows:
            records[media.content_item_id].media.append(media)
        return [records[content.id] for content in contents]
