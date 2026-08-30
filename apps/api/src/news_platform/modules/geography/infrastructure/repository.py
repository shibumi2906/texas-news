from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.geography.domain.models import GeographyNode


class GeographyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, geography: GeographyNode) -> GeographyNode:
        self.session.add(geography)
        await self.session.flush()
        return geography

    async def get(self, geography_id: UUID) -> GeographyNode | None:
        return await self.session.get(GeographyNode, geography_id)

    async def get_by_slug(self, slug: str) -> GeographyNode | None:
        return cast(
            GeographyNode | None,
            await self.session.scalar(select(GeographyNode).where(GeographyNode.slug == slug)),
        )
