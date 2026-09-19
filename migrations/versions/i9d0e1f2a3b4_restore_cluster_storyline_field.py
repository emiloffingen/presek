"""restore storyline narrative used by cluster detail responses

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "h8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cluster_summaries", sa.Column("storyline_narrative", sa.Text()))


def downgrade() -> None:
    op.drop_column("cluster_summaries", "storyline_narrative")
