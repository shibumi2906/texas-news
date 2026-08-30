"""Import all Phase 1 models so SQLAlchemy metadata is complete."""

from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentItem,
    ContentTopic,
    ContentVersion,
    Source,
)
from news_platform.modules.entities.domain.models import Entity
from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.media.domain.models import MediaAsset
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.taxonomy.domain.models import Category, Topic

__all__ = [
    "Category",
    "ContentCategory",
    "ContentEntity",
    "ContentGeography",
    "ContentItem",
    "ContentTopic",
    "ContentVersion",
    "Entity",
    "GeographyNode",
    "MediaAsset",
    "Portal",
    "Source",
    "Topic",
]
