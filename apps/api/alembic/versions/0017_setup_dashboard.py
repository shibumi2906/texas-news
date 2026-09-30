"""add encrypted portal integration settings

Revision ID: 0017_setup_dashboard
Revises: 0016_phase_15_ads_notifications
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_setup_dashboard"
down_revision: str | None = "0016_phase_15_ads_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portal_integrations",
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("secret_hint", sa.String(length=32), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("last_error", sa.String(length=64), nullable=True),
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
        sa.UniqueConstraint("portal_id", "kind", name="uq_portal_integrations_portal_kind"),
    )
    op.create_index("ix_portal_integrations_portal", "portal_integrations", ["portal_id"])


def downgrade() -> None:
    op.drop_index("ix_portal_integrations_portal", table_name="portal_integrations")
    op.drop_table("portal_integrations")
