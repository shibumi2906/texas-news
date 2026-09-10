from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import UUIDPrimaryKeyMixin


class PersonalizationTargetType(StrEnum):
    CATEGORY = "category"
    TOPIC = "topic"
    ENTITY = "entity"
    GEOGRAPHY = "geography"


class AffinityTargetType(StrEnum):
    CATEGORY = "category"
    ENTITY = "entity"
    GEOGRAPHY = "geography"


class UserInterest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_interests"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('category', 'topic', 'entity', 'geography')", name="target_type"
        ),
        CheckConstraint("weight BETWEEN 1 AND 5", name="weight"),
        UniqueConstraint(
            "portal_id", "user_id", "target_type", "target_id", name="uq_user_interests_target"
        ),
        Index("ix_user_interests_owner", "portal_id", "user_id"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[UUID] = mapped_column(nullable=False)
    weight: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserAffinity(Base):
    __tablename__ = "user_affinities"
    __table_args__ = (
        CheckConstraint("target_type IN ('category', 'entity', 'geography')", name="target_type"),
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        Index("ix_user_affinities_owner", "portal_id", "user_id"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    target_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    target_id: Mapped[UUID] = mapped_column(primary_key=True)
    score: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecommendationSignalReceipt(Base):
    __tablename__ = "recommendation_signal_receipts"

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("behavior_events.id", ondelete="CASCADE"), primary_key=True
    )
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RecommendationGeneration(Base):
    __tablename__ = "recommendation_generations"

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    generation: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
