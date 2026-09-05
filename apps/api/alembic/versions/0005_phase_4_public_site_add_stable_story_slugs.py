"""add stable story slugs for the Phase 4 public site

Revision ID: 0005_phase_4_public_site
Revises: 0004_phase_3_editorial
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_phase_4_public_site"
down_revision: str | None = "0004_phase_3_editorial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("slug", sa.String(length=220), nullable=True))
    op.execute("UPDATE content_items SET slug = 'story-' || replace(id::text, '-', '')")
    op.alter_column("content_items", "slug", nullable=False)
    op.create_unique_constraint(op.f("uq_content_items_slug"), "content_items", ["slug"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_content_items_slug"), "content_items", type_="unique")
    op.drop_column("content_items", "slug")
