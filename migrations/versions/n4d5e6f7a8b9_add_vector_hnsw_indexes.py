"""restore hnsw vector indexes for articles.embedding and cluster_metadata.centroid

Revision ID: n4d5e6f7a8b9
Revises: m3c4d5e6f7a8
Create Date: 2026-10-04 10:45:00.000000

Migration a1b2c3d4e5f6 dropped the original vector indexes and g7b8c9d0e1f2
re-added the columns without the indexes. Restore them so semantic search uses
an HNSW index instead of a sequential scan.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "n4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "m3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_articles_embedding "
        "ON articles USING hnsw (embedding vector_cosine_ops) "
        "WITH (m=16, ef_construction=64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cluster_metadata_centroid "
        "ON cluster_metadata USING hnsw (centroid vector_cosine_ops) "
        "WITH (m=16, ef_construction=64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_articles_embedding")
    op.execute("DROP INDEX IF EXISTS idx_cluster_metadata_centroid")
