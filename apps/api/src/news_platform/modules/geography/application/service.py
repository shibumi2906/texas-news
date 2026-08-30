from uuid import UUID

from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.geography.domain.schemas import GeographyNodeCreate
from news_platform.modules.geography.infrastructure.repository import GeographyRepository


class GeographyService:
    def __init__(self, repository: GeographyRepository) -> None:
        self.repository = repository

    async def create(self, data: GeographyNodeCreate) -> GeographyNode:
        values = data.model_dump(exclude={"metadata"})
        geography = GeographyNode(**values, metadata_=data.metadata)
        return await self.repository.add(geography)

    async def get(self, geography_id: UUID) -> GeographyNode | None:
        return await self.repository.get(geography_id)

    async def get_by_slug(self, slug: str) -> GeographyNode | None:
        return await self.repository.get_by_slug(slug)
