"""add_indexes_and_storyline_centroid

Revision ID: 24434f8a57fc
Revises: e5e62daa3cae
Create Date: 2026-05-18 16:30:10.703930

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24434f8a57fc'
down_revision: Union[str, Sequence[str], None] = 'e5e62daa3cae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 0. Ensure storylines tables exist (recovery if they were missed in baseline)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS storylines_v2 (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            slug TEXT UNIQUE,
            summary TEXT,
            status TEXT DEFAULT 'active',
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS storyline_clusters_v2 (
            storyline_id INTEGER REFERENCES storylines_v2(id) ON DELETE CASCADE,
            cluster_id TEXT NOT NULL,
            relevance_score REAL DEFAULT 1.0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (storyline_id, cluster_id)
        )
    """
    )

    # 1. Add centroid to storylines_v2
    op.execute("ALTER TABLE storylines_v2 ADD COLUMN IF NOT EXISTS centroid vector(384)")
    
    # 2. Add HNSW indexes for faster semantic lookups
    # These indexes significantly speed up vector distance calculations used in clustering and discovery
    op.execute("CREATE INDEX IF NOT EXISTS idx_cluster_metadata_centroid ON cluster_metadata USING hnsw (centroid vector_cosine_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_storylines_v2_centroid ON storylines_v2 USING hnsw (centroid vector_cosine_ops)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_storylines_v2_centroid")
    op.execute("DROP INDEX IF EXISTS idx_cluster_metadata_centroid")
    op.execute("ALTER TABLE storylines_v2 DROP COLUMN IF EXISTS centroid")
