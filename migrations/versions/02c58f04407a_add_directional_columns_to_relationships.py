"""add_directional_columns_to_relationships

Revision ID: 02c58f04407a
Revises: 8d3f7a6c1b92
Create Date: 2026-05-24 14:44:53.834885

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '02c58f04407a'
down_revision: Union[str, Sequence[str], None] = '8d3f7a6c1b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('knowledge_relationships', sa.Column('count_a_to_b', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('knowledge_relationships', sa.Column('count_b_to_a', sa.Integer(), nullable=False, server_default='0'))
    # Populate existing rows: set count_a_to_b equal to the undirected weight, and count_b_to_a to 0
    op.execute("UPDATE knowledge_relationships SET count_a_to_b = weight, count_b_to_a = 0")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('knowledge_relationships', 'count_b_to_a')
    op.drop_column('knowledge_relationships', 'count_a_to_b')
