from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.portals.domain.schemas import PortalCreate
from news_platform.modules.portals.infrastructure.repository import PortalRepository


class PortalService:
    def __init__(self, repository: PortalRepository) -> None:
        self.repository = repository

    async def create(self, data: PortalCreate) -> Portal:
        portal = Portal(**data.model_dump())
        return await self.repository.add(portal)

    async def get_by_slug(self, slug: str) -> Portal | None:
        return await self.repository.get_by_slug(slug)
