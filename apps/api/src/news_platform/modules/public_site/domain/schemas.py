from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from news_platform.modules.content.domain.models import ContentType


class PublicCategory(BaseModel):
    name: str
    slug: str


class PublicGeography(BaseModel):
    name: str
    slug: str
    type: str


class PublicEntity(BaseModel):
    id: UUID
    name: str
    slug: str
    type: str


class PublicSource(BaseModel):
    name: str
    url: str | None


class PublicMedia(BaseModel):
    id: UUID
    type: str
    url: str
    thumbnail_url: str | None
    mime_type: str | None
    width: int | None
    height: int | None
    duration: float | None
    position: int
    attribution: str | None
    provider: str | None


class PublicPortal(BaseModel):
    name: str
    slug: str
    domain: str
    timezone: str
    default_language: str
    supported_languages: list[str]
    canonical_url: str
    branding: dict[str, Any]
    categories: list[PublicCategory]


class PublicStorySummary(BaseModel):
    id: UUID
    slug: str
    url: str
    canonical_url: str
    language: str
    alternates: dict[str, str]
    content_type: ContentType
    title: str
    subtitle: str | None
    description: str | None
    author: str | None
    published_at: datetime
    updated_at: datetime
    source: PublicSource | None
    categories: list[PublicCategory]
    geography: list[PublicGeography]
    media: list[PublicMedia]


class PublicCategorySection(BaseModel):
    category: PublicCategory
    items: list[PublicStorySummary]


class PublicHomepage(BaseModel):
    portal: PublicPortal
    language: str
    canonical_url: str
    alternates: dict[str, str]
    hero: PublicStorySummary | None
    trending: list[PublicStorySummary]
    category_sections: list[PublicCategorySection]
    video_highlights: list[PublicStorySummary]
    media_highlights: list[PublicStorySummary] = Field(default_factory=list)


class PublicCategoryPage(BaseModel):
    portal: PublicPortal
    language: str
    category: PublicCategory
    canonical_url: str
    alternates: dict[str, str]
    items: list[PublicStorySummary]
    total: int
    offset: int
    limit: int


class PublicStory(PublicStorySummary):
    portal: PublicPortal
    body: str | None
    original_url: str | None
    entities: list[PublicEntity]
    seo: dict[str, Any]
    related: list[PublicStorySummary]
