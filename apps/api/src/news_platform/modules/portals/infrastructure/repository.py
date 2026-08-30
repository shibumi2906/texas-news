from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.portals.domain.models import Portal


class PortalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, portal: Portal) -> Portal:
        self.session.add(portal)
        await self.session.flush()
        return portal

    async def get(self, portal_id: UUID) -> Portal | None:
        return await self.session.get(Portal, portal_id)

    async def get_by_slug(self, slug: str) -> Portal | None:
        return cast(
            Portal | None, await self.session.scalar(select(Portal).where(Portal.slug == slug))
        )
