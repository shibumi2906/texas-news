from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import TimestampMixin, UUIDPrimaryKeyMixin, empty_object


class ContentType(StrEnum):
    ARTICLE = "article"
    IMAGE = "image"
    GALLERY = "gallery"
    MEME = "meme"
    VIDEO = "video"
    SHORT = "short"
    LIVE = "live"
    EVENT = "event"


class ContentStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    READY = "ready"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    RETRACTED = "retracted"
    ARCHIVED = "archived"
    DELETED = "deleted"
    FAILED = "failed"


class ContentVersionOrigin(StrEnum):
    SOURCE = "source"
    EDITORIAL = "editorial"


class ContentGeographyRelationship(StrEnum):
    PRIMARY = "primary"
    MENTIONED = "mentioned"
    EVENT_LOCATION = "event_location"
    PERSON_ORIGIN = "person_origin"
    TEAM_LOCATION = "team_location"
    VENUE_LOCATION = "venue_location"


def content_type_enum() -> Enum:
    return Enum(
        ContentType,
        values_callable=lambda values: [value.value for value in values],
        native_enum=False,
        create_constraint=False,
        name="content_type",
        validate_strings=True,
    )


def content_status_enum() -> Enum:
    return Enum(
        ContentStatus,
        values_callable=lambda values: [value.value for value in values],
        native_enum=False,
        create_constraint=False,
        name="content_status",
        validate_strings=True,
    )


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=empty_object, nullable=False
    )


class ContentItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('article', 'image', 'gallery', 'meme', 'video', 'short', "
            "'live', 'event')",
            name="content_type",
        ),
        CheckConstraint(
            "status IN ('received', 'processing', 'ready', 'scheduled', 'published', "
            "'unpublished', 'retracted', 'archived', 'deleted', 'failed')",
            name="content_status",
        ),
        Index("ix_content_items_status_publication_time", "status", "publication_time"),
        Index("ix_content_items_source_id", "source_id"),
        Index("ix_content_items_external_id", "external_id"),
        Index("ix_content_items_story_cluster_id", "story_cluster_id"),
        Index("ix_content_items_scheduled_at", "scheduled_at"),
    )

    external_id: Mapped[str | None] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(
        String(220), unique=True, nullable=False, default=lambda: f"story-{uuid4().hex}"
    )
    content_type: Mapped[ContentType] = mapped_column(content_type_enum(), nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        content_status_enum(), default=ContentStatus.RECEIVED, nullable=False
    )
    upstream_status: Mapped[ContentStatus] = mapped_column(
        content_status_enum(), default=ContentStatus.RECEIVED, nullable=False
    )
    has_editorial_override: Mapped[bool] = mapped_column(default=False, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    site_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    original_url: Mapped[str | None] = mapped_column(Text)
    original_language: Mapped[str] = mapped_column(String(35), nullable=False)
    primary_language: Mapped[str] = mapped_column(String(35), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    publication_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_publication_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    canonical_content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    story_cluster_id: Mapped[str | None] = mapped_column(String(255))
    author: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=empty_object, nullable=False
    )
    seo: Mapped[dict[str, Any]] = mapped_column(JSONB, default=empty_object, nullable=False)


class ContentVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint(
            "content_item_id", "version_number", name="uq_content_versions_item_version"
        ),
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint(
            "source_revision IS NULL OR source_revision > 0", name="source_revision_positive"
        ),
        Index("ix_content_versions_content_item_id", "content_item_id"),
        CheckConstraint("origin IN ('source', 'editorial')", name="content_version_origin"),
    )

    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_revision: Mapped[int | None] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(
        String(16), default=ContentVersionOrigin.SOURCE, nullable=False
    )
    incoming_package_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("incoming_package_versions.id", ondelete="RESTRICT"), unique=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=empty_object, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[UUID | None]
    change_reason: Mapped[str | None] = mapped_column(String(500))


class ContentCategory(Base):
    __tablename__ = "content_categories"
    __table_args__ = (Index("ix_content_categories_category_id", "category_id"),)

    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ContentTopic(Base):
    __tablename__ = "content_topics"
    __table_args__ = (Index("ix_content_topics_topic_id", "topic_id"),)

    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ContentEntity(Base):
    __tablename__ = "content_entities"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        Index("ix_content_entities_entity_id", "entity_id"),
    )

    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    relationship_type: Mapped[str] = mapped_column(String(64), default="mentioned", nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    source: Mapped[str | None] = mapped_column(String(120))


class ContentGeography(Base):
    __tablename__ = "content_geographies"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        CheckConstraint(
            "relationship_type IN ('primary', 'mentioned', 'event_location', "
            "'person_origin', 'team_location', 'venue_location')",
            name="content_geography_relationship",
        ),
        Index("ix_content_geographies_geography_id", "geography_id"),
    )

    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True
    )
    geography_id: Mapped[UUID] = mapped_column(
        ForeignKey("geography_nodes.id", ondelete="CASCADE"), primary_key=True
    )
    relationship_type: Mapped[ContentGeographyRelationship] = mapped_column(
        Enum(
            ContentGeographyRelationship,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=False,
            name="content_geography_relationship",
            validate_strings=True,
        ),
        primary_key=True,
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    source: Mapped[str | None] = mapped_column(String(120))
