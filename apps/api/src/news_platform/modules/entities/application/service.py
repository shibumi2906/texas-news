from news_platform.modules.entities.domain.models import Entity
from news_platform.modules.entities.domain.schemas import EntityCreate
from news_platform.modules.entities.infrastructure.repository import EntityRepository


class EntityService:
    def __init__(self, repository: EntityRepository) -> None:
        self.repository = repository

    async def create(self, data: EntityCreate) -> Entity:
        values = data.model_dump(exclude={"metadata"})
        return await self.repository.add(Entity(**values, metadata_=data.metadata))
