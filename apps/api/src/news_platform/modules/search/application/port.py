from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.public_site.infrastructure.repository import PublicContentRecord
from news_platform.modules.search.domain.schemas import SearchCursor, SearchQuery


@dataclass(frozen=True)
class SearchRecord:
    record: PublicContentRecord
    score: Decimal


class SearchBackend(Protocol):
    async def generation(self) -> int: ...

    async def search(
        self, portal: Portal, query: SearchQuery, snapshot_at: datetime, cursor: SearchCursor | None
    ) -> tuple[list[SearchRecord], bool]: ...
