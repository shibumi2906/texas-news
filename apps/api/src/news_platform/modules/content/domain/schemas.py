from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator

from news_platform.modules.content.domain.models import (
    ContentGeographyRelationship,
    ContentStatus,
    ContentType,
)

LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class SourceCreate(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    canonical_url: HttpUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentItemCreate(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(default=None, max_length=220, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    content_type: ContentType
    status: ContentStatus = ContentStatus.RECEIVED
    source_id: UUID | None = None
    original_url: HttpUrl | None = None
    original_language: str
    primary_language: str
    title: str = Field(min_length=1, max_length=500)
    subtitle: str | None = Field(default=None, max_length=500)
    description: str | None = None
    body: str | None = None
    publication_time: datetime | None = None
    original_publication_time: datetime | None = None
    first_seen_at: datetime | None = None
    canonical_content_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    story_cluster_id: str | None = Field(default=None, max_length=255)
    author: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    seo: dict[str, Any] = Field(default_factory=dict)

    @field_validator("original_language", "primary_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        if not LANGUAGE_PATTERN.fullmatch(value):
            raise ValueError("invalid language code")
        return value.lower()


class ContentVersionCreate(BaseModel):
    content_item_id: UUID
    version_number: int = Field(gt=0)
    source_revision: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    body: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: UUID | None = None
    change_reason: str | None = Field(default=None, max_length=500)


class ContentEntityAssociation(BaseModel):
    entity_id: UUID
    relationship_type: str = Field(default="mentioned", min_length=1, max_length=64)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str | None = Field(default=None, max_length=120)


class ContentGeographyAssociation(BaseModel):
    geography_id: UUID
    relationship_type: ContentGeographyRelationship
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str | None = Field(default=None, max_length=120)
