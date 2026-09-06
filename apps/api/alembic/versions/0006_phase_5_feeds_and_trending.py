"""add Phase 5 engagement counters

Revision ID: 0006_phase_5_feeds
Revises: 0005_phase_4_public_site
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_phase_5_feeds"
down_revision: str | None = "0005_phase_4_public_site"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COUNTERS = (
    "impressions",
    "clicks",
    "views",
    "comments",
    "likes",
    "shares",
    "saves",
    "watch_time_seconds",
    "completions",
)


def upgrade() -> None:
    op.create_table(
        "content_engagement_counters",
        sa.Column("content_item_id", sa.Uuid(), nullable=False),
        *(
            sa.Column(name, sa.BigInteger(), server_default="0", nullable=False)
            for name in COUNTERS
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *(
            sa.CheckConstraint(
                f"{name} >= 0",
                name=op.f(f"ck_content_engagement_counters_{name}_non_negative"),
            )
            for name in COUNTERS
        ),
        sa.ForeignKeyConstraint(
            ["content_item_id"],
            ["content_items.id"],
            name=op.f("fk_content_engagement_counters_content_item_id_content_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("content_item_id", name=op.f("pk_content_engagement_counters")),
    )
    op.create_table(
        "engagement_counter_updates",
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("content_item_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "amount > 0", name=op.f("ck_engagement_counter_updates_amount_positive")
        ),
        sa.ForeignKeyConstraint(
            ["content_item_id"],
            ["content_items.id"],
            name=op.f("fk_engagement_counter_updates_content_item_id_content_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_engagement_counter_updates")),
        sa.UniqueConstraint(
            "idempotency_key",
            name=op.f("uq_engagement_counter_updates_idempotency_key"),
        ),
    )
    op.create_index(
        op.f("ix_engagement_counter_updates_content_item_id"),
        "engagement_counter_updates",
        ["content_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_engagement_counter_updates_content_item_id",
        table_name="engagement_counter_updates",
    )
    op.drop_table("engagement_counter_updates")
    op.drop_table("content_engagement_counters")
