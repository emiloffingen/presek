"""recover_missing_intelligence_tables

Revision ID: 722c56e76f5b
Revises: 0ac29fdc82e0
Create Date: 2026-05-16 23:00:42.053430

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "722c56e76f5b"
down_revision: Union[str, Sequence[str], None] = "0ac29fdc82e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Recover Knowledge Graph tables (which seem to be missing in some environments)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_entities (
            name TEXT PRIMARY KEY,
            type TEXT,
            total_mentions INTEGER DEFAULT 1,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sentiment_score REAL DEFAULT 0,
            image_url TEXT,
            metadata JSONB DEFAULT '{}'
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_relationships (
            entity_a TEXT REFERENCES knowledge_entities(name),
            entity_b TEXT REFERENCES knowledge_entities(name),
            weight INTEGER DEFAULT 1,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (entity_a, entity_b)
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_mentions_daily (
            entity_name TEXT REFERENCES knowledge_entities(name) ON DELETE CASCADE,
            cluster_id TEXT NOT NULL,
            day DATE DEFAULT CURRENT_DATE,
            PRIMARY KEY (entity_name, cluster_id, day)
        )
    """
    )

    # Recover Cluster Entities if missing
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cluster_entities (
            cluster_id TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            mentions INTEGER DEFAULT 1,
            PRIMARY KEY (cluster_id, entity_name)
        )
    """
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
