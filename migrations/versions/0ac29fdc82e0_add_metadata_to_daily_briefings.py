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
    
    # Ensure daily_briefings table exists (it seems to be missing in some environments)
    op.execute("""
        CREATE TABLE IF NOT EXISTS daily_briefings (
            date DATE NOT NULL,
            content TEXT,
            lang VARCHAR(5) NOT NULL DEFAULT 'sr',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, lang)
        )
    """)
    
    # Add metadata column if it doesn't exist
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='daily_briefings' AND column_name='metadata') THEN
                ALTER TABLE daily_briefings ADD COLUMN metadata JSONB DEFAULT '{}';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('daily_briefings', 'metadata')
