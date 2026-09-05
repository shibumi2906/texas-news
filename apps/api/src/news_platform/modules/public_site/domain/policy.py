from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement

from news_platform.modules.content.domain.models import ContentItem, ContentStatus


def public_content_predicates(now: datetime) -> tuple[ColumnElement[Any], ...]:
    """The single visibility policy used by every public content query."""
    return (
        ContentItem.status == ContentStatus.PUBLISHED,
        ContentItem.upstream_status.not_in((ContentStatus.RETRACTED, ContentStatus.DELETED)),
        ContentItem.site_published_at.is_not(None),
        ContentItem.site_published_at <= now,
    )
