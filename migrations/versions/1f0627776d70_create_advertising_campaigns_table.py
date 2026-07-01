"""create_advertising_campaigns_table

Revision ID: 1f0627776d70
Revises: c4e8f1a2b3d0
Create Date: 2026-06-23 13:52:31.389375

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1f0627776d70'
down_revision: Union[str, Sequence[str], None] = 'c4e8f1a2b3d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """CREATE TABLE IF NOT EXISTS advertising_campaigns (
        id TEXT PRIMARY KEY,
        buyer_name TEXT NOT NULL,
        buyer_email TEXT NOT NULL,
        slot_id TEXT NOT NULL,
        target_impressions INTEGER NOT NULL,
        impressions_delivered INTEGER DEFAULT 0 NOT NULL,
        clicks INTEGER DEFAULT 0 NOT NULL,
        image_url TEXT NOT NULL,
        target_url TEXT NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,
        status TEXT DEFAULT 'pending' NOT NULL,
        stripe_session_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )"""
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS advertising_campaigns")
