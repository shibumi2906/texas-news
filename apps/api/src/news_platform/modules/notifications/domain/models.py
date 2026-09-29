from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
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
from news_platform.modules.common import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    empty_list,
    empty_object,
)


class NotificationSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_subscriptions"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'web_push')", name="channel"),
        UniqueConstraint(
            "portal_id",
            "user_id",
            "channel",
            "destination_hash",
            name="uq_notification_subscriptions_destination",
        ),
        Index("ix_notification_subscriptions_portal_enabled", "portal_id", "enabled"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    destination_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=empty_object, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notification_messages"
    __table_args__ = (Index("ix_notification_messages_portal_created", "portal_id", "created_at"),)

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSONB, default=empty_list, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationDelivery(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'failed')", name="status"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        UniqueConstraint(
            "message_id", "subscription_id", name="uq_notification_deliveries_message_subscription"
        ),
        Index("ix_notification_deliveries_pending", "status", "next_attempt_at"),
    )

    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("notification_messages.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("notification_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
