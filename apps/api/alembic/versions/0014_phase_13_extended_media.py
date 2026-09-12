"""add Phase 13 ordered media

Revision ID: 0014_phase_13_extended_media
Revises: 0013_phase_12_multilingual
Create Date: 2026-09-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_phase_13_extended_media"
down_revision: str | None = "0013_phase_12_multilingual"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_media_assets_position_nonnegative"),
        "media_assets",
        "position >= 0",
    )
    op.create_index(
        "ix_media_assets_content_position",
        "media_assets",
        ["content_item_id", "position", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_media_assets_content_position", table_name="media_assets")
    op.drop_constraint(op.f("ck_media_assets_position_nonnegative"), "media_assets", type_="check")
    op.drop_column("media_assets", "position")
