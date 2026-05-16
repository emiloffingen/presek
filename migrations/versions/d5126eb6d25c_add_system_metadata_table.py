"""add system_metadata table

Revision ID: d5126eb6d25c
Revises: eba041de01ad
Create Date: 2026-05-12 08:37:11.986542

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd5126eb6d25c'
down_revision: Union[str, Sequence[str], None] = 'eba041de01ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS system_metadata (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS system_metadata")
