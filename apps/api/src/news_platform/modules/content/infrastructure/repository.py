from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentGeographyRelationship,
    ContentItem,
    ContentTopic,
    ContentVersion,
    Source,
)


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, source: Source) -> Source:
        self.session.add(source)
        await self.session.flush()
        return source

    async def get(self, source_id: UUID) -> Source | None:
        return await self.session.get(Source, source_id)


class ContentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, content: ContentItem) -> ContentItem:
        self.session.add(content)
        await self.session.flush()
        return content

    async def get(self, content_id: UUID) -> ContentItem | None:
        return await self.session.get(ContentItem, content_id)

    async def add_version(self, version: ContentVersion) -> ContentVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def associate_category(self, content_id: UUID, category_id: UUID) -> ContentCategory:
        existing = await self.session.get(ContentCategory, (content_id, category_id))
        if existing is not None:
            return existing
        association = ContentCategory(content_item_id=content_id, category_id=category_id)
        self.session.add(association)
        await self.session.flush()
        return association

    async def associate_topic(self, content_id: UUID, topic_id: UUID) -> ContentTopic:
        existing = await self.session.get(ContentTopic, (content_id, topic_id))
        if existing is not None:
            return existing
        association = ContentTopic(content_item_id=content_id, topic_id=topic_id)
        self.session.add(association)
        await self.session.flush()
        return association

    async def associate_entity(
        self,
        content_id: UUID,
        entity_id: UUID,
        relationship_type: str,
        confidence: float | None,
        source: str | None,
    ) -> ContentEntity:
        existing = await self.session.get(ContentEntity, (content_id, entity_id))
        if existing is not None:
            return existing
        association = ContentEntity(
            content_item_id=content_id,
            entity_id=entity_id,
            relationship_type=relationship_type,
            confidence=Decimal(str(confidence)) if confidence is not None else None,
            source=source,
        )
        self.session.add(association)
        await self.session.flush()
        return association

    async def associate_geography(
        self,
        content_id: UUID,
        geography_id: UUID,
        relationship_type: ContentGeographyRelationship,
        confidence: float | None,
        source: str | None,
    ) -> ContentGeography:
        key = (content_id, geography_id, relationship_type)
        existing = await self.session.get(ContentGeography, key)
        if existing is not None:
            return existing
        association = ContentGeography(
            content_item_id=content_id,
            geography_id=geography_id,
            relationship_type=relationship_type,
            confidence=Decimal(str(confidence)) if confidence is not None else None,
            source=source,
        )
        self.session.add(association)
        await self.session.flush()
        return association

    async def count_categories(self, content_id: UUID) -> int:
        rows = await self.session.scalars(
            select(ContentCategory).where(ContentCategory.content_item_id == content_id)
        )
        return len(rows.all())
