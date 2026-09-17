"""simplify schema for mk-only minimal ai

Revision ID: a1b2c3d4e5f6
Revises: f631fc2a7880
Create Date: 2026-09-17 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f631fc2a7880"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    
    # Drop columns that are no longer needed
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE cluster_metadata DROP COLUMN IF EXISTS centroid")
    op.execute("ALTER TABLE cluster_summaries DROP COLUMN IF EXISTS lang")
    op.execute("ALTER TABLE subscribers DROP COLUMN IF EXISTS locale")
    
    # Remove vector indexes if they exist
    op.execute("DROP INDEX IF EXISTS idx_articles_embedding")
    op.execute("DROP INDEX IF EXISTS idx_cluster_metadata_centroid")
    op.execute("DROP INDEX IF EXISTS idx_storylines_centroid")
    
    # Remove Serbian sources from sources table
    op.execute("DELETE FROM sources WHERE country = 'RS'")
    
    # Remove Serbian subscribers
    op.execute("DELETE FROM subscribers WHERE locale = 'sr'")
    
    # Remove cluster_summaries for Serbian
    op.execute("DELETE FROM cluster_summaries WHERE lang = 'sr'")


def downgrade() -> None:
    """Revert schema changes (not recommended - data will be lost)."""
    # This is a destructive migration - downgrade is not supported
    # The original schema can be restored from backup
    raise NotImplementedError("This migration is not reversible - restore from backup")
