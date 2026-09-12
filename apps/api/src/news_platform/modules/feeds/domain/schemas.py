from enum import StrEnum

from pydantic import BaseModel

from news_platform.modules.public_site.domain.schemas import PublicPortal, PublicStorySummary


class FeedKind(StrEnum):
    HOME = "home"
    LATEST = "latest"
    CATEGORY = "category"
    LOCAL = "local"
    TRENDING = "trending"
    FOR_YOU = "for_you"
    FOLLOWING = "following"
    SHORTS = "shorts"


class PublicFeedPage(BaseModel):
    portal: PublicPortal
    feed: FeedKind
    scope: str | None
    label: str
    language: str
    canonical_url: str
    alternates: dict[str, str]
    items: list[PublicStorySummary]
    next_cursor: str | None
