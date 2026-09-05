from uuid import UUID

from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentItem,
    ContentTopic,
    ContentVersion,
    Source,
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
from news_platform.modules.entities.infrastructure.repository import EntityRepository
from news_platform.modules.geography.infrastructure.repository import GeographyRepository
from news_platform.modules.taxonomy.infrastructure.repository import TaxonomyRepository


class SourceService:
    def __init__(self, repository: SourceRepository) -> None:
        self.repository = repository

    async def create(self, data: SourceCreate) -> Source:
        values = data.model_dump(exclude={"canonical_url", "metadata"})
        source = Source(
            **values,
            canonical_url=str(data.canonical_url) if data.canonical_url else None,
            metadata_=data.metadata,
        )
        return await self.repository.add(source)


class ContentService:
    def __init__(
        self,
        repository: ContentRepository,
        taxonomy_repository: TaxonomyRepository,
        entity_repository: EntityRepository,
        geography_repository: GeographyRepository,
    ) -> None:
        self.repository = repository
        self.taxonomy_repository = taxonomy_repository
        self.entity_repository = entity_repository
        self.geography_repository = geography_repository

    async def create(self, data: ContentItemCreate) -> ContentItem:
        values = data.model_dump(exclude={"original_url", "metadata", "first_seen_at"})
        if values["slug"] is None:
            del values["slug"]
        if data.first_seen_at is not None:
            values["first_seen_at"] = data.first_seen_at
        content = ContentItem(
            **values,
            original_url=str(data.original_url) if data.original_url else None,
            metadata_=data.metadata,
        )
        return await self.repository.add(content)

    async def get(self, content_id: UUID) -> ContentItem | None:
        return await self.repository.get(content_id)

    async def create_version(self, data: ContentVersionCreate) -> ContentVersion:
        if await self.repository.get(data.content_item_id) is None:
            raise LookupError("content item not found")
        values = data.model_dump(exclude={"metadata"})
        return await self.repository.add_version(ContentVersion(**values, metadata_=data.metadata))

    async def associate_category(self, content_id: UUID, category_id: UUID) -> ContentCategory:
        await self._require_content(content_id)
        if await self.taxonomy_repository.get_category(category_id) is None:
            raise LookupError("category not found")
        return await self.repository.associate_category(content_id, category_id)

    async def associate_topic(self, content_id: UUID, topic_id: UUID) -> ContentTopic:
        await self._require_content(content_id)
        if await self.taxonomy_repository.get_topic(topic_id) is None:
            raise LookupError("topic not found")
        return await self.repository.associate_topic(content_id, topic_id)

    async def associate_entity(
        self, content_id: UUID, data: ContentEntityAssociation
    ) -> ContentEntity:
        await self._require_content(content_id)
        if await self.entity_repository.get(data.entity_id) is None:
            raise LookupError("entity not found")
        return await self.repository.associate_entity(
            content_id,
            data.entity_id,
            data.relationship_type,
            data.confidence,
            data.source,
        )

    async def associate_geography(
        self, content_id: UUID, data: ContentGeographyAssociation
    ) -> ContentGeography:
        await self._require_content(content_id)
        if await self.geography_repository.get(data.geography_id) is None:
            raise LookupError("geography not found")
        return await self.repository.associate_geography(
            content_id,
            data.geography_id,
            data.relationship_type,
            data.confidence,
            data.source,
        )

    async def _require_content(self, content_id: UUID) -> None:
        if await self.repository.get(content_id) is None:
            raise LookupError("content item not found")
