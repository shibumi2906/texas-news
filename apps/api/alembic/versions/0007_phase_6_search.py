"""PostgreSQL search index and transactional ranking generation."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_phase_6_search"
down_revision: str | None = "0006_phase_5_feeds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VECTOR = (
    "setweight(to_tsvector((CASE WHEN split_part(primary_language, '-', 1) = "
    "'en' THEN 'english'::regconfig WHEN split_part(primary_language, '-', 1) = "
    "'es' THEN 'spanish'::regconfig ELSE 'simple'::regconfig END), "
    "coalesce(title, '')), 'A') || setweight(to_tsvector((CASE WHEN "
    "split_part(primary_language, '-', 1) = 'en' THEN 'english'::regconfig WHEN "
    "split_part(primary_language, '-', 1) = 'es' THEN 'spanish'::regconfig ELSE "
    "'simple'::regconfig END), coalesce(subtitle, '')), 'B') || "
    "setweight(to_tsvector((CASE WHEN split_part(primary_language, '-', 1) = "
    "'en' THEN 'english'::regconfig WHEN split_part(primary_language, '-', 1) = "
    "'es' THEN 'spanish'::regconfig ELSE 'simple'::regconfig END), "
    "coalesce(description, '')), 'B') || setweight(to_tsvector((CASE WHEN "
    "split_part(primary_language, '-', 1) = 'en' THEN 'english'::regconfig WHEN "
    "split_part(primary_language, '-', 1) = 'es' THEN 'spanish'::regconfig ELSE "
    "'simple'::regconfig END), coalesce(body, '')), 'D')"
)
TABLES = (
    "content_items",
    "content_categories",
    "content_geographies",
    "content_entities",
    "entities",
    "categories",
    "geography_nodes",
    "portals",
)


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(VECTOR, persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_content_items_search_vector", "content_items", ["search_vector"], postgresql_using="gin"
    )
    op.create_table(
        "search_generation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("id = 1", name="singleton"),
    )
    op.execute("INSERT INTO search_generation VALUES (1, 0)")
    op.execute("""CREATE FUNCTION advance_search_generation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        UPDATE search_generation SET generation = generation + 1 WHERE id = 1;
        RETURN NULL; END $$""")
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER search_changed AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE "
            f"ON {table} FOR EACH STATEMENT EXECUTE FUNCTION advance_search_generation()"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TRIGGER search_changed ON {table}")
    op.execute("DROP FUNCTION advance_search_generation()")
    op.drop_table("search_generation")
    op.drop_index("ix_content_items_search_vector", table_name="content_items")
    op.drop_column("content_items", "search_vector")
