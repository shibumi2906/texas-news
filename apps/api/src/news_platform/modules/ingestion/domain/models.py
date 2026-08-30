from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import TimestampMixin, UUIDPrimaryKeyMixin


class IncomingOperation(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    CORRECTED = "corrected"
    RETRACTED = "retracted"
    DELETED = "deleted"


class IntegratorConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integrator_connections"
    __table_args__ = (
        CheckConstraint(
            "previous_key_id IS NULL OR previous_key_id <> active_key_id",
            name="distinct_signing_key_ids",
        ),
    )

    instance_id: Mapped[UUID] = mapped_column(unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    active_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    active_secret: Mapped[str] = mapped_column(Text, nullable=False)
    previous_key_id: Mapped[str | None] = mapped_column(String(64))
    previous_secret: Mapped[str | None] = mapped_column(Text)


class IncomingPackage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "incoming_packages"
    __table_args__ = (
        CheckConstraint("latest_version > 0", name="latest_version_positive"),
        UniqueConstraint("package_id", name="uq_incoming_packages_package_id"),
    )

    package_id: Mapped[UUID] = mapped_column(nullable=False)
    integrator_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("integrator_connections.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    content_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="RESTRICT"), unique=True
    )
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False)


class IncomingPackageVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "incoming_package_versions"
    __table_args__ = (
        CheckConstraint("package_version > 0", name="package_version_positive"),
        CheckConstraint("schema_version IN ('1.0', '1.1')", name="supported_schema_version"),
        CheckConstraint(
            "operation IN ('created', 'updated', 'corrected', 'retracted', 'deleted')",
            name="incoming_operation",
        ),
        UniqueConstraint(
            "package_id", "package_version", name="uq_incoming_package_versions_identity"
        ),
        UniqueConstraint("event_id", name="uq_incoming_package_versions_event_id"),
        Index("ix_incoming_package_versions_received_at", "received_at"),
    )

    incoming_package_id: Mapped[UUID] = mapped_column(
        ForeignKey("incoming_packages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    package_id: Mapped[UUID] = mapped_column(nullable=False)
    package_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    instance_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    event_id: Mapped[UUID] = mapped_column(nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    revision_reason: Mapped[str | None] = mapped_column(Text)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
