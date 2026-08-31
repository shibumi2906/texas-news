from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import UUIDPrimaryKeyMixin, empty_object


class EditorialAuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "editorial_audit_logs"
    __table_args__ = (
        Index("ix_editorial_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_editorial_audit_logs_timestamp", "timestamp"),
    )

    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    before: Mapped[dict[str, Any]] = mapped_column(JSONB, default=empty_object, nullable=False)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB, default=empty_object, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
