from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import UUIDPrimaryKeyMixin


class EngagementMetric(StrEnum):
    IMPRESSIONS = "impressions"
    CLICKS = "clicks"
    VIEWS = "views"
    COMMENTS = "comments"
    LIKES = "likes"
    SHARES = "shares"
    SAVES = "saves"
    WATCH_TIME_SECONDS = "watch_time_seconds"
    COMPLETIONS = "completions"


COUNTER_COLUMNS = tuple(metric.value for metric in EngagementMetric)


class ContentEngagementCounter(Base):
    __tablename__ = "content_engagement_counters"
    __table_args__ = tuple(
        CheckConstraint(f"{column} >= 0", name=f"{column}_non_negative")
        for column in COUNTER_COLUMNS
    )

    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True
    )
    impressions: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    clicks: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    views: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    comments: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    likes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    shares: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    saves: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    watch_time_seconds: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    completions: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EngagementCounterUpdate(UUIDPrimaryKeyMixin, Base):
    """Minimal deduplication receipt, not a Phase 7 behavioral-event record."""

    __tablename__ = "engagement_counter_updates"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_engagement_counter_updates_content_item_id", "content_item_id"),
    )

    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
