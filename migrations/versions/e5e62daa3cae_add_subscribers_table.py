"""add_subscribers_table

Revision ID: e5e62daa3cae
Revises: 722c56e76f5b
Create Date: 2026-05-17 18:38:17.708119

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5e62daa3cae"
down_revision: Union[str, Sequence[str], None] = "722c56e76f5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            email TEXT PRIMARY KEY,
            locale TEXT DEFAULT 'sr',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS subscribers;")
