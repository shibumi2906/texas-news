from __future__ import annotations

from datetime import datetime
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
from news_platform.modules.common import TimestampMixin, UUIDPrimaryKeyMixin, empty_list


class AdPlacement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ad_placements"
    __table_args__ = (
        UniqueConstraint("portal_id", "code", name="uq_ad_placements_portal_code"),
        Index("ix_ad_placements_portal_active", "portal_id", "active"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    allowed_content_types: Mapped[list[str]] = mapped_column(
        JSONB, default=empty_list, nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AdCampaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ad_campaigns"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'paused', 'ended')", name="status"),
        CheckConstraint("priority BETWEEN 0 AND 1000", name="priority_range"),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="date_range"),
        Index("ix_ad_campaigns_portal_status_window", "portal_id", "status", "starts_at"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdCreative(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ad_creatives"
    __table_args__ = (
        CheckConstraint("format IN ('image', 'html', 'text')", name="format"),
        Index("ix_ad_creatives_campaign", "campaign_id", "active"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("ad_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_url: Mapped[str | None] = mapped_column(Text)
    click_url: Mapped[str] = mapped_column(Text, nullable=False)
    alt_text: Mapped[str] = mapped_column(String(300), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AdTargeting(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ad_targeting"

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("ad_campaigns.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    placement_codes: Mapped[list[str]] = mapped_column(JSONB, default=empty_list, nullable=False)
    geography_ids: Mapped[list[str]] = mapped_column(JSONB, default=empty_list, nullable=False)
    languages: Mapped[list[str]] = mapped_column(JSONB, default=empty_list, nullable=False)
    category_ids: Mapped[list[str]] = mapped_column(JSONB, default=empty_list, nullable=False)
    content_types: Mapped[list[str]] = mapped_column(JSONB, default=empty_list, nullable=False)


class AdImpression(Base):
    __tablename__ = "ad_impressions"
    __table_args__ = (Index("ix_ad_impressions_portal_occurred", "portal_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="RESTRICT"), nullable=False
    )
    placement_id: Mapped[UUID] = mapped_column(
        ForeignKey("ad_placements.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("ad_campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    creative_id: Mapped[UUID] = mapped_column(
        ForeignKey("ad_creatives.id", ondelete="RESTRICT"), nullable=False
    )
    content_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="RESTRICT")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdClick(Base):
    __tablename__ = "ad_clicks"
    __table_args__ = (Index("ix_ad_clicks_portal_occurred", "portal_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="RESTRICT"), nullable=False
    )
    impression_id: Mapped[UUID] = mapped_column(
        ForeignKey("ad_impressions.id", ondelete="RESTRICT"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
