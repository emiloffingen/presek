"""add full_content to articles

Revision ID: 47af8e3d997a
Revises: d5126eb6d25c
Create Date: 2026-05-12 08:42:08.907527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47af8e3d997a'
down_revision: Union[str, Sequence[str], None] = 'd5126eb6d25c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS full_content TEXT")

def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS full_content")
