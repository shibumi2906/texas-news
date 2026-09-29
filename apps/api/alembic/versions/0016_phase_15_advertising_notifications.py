"""add advertising and notifications

Revision ID: 0016_phase_15_ads_notifications
Revises: 0015_phase_14_ai_admin
Create Date: 2026-09-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_phase_15_ads_notifications"
down_revision: str | None = "0015_phase_14_ai_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ad_placements",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("allowed_content_types", postgresql.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portal_id", "code", name="uq_ad_placements_portal_code"),
    )
    op.create_index("ix_ad_placements_portal_active", "ad_placements", ["portal_id", "active"])
    op.create_table(
        "ad_campaigns",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at", name=op.f("ck_ad_campaigns_date_range")
        ),
        sa.CheckConstraint(
            "priority BETWEEN 0 AND 1000", name=op.f("ck_ad_campaigns_priority_range")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'ended')", name=op.f("ck_ad_campaigns_status")
        ),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ad_campaigns_portal_status_window", "ad_campaigns", ["portal_id", "status", "starts_at"]
    )
    op.create_table(
        "ad_creatives",
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("asset_url", sa.Text(), nullable=True),
        sa.Column("click_url", sa.Text(), nullable=False),
        sa.Column("alt_text", sa.String(length=300), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "format IN ('image', 'html', 'text')", name=op.f("ck_ad_creatives_format")
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["ad_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ad_creatives_campaign", "ad_creatives", ["campaign_id", "active"])
    op.create_table(
        "ad_targeting",
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("placement_codes", postgresql.JSONB(), nullable=False),
        sa.Column("geography_ids", postgresql.JSONB(), nullable=False),
        sa.Column("languages", postgresql.JSONB(), nullable=False),
        sa.Column("category_ids", postgresql.JSONB(), nullable=False),
        sa.Column("content_types", postgresql.JSONB(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["ad_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id"),
    )
    op.create_table(
        "ad_impressions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("placement_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("creative_id", sa.Uuid(), nullable=False),
        sa.Column("content_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["ad_campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["content_id"], ["content_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creative_id"], ["ad_creatives.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["placement_id"], ["ad_placements.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ad_impressions_portal_occurred", "ad_impressions", ["portal_id", "occurred_at"]
    )
    op.create_table(
        "ad_clicks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("impression_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["impression_id"], ["ad_impressions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ad_clicks_portal_occurred", "ad_clicks", ["portal_id", "occurred_at"])

    op.create_table(
        "notification_subscriptions",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("destination_hash", sa.String(length=64), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "channel IN ('email', 'web_push')", name=op.f("ck_notification_subscriptions_channel")
        ),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portal_id",
            "user_id",
            "channel",
            "destination_hash",
            name="uq_notification_subscriptions_destination",
        ),
    )
    op.create_index(
        "ix_notification_subscriptions_portal_enabled",
        "notification_subscriptions",
        ["portal_id", "enabled"],
    )
    op.create_table(
        "notification_messages",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("content_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=1000), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("channels", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["content_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_messages_portal_created",
        "notification_messages",
        ["portal_id", "created_at"],
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "attempts >= 0", name=op.f("ck_notification_deliveries_attempts_nonnegative")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name=op.f("ck_notification_deliveries_status"),
        ),
        sa.ForeignKeyConstraint(["message_id"], ["notification_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["notification_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id", "subscription_id", name="uq_notification_deliveries_message_subscription"
        ),
    )
    op.create_index(
        "ix_notification_deliveries_pending",
        "notification_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_pending", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index("ix_notification_messages_portal_created", table_name="notification_messages")
    op.drop_table("notification_messages")
    op.drop_index(
        "ix_notification_subscriptions_portal_enabled", table_name="notification_subscriptions"
    )
    op.drop_table("notification_subscriptions")
    op.drop_index("ix_ad_clicks_portal_occurred", table_name="ad_clicks")
    op.drop_table("ad_clicks")
    op.drop_index("ix_ad_impressions_portal_occurred", table_name="ad_impressions")
    op.drop_table("ad_impressions")
    op.drop_table("ad_targeting")
    op.drop_index("ix_ad_creatives_campaign", table_name="ad_creatives")
    op.drop_table("ad_creatives")
    op.drop_index("ix_ad_campaigns_portal_status_window", table_name="ad_campaigns")
    op.drop_table("ad_campaigns")
    op.drop_index("ix_ad_placements_portal_active", table_name="ad_placements")
    op.drop_table("ad_placements")
