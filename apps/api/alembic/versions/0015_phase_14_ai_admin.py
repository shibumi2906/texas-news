"""add portal-scoped AI administration

Revision ID: 0015_phase_14_ai_admin
Revises: 0014_phase_13_extended_media
Create Date: 2026-09-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_phase_14_ai_admin"
down_revision: str | None = "0014_phase_13_extended_media"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("uq_ai_prompt_definitions_task"), "ai_prompt_definitions", type_="unique"
    )
    op.add_column(
        "ai_prompt_definitions",
        sa.Column("portal_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_ai_prompt_definitions_portal_id_portals"),
        "ai_prompt_definitions",
        "portals",
        ["portal_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_ai_prompt_definitions_global_task",
        "ai_prompt_definitions",
        ["task"],
        unique=True,
        postgresql_where=sa.text("portal_id IS NULL"),
    )
    op.create_index(
        "uq_ai_prompt_definitions_portal_task",
        "ai_prompt_definitions",
        ["portal_id", "task"],
        unique=True,
        postgresql_where=sa.text("portal_id IS NOT NULL"),
    )
    op.create_table(
        "ai_task_configs",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.String(length=120), nullable=False),
        sa.Column("primary_model", sa.String(length=255), nullable=False),
        sa.Column("fallback_models", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowed_providers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("max_cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("max_input_tokens", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Numeric(6, 2), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("max_cost >= 0", name=op.f("ck_ai_task_configs_max_cost_nonnegative")),
        sa.CheckConstraint(
            "max_input_tokens >= 128",
            name=op.f("ck_ai_task_configs_max_input_tokens_minimum"),
        ),
        sa.CheckConstraint(
            "max_output_tokens >= 32",
            name=op.f("ck_ai_task_configs_max_output_tokens_minimum"),
        ),
        sa.CheckConstraint(
            "max_retries BETWEEN 0 AND 5", name=op.f("ck_ai_task_configs_max_retries_range")
        ),
        sa.CheckConstraint(
            "timeout_seconds > 0 AND timeout_seconds <= 120",
            name=op.f("ck_ai_task_configs_timeout_range"),
        ),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portal_id", "task", name="uq_ai_task_configs_portal_task"),
    )
    op.create_index("ix_ai_task_configs_portal", "ai_task_configs", ["portal_id"])
    op.create_table(
        "ai_experiments",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("prompt_version_a_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version_b_id", sa.Uuid(), nullable=False),
        sa.Column("variant_b_percent", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'paused')", name=op.f("ck_ai_experiments_status")
        ),
        sa.CheckConstraint(
            "variant_b_percent BETWEEN 1 AND 99",
            name=op.f("ck_ai_experiments_variant_b_percent_range"),
        ),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["prompt_version_a_id"], ["ai_prompt_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_b_id"], ["ai_prompt_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portal_id", "task", name="uq_ai_experiments_portal_task"),
    )
    op.create_index("ix_ai_experiments_portal_status", "ai_experiments", ["portal_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_ai_experiments_portal_status", table_name="ai_experiments")
    op.drop_table("ai_experiments")
    op.drop_index("ix_ai_task_configs_portal", table_name="ai_task_configs")
    op.drop_table("ai_task_configs")
    op.execute("DELETE FROM ai_prompt_definitions WHERE portal_id IS NOT NULL")
    op.drop_index("uq_ai_prompt_definitions_portal_task", table_name="ai_prompt_definitions")
    op.drop_index("uq_ai_prompt_definitions_global_task", table_name="ai_prompt_definitions")
    op.drop_constraint(
        op.f("fk_ai_prompt_definitions_portal_id_portals"),
        "ai_prompt_definitions",
        type_="foreignkey",
    )
    op.drop_column("ai_prompt_definitions", "portal_id")
    op.create_unique_constraint(
        op.f("uq_ai_prompt_definitions_task"), "ai_prompt_definitions", ["task"]
    )
