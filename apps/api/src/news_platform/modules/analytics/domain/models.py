from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import empty_object


class BehaviorEventType(StrEnum):
    IMPRESSION = "impression"
    CLICK = "click"
    CONTENT_OPEN = "content_open"
    SCROLL = "scroll"
    VIDEO_START = "video_start"
    WATCH_TIME = "watch_time"
    COMPLETION = "completion"
    SHARE = "share"
    SEARCH = "search"
    LIKE = "like"
    REACTION = "reaction"
    COMMENT = "comment"
    SAVE = "save"
    FOLLOW = "follow"


EVENT_TYPES = tuple(event_type.value for event_type in BehaviorEventType)


class BehaviorEvent(Base):
    """Immutable client event; processing state lives in a separate table."""

    __tablename__ = "behavior_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN (" + ", ".join(f"'{value}'" for value in EVENT_TYPES) + ")",
            name="event_type",
        ),
        CheckConstraint(
            "user_id IS NOT NULL OR anonymous_id IS NOT NULL",
            name="actor_identity",
        ),
        Index("ix_behavior_events_portal_timestamp", "portal_id", "timestamp"),
        Index("ix_behavior_events_content_timestamp", "content_id", "timestamp"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID | None]
    anonymous_id: Mapped[str | None] = mapped_column(String(128))
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="RESTRICT")
    )
    entity_id: Mapped[UUID | None] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"))
    geography_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("geography_nodes.id", ondelete="RESTRICT")
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=empty_object, nullable=False)


class BehaviorEventAggregation(Base):
    """Exactly-once processing receipt and durable Redis invalidation outbox."""

    __tablename__ = "behavior_event_aggregations"
    __table_args__ = (
        Index(
            "ix_behavior_event_aggregations_pending_invalidation",
            "feed_invalidated_at",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("behavior_events.id", ondelete="CASCADE"), primary_key=True
    )
    aggregated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ranking_changed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    feed_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
