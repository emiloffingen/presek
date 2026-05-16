"""add_metadata_to_daily_briefings

Revision ID: 0ac29fdc82e0
Revises: cc17c5bca747
Create Date: 2026-05-16 21:52:31.197255

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0ac29fdc82e0'
down_revision: Union[str, Sequence[str], None] = 'cc17c5bca747'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy.dialects import postgresql
    op.add_column('daily_briefings', sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('daily_briefings', 'metadata')
