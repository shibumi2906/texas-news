from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import TimestampMixin, UUIDPrimaryKeyMixin


class TranslationStatus(StrEnum):
    MACHINE = "machine"
    REVIEWED = "reviewed"
    EDITORIAL = "editorial"
    OUTDATED = "outdated"
    FAILED = "failed"


PUBLIC_TRANSLATION_STATUSES = (
    TranslationStatus.MACHINE,
    TranslationStatus.REVIEWED,
    TranslationStatus.EDITORIAL,
)


def translation_status_enum() -> Enum:
    return Enum(
        TranslationStatus,
        values_callable=lambda values: [value.value for value in values],
        native_enum=False,
        create_constraint=False,
        name="translation_status",
        length=16,
        validate_strings=True,
    )


class Translation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "translations"
    __table_args__ = (
        UniqueConstraint(
            "portal_id",
            "content_item_id",
            "language",
            name="uq_translations_portal_content_language",
        ),
        CheckConstraint(
            "status IN ('machine', 'reviewed', 'editorial', 'outdated', 'failed')",
            name="translation_status",
        ),
        Index("ix_translations_content_item_id", "content_item_id"),
        Index("ix_translations_portal_language", "portal_id", "language"),
        Index("ix_translations_search_vector", "search_vector", postgresql_using="gin"),
    )

    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector((CASE WHEN split_part(language, '-', 1) = 'en' "
            "THEN 'english'::regconfig WHEN split_part(language, '-', 1) = 'es' "
            "THEN 'spanish'::regconfig ELSE 'simple'::regconfig END), "
            "coalesce(title, '')), 'A') || "
            "setweight(to_tsvector((CASE WHEN split_part(language, '-', 1) = 'en' "
            "THEN 'english'::regconfig WHEN split_part(language, '-', 1) = 'es' "
            "THEN 'spanish'::regconfig ELSE 'simple'::regconfig END), "
            "coalesce(subtitle, '')), 'B') || "
            "setweight(to_tsvector((CASE WHEN split_part(language, '-', 1) = 'en' "
            "THEN 'english'::regconfig WHEN split_part(language, '-', 1) = 'es' "
            "THEN 'spanish'::regconfig ELSE 'simple'::regconfig END), "
            "coalesce(description, '')), 'B') || "
            "setweight(to_tsvector((CASE WHEN split_part(language, '-', 1) = 'en' "
            "THEN 'english'::regconfig WHEN split_part(language, '-', 1) = 'es' "
            "THEN 'spanish'::regconfig ELSE 'simple'::regconfig END), coalesce(body, '')), 'D')",
            persisted=True,
        ),
    )
    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(35), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    translation_source: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[TranslationStatus] = mapped_column(translation_status_enum(), nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
