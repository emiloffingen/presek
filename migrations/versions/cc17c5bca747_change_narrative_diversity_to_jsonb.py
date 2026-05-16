"""change narrative_diversity to jsonb

Revision ID: cc17c5bca747
Revises: add_language_to_daily_briefings
Create Date: 2026-05-14 16:28:31.817220

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'cc17c5bca747'
down_revision: Union[str, Sequence[str], None] = 'add_language_to_daily_briefings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE cluster_summaries ALTER COLUMN narrative_diversity TYPE JSONB USING narrative_diversity::text::jsonb")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE cluster_summaries ALTER COLUMN narrative_diversity TYPE FLOAT USING (narrative_diversity->>'score')::float")
