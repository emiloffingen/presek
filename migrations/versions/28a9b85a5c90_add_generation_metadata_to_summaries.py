"""add_generation_metadata_to_summaries

Revision ID: 28a9b85a5c90
Revises: 02c58f04407a
Create Date: 2026-06-03 16:10:09.937960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28a9b85a5c90'
down_revision: Union[str, Sequence[str], None] = '02c58f04407a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('cluster_summaries', sa.Column('generation_provider', sa.String(), nullable=True))
    op.add_column('cluster_summaries', sa.Column('generation_model', sa.String(), nullable=True))
    op.add_column('cluster_summaries', sa.Column('quality_score', sa.Float(), nullable=True))
    op.add_column('cluster_summaries', sa.Column('fallback_reason', sa.String(), nullable=True))

    op.add_column('cluster_summary_history', sa.Column('generation_provider', sa.String(), nullable=True))
    op.add_column('cluster_summary_history', sa.Column('generation_model', sa.String(), nullable=True))
    op.add_column('cluster_summary_history', sa.Column('quality_score', sa.Float(), nullable=True))
    op.add_column('cluster_summary_history', sa.Column('fallback_reason', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cluster_summaries', 'generation_provider')
    op.drop_column('cluster_summaries', 'generation_model')
    op.drop_column('cluster_summaries', 'quality_score')
    op.drop_column('cluster_summaries', 'fallback_reason')

    op.drop_column('cluster_summary_history', 'generation_provider')
    op.drop_column('cluster_summary_history', 'generation_model')
    op.drop_column('cluster_summary_history', 'quality_score')
    op.drop_column('cluster_summary_history', 'fallback_reason')
