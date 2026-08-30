from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.taxonomy.domain.models import Category, Topic


class TaxonomyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_category(self, category: Category) -> Category:
        self.session.add(category)
        await self.session.flush()
        return category

    async def add_topic(self, topic: Topic) -> Topic:
        self.session.add(topic)
        await self.session.flush()
        return topic

    async def get_category(self, category_id: UUID) -> Category | None:
        return await self.session.get(Category, category_id)

    async def get_category_by_slug(self, slug: str) -> Category | None:
        return cast(
            Category | None,
            await self.session.scalar(select(Category).where(Category.slug == slug)),
        )

    async def get_topic(self, topic_id: UUID) -> Topic | None:
        return await self.session.get(Topic, topic_id)

    async def get_topic_by_slug(self, slug: str) -> Topic | None:
        return cast(
            Topic | None, await self.session.scalar(select(Topic).where(Topic.slug == slug))
        )
