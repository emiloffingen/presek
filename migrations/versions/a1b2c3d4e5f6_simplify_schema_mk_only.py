"""simplify schema for mk-only minimal ai

Revision ID: a1b2c3d4e5f6
Revises: f631fc2a7880
Create Date: 2026-09-17 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f631fc2a7880"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _safe_execute(sql: str) -> None:
    """Execute raw SQL inside a DO block that swallows errors.

    Alembic wraps each migration in a single transaction, so a failed
    statement aborts the entire transaction on PostgreSQL.  Wrapping in a
    PL/pgSQL block lets us ignore errors from columns/tables that don't
    exist yet on this branch.
    """
    op.execute(
        f"DO $$ BEGIN {sql}; "
        "EXCEPTION WHEN undefined_column OR undefined_table "
        "OR undefined_object THEN NULL; END $$"
    )


def upgrade() -> None:
    """Simplify schema for MK-only minimal AI version."""

    # Drop tables that are no longer needed
    tables_to_drop = [
        "feed_sources",
        "cluster_summary_history",
        "cluster_entities",
        "knowledge_entities",
        "knowledge_relationships",
        "entity_mentions_daily",
        "entity_knowledge",
        "storylines_v2",
        "storyline_clusters_v2",
        "synced_reader_profiles",
        "synced_delivery_subscriptions",
        "suggestion_surface_events",
        "daily_briefings",
        "saved_insights",
    ]

    for table in tables_to_drop:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # Remove Serbian data (safe even if columns don't exist on this branch)
    _safe_execute("DELETE FROM sources WHERE country = 'RS'")
    _safe_execute("DELETE FROM cluster_summaries WHERE lang = 'sr'")
    _safe_execute("DELETE FROM subscribers WHERE locale = 'sr'")

    # Drop columns that are no longer needed
    _safe_execute("ALTER TABLE articles DROP COLUMN embedding")
    _safe_execute("ALTER TABLE cluster_metadata DROP COLUMN centroid")
    _safe_execute("ALTER TABLE cluster_summaries DROP COLUMN lang")
    _safe_execute("ALTER TABLE subscribers DROP COLUMN locale")

    # Remove vector indexes if they exist
    op.execute("DROP INDEX IF EXISTS idx_articles_embedding")
    op.execute("DROP INDEX IF EXISTS idx_cluster_metadata_centroid")
    op.execute("DROP INDEX IF EXISTS idx_storylines_centroid")


def downgrade() -> None:
    """Revert schema changes (not recommended - data will be lost)."""
    raise NotImplementedError("This migration is not reversible - restore from backup")
