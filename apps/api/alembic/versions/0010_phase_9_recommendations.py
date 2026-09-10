"""add Phase 9 recommendations and personalization

Revision ID: 0010_phase_9_recommendations
Revises: 0009_phase_8_users_community
Create Date: 2026-09-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_phase_9_recommendations"
down_revision: str | None = "0009_phase_8_users_community"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        op.f("fk_behavior_events_user_id_users"),
        "behavior_events",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "recommendation_generations",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["portal_id"],
            ["portals.id"],
            name=op.f("fk_recommendation_generations_portal_id_portals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recommendation_generations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("portal_id", "user_id", name=op.f("pk_recommendation_generations")),
    )
    op.create_table(
        "user_interests",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('category', 'topic', 'entity', 'geography')",
            name=op.f("ck_user_interests_target_type"),
        ),
        sa.CheckConstraint("weight BETWEEN 1 AND 5", name=op.f("ck_user_interests_weight")),
        sa.ForeignKeyConstraint(
            ["portal_id"],
            ["portals.id"],
            name=op.f("fk_user_interests_portal_id_portals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_interests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_interests")),
        sa.UniqueConstraint(
            "portal_id", "user_id", "target_type", "target_id", name="uq_user_interests_target"
        ),
    )
    op.create_index("ix_user_interests_owner", "user_interests", ["portal_id", "user_id"])
    op.create_table(
        "user_affinities",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('category', 'entity', 'geography')",
            name=op.f("ck_user_affinities_target_type"),
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 100", name=op.f("ck_user_affinities_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["portal_id"],
            ["portals.id"],
            name=op.f("fk_user_affinities_portal_id_portals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_affinities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "portal_id", "user_id", "target_type", "target_id", name=op.f("pk_user_affinities")
        ),
    )
    op.create_index("ix_user_affinities_owner", "user_affinities", ["portal_id", "user_id"])
    op.create_table(
        "recommendation_signal_receipts",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["behavior_events.id"],
            name=op.f("fk_recommendation_signal_receipts_event_id_behavior_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_recommendation_signal_receipts")),
    )
    op.execute(
        "UPDATE portals SET feature_flags = feature_flags || "
        '\'{"recommendations": true, "personalization": true}\'::jsonb'
    )


def downgrade() -> None:
    op.drop_table("recommendation_signal_receipts")
    op.drop_index("ix_user_affinities_owner", table_name="user_affinities")
    op.drop_table("user_affinities")
    op.drop_index("ix_user_interests_owner", table_name="user_interests")
    op.drop_table("user_interests")
    op.drop_table("recommendation_generations")
    op.drop_constraint(
        op.f("fk_behavior_events_user_id_users"), "behavior_events", type_="foreignkey"
    )
