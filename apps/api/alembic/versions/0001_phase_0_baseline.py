"""Create the Phase 0 schema baseline.

Revision ID: 0001_phase_0_baseline
Revises:
Create Date: 2026-08-29
"""

from collections.abc import Sequence

revision: str = "0001_phase_0_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish a migration head without creating Phase 1 domain tables."""


def downgrade() -> None:
    """Remove the empty Phase 0 baseline."""
