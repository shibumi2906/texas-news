from enum import StrEnum

from pydantic import BaseModel

from news_platform.modules.public_site.domain.schemas import PublicPortal, PublicStorySummary


class FeedKind(StrEnum):
    HOME = "home"
    LATEST = "latest"
    CATEGORY = "category"
    LOCAL = "local"
    TRENDING = "trending"


class PublicFeedPage(BaseModel):
    portal: PublicPortal
    feed: FeedKind
    scope: str | None
    label: str
    language: str
    canonical_url: str
    items: list[PublicStorySummary]
    next_cursor: str | None
