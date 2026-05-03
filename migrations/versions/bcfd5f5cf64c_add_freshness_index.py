"""add freshness index

Revision ID: bcfd5f5cf64c
Revises: b251aec55d2e
Create Date: 2026-05-04 00:28:35.861055

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcfd5f5cf64c'
down_revision: Union[str, Sequence[str], None] = 'b251aec55d2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_freshness ON articles (COALESCE(ingested_at, created_at) DESC)")

def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_articles_freshness")
