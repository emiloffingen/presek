"""add_metadata_to_daily_briefings

Revision ID: 0ac29fdc82e0
Revises: cc17c5bca747
Create Date: 2026-05-16 21:52:31.197255

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0ac29fdc82e0"
down_revision: Union[str, Sequence[str], None] = "cc17c5bca747"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy.dialects import postgresql

    # 1. Ensure daily_briefings table exists
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_briefings (
            date DATE NOT NULL,
            content TEXT,
            lang VARCHAR(5) NOT NULL DEFAULT 'sr',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, lang)
        )
    """
    )

    # 2. Add metadata column to daily_briefings if missing
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='daily_briefings' AND column_name='metadata') THEN
                ALTER TABLE daily_briefings ADD COLUMN metadata JSONB DEFAULT '{}';
            END IF;
        END $$;
    """
    )

    # 3. Recover Knowledge Graph tables (which seem to be missing in some environments)
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

    # 4. Recover Cluster Entities if missing
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
