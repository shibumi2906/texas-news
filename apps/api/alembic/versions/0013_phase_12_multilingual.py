"""add Phase 12 multilingual support

Revision ID: 0013_phase_12_multilingual
Revises: 0012_phase_11_ai_search_chat
Create Date: 2026-09-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_phase_12_multilingual"
down_revision: str | None = "0012_phase_11_ai_search_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "translations",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector((CASE WHEN split_part(language, '-', 1) = 'en' "
                "THEN 'english'::regconfig WHEN split_part(language, '-', 1) = 'es' "
                "THEN 'spanish'::regconfig ELSE 'simple'::regconfig END), "
                "coalesce(title, '')), 'A') || setweight(to_tsvector((CASE WHEN "
                "split_part(language, '-', 1) = 'en' THEN 'english'::regconfig WHEN "
                "split_part(language, '-', 1) = 'es' THEN 'spanish'::regconfig ELSE "
                "'simple'::regconfig END), coalesce(subtitle, '')), 'B') || "
                "setweight(to_tsvector((CASE WHEN split_part(language, '-', 1) = 'en' "
                "THEN 'english'::regconfig WHEN split_part(language, '-', 1) = 'es' "
                "THEN 'spanish'::regconfig ELSE 'simple'::regconfig END), "
                "coalesce(description, '')), 'B') || setweight(to_tsvector((CASE WHEN "
                "split_part(language, '-', 1) = 'en' THEN 'english'::regconfig WHEN "
                "split_part(language, '-', 1) = 'es' THEN 'spanish'::regconfig ELSE "
                "'simple'::regconfig END), coalesce(body, '')), 'D')",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("portal_id", sa.Uuid(), nullable=False),
        sa.Column("content_item_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=35), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("subtitle", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("translation_source", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
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
            "status IN ('machine', 'reviewed', 'editorial', 'outdated', 'failed')",
            name=op.f("ck_translations_translation_status"),
        ),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["portal_id"], ["portals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portal_id",
            "content_item_id",
            "language",
            name="uq_translations_portal_content_language",
        ),
    )
    op.create_index("ix_translations_content_item_id", "translations", ["content_item_id"])
    op.create_index("ix_translations_portal_language", "translations", ["portal_id", "language"])
    op.create_index(
        "ix_translations_search_vector", "translations", ["search_vector"], postgresql_using="gin"
    )
    op.execute(
        "CREATE TRIGGER search_changed AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE "
        "ON translations FOR EACH STATEMENT EXECUTE FUNCTION advance_search_generation()"
    )
    op.execute(
        "UPDATE portals SET supported_languages = CASE "
        "WHEN supported_languages ? 'es' THEN supported_languages "
        "ELSE supported_languages || '[\"es\"]'::jsonb END, "
        "feature_flags = feature_flags || '{\"multilingual\": true}'::jsonb "
        "WHERE slug = 'texas'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE portals SET supported_languages = "
        "COALESCE((SELECT jsonb_agg(value) FROM jsonb_array_elements(supported_languages) value "
        "WHERE value <> '\"es\"'::jsonb), '[]'::jsonb), "
        "feature_flags = feature_flags || '{\"multilingual\": false}'::jsonb "
        "WHERE slug = 'texas'"
    )
    op.execute("DROP TRIGGER search_changed ON translations")
    op.drop_index(
        "ix_translations_search_vector", table_name="translations", postgresql_using="gin"
    )
    op.drop_index("ix_translations_portal_language", table_name="translations")
    op.drop_index("ix_translations_content_item_id", table_name="translations")
    op.drop_table("translations")
