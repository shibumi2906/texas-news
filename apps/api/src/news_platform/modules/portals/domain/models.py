from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    empty_list,
    empty_object,
)


class PortalStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"


class Portal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "portals"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'inactive')", name="portal_status"),
    )

    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[PortalStatus] = mapped_column(
        Enum(
            PortalStatus,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=False,
            name="portal_status",
            validate_strings=True,
        ),
        default=PortalStatus.DRAFT,
        nullable=False,
    )
    primary_geography_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("geography_nodes.id", ondelete="SET NULL"), index=True
    )
    default_language: Mapped[str] = mapped_column(String(35), nullable=False)
    supported_languages: Mapped[list[str]] = mapped_column(
        JSONB, default=empty_list, nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    branding: Mapped[dict[str, Any]] = mapped_column(JSONB, default=empty_object, nullable=False)
    logo: Mapped[str | None] = mapped_column(Text)
    category_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=empty_object, nullable=False
    )
    ranking_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=empty_object, nullable=False
    )
    ai_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=empty_object, nullable=False)
    advertising_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=empty_object, nullable=False
    )
    seo_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=empty_object, nullable=False
    )
    feature_flags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=empty_object, nullable=False
    )
