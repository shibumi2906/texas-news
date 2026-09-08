"""add Phase 7 behavioral events and aggregation receipts

Revision ID: 0008_phase_7_analytics
Revises: 0007_phase_6_search
Create Date: 2026-09-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_phase_7_analytics"
down_revision: str | None = "0007_phase_6_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENT_TYPES = (
    "impression",
    "click",
    "content_open",
    "scroll",
    "video_start",
    "watch_time",
    "completion",
    "share",
    "search",
)


def upgrade() -> None:
    op.create_table(
        "behavior_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("anonymous_id", sa.String(length=128), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("content_id", sa.Uuid(), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("geography_id", sa.Uuid(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "event_type IN (" + ", ".join(f"'{value}'" for value in EVENT_TYPES) + ")",
            name=op.f("ck_behavior_events_event_type"),
        ),
        sa.CheckConstraint(
            "user_id IS NOT NULL OR anonymous_id IS NOT NULL",
            name=op.f("ck_behavior_events_actor_identity"),
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["content_items.id"],
            name=op.f("fk_behavior_events_content_id_content_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name=op.f("fk_behavior_events_entity_id_entities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["geography_id"],
            ["geography_nodes.id"],
            name=op.f("fk_behavior_events_geography_id_geography_nodes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portal_id"],
            ["portals.id"],
            name=op.f("fk_behavior_events_portal_id_portals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_behavior_events")),
    )
    op.create_index(
        "ix_behavior_events_portal_timestamp",
        "behavior_events",
        ["portal_id", "timestamp"],
    )
    op.create_index(
        "ix_behavior_events_content_timestamp",
        "behavior_events",
        ["content_id", "timestamp"],
    )
    op.create_table(
        "behavior_event_aggregations",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "aggregated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ranking_changed", sa.Boolean(), nullable=False),
        sa.Column("feed_invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["behavior_events.id"],
            name=op.f("fk_behavior_event_aggregations_event_id_behavior_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_behavior_event_aggregations")),
    )
    op.create_index(
        "ix_behavior_event_aggregations_pending_invalidation",
        "behavior_event_aggregations",
        ["feed_invalidated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_behavior_event_aggregations_pending_invalidation",
        table_name="behavior_event_aggregations",
    )
    op.drop_table("behavior_event_aggregations")
    op.drop_index("ix_behavior_events_content_timestamp", table_name="behavior_events")
    op.drop_index("ix_behavior_events_portal_timestamp", table_name="behavior_events")
    op.drop_table("behavior_events")
