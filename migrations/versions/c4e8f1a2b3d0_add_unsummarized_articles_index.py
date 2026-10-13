"""add unsummarized articles index

Revision ID: c4e8f1a2b3d0
Revises: 28a9b85a5c90
Create Date: 2026-06-11 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8f1a2b3d0"
down_revision: Union[str, Sequence[str], None] = "28a9b85a5c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_unsummarized_id ON articles (id) WHERE summary IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_articles_unsummarized_id")
