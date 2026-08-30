from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.entities.domain.models import Entity


class EntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, entity: Entity) -> Entity:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, entity_id: UUID) -> Entity | None:
        return await self.session.get(Entity, entity_id)

    async def get_by_slug(self, slug: str) -> Entity | None:
        return cast(
            Entity | None, await self.session.scalar(select(Entity).where(Entity.slug == slug))
        )
