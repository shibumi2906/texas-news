from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import TimestampMixin, UUIDPrimaryKeyMixin, empty_object


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    THUMBNAIL = "thumbnail"
    POSTER = "poster"
    DOCUMENT = "document"


class MediaStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    INACTIVE = "inactive"


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            "type IN ('image', 'video', 'audio', 'thumbnail', 'poster', 'document')",
            name="media_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed', 'inactive')", name="media_status"
        ),
        CheckConstraint("width IS NULL OR width >= 0", name="width_nonnegative"),
        CheckConstraint("height IS NULL OR height >= 0", name="height_nonnegative"),
        CheckConstraint("duration IS NULL OR duration >= 0", name="duration_nonnegative"),
        CheckConstraint("size IS NULL OR size >= 0", name="size_nonnegative"),
    )

    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[MediaType] = mapped_column(
        Enum(
            MediaType,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=False,
            name="media_type",
            validate_strings=True,
        ),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    storage_url: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[float | None] = mapped_column(Numeric(12, 3))
    size: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(128), index=True)
    copyright: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=empty_object, nullable=False
    )
    status: Mapped[MediaStatus] = mapped_column(
        Enum(
            MediaStatus,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=False,
            name="media_status",
            validate_strings=True,
        ),
        default=MediaStatus.PENDING,
        nullable=False,
    )
