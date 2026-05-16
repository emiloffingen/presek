"""add centroid and category to cluster_metadata

Revision ID: f631fc2a7880
Revises: 0aa973f3adcf
Create Date: 2026-05-12 07:40:09.760828

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f631fc2a7880'
down_revision: Union[str, Sequence[str], None] = '0aa973f3adcf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE cluster_metadata ADD COLUMN IF NOT EXISTS centroid vector(384)")
    op.execute("ALTER TABLE cluster_metadata ADD COLUMN IF NOT EXISTS category TEXT")

def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE cluster_metadata DROP COLUMN IF EXISTS centroid")
    op.execute("ALTER TABLE cluster_metadata DROP COLUMN IF EXISTS category")
