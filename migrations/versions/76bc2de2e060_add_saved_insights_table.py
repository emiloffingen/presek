"""add_saved_insights_table

Revision ID: 76bc2de2e060
Revises: 472c0aa46965
Create Date: 2026-05-19 12:41:12.427045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '76bc2de2e060'
down_revision: Union[str, Sequence[str], None] = '472c0aa46965'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'saved_insights',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False, index=True),
        sa.Column('cluster_id', sa.String(64), nullable=False, index=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('report', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('saved_insights')
