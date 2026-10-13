"""add_generation_metadata_to_summaries

Revision ID: 28a9b85a5c90
Revises: 02c58f04407a
Create Date: 2026-06-03 16:10:09.937960

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "28a9b85a5c90"
down_revision: Union[str, Sequence[str], None] = "g7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_missing_columns(table: str, columns: list[tuple[str, sa.Column]]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns(table)}
    for name, column in columns:
        if name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    """Upgrade schema."""
    _add_missing_columns(
        "cluster_summaries",
        [
            ("generation_provider", sa.Column("generation_provider", sa.String(), nullable=True)),
            ("generation_model", sa.Column("generation_model", sa.String(), nullable=True)),
            ("quality_score", sa.Column("quality_score", sa.Float(), nullable=True)),
            ("fallback_reason", sa.Column("fallback_reason", sa.String(), nullable=True)),
        ],
    )
    _add_missing_columns(
        "cluster_summary_history",
        [
            ("generation_provider", sa.Column("generation_provider", sa.String(), nullable=True)),
            ("generation_model", sa.Column("generation_model", sa.String(), nullable=True)),
            ("quality_score", sa.Column("quality_score", sa.Float(), nullable=True)),
            ("fallback_reason", sa.Column("fallback_reason", sa.String(), nullable=True)),
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cluster_summaries", "generation_provider")
    op.drop_column("cluster_summaries", "generation_model")
    op.drop_column("cluster_summaries", "quality_score")
    op.drop_column("cluster_summaries", "fallback_reason")

    op.drop_column("cluster_summary_history", "generation_provider")
    op.drop_column("cluster_summary_history", "generation_model")
    op.drop_column("cluster_summary_history", "quality_score")
    op.drop_column("cluster_summary_history", "fallback_reason")
