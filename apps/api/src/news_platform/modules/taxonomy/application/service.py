from news_platform.modules.taxonomy.domain.models import Category, Topic
from news_platform.modules.taxonomy.domain.schemas import CategoryCreate, TopicCreate
from news_platform.modules.taxonomy.infrastructure.repository import TaxonomyRepository


class TaxonomyService:
    def __init__(self, repository: TaxonomyRepository) -> None:
        self.repository = repository

    async def create_category(self, data: CategoryCreate) -> Category:
        return await self.repository.add_category(Category(**data.model_dump()))

    async def create_topic(self, data: TopicCreate) -> Topic:
        return await self.repository.add_topic(Topic(**data.model_dump()))
