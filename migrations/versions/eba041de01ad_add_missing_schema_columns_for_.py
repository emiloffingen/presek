"""add missing schema columns for intelligence v2

Revision ID: eba041de01ad
Revises: f631fc2a7880
Create Date: 2026-05-12 08:28:32.058453

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eba041de01ad"
down_revision: Union[str, Sequence[str], None] = "f631fc2a7880"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS is_global BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE cluster_summaries ADD COLUMN IF NOT EXISTS key_facts JSONB")
    op.execute("ALTER TABLE cluster_summaries ADD COLUMN IF NOT EXISTS analyst_entities JSONB")
    op.execute("ALTER TABLE cluster_summaries ADD COLUMN IF NOT EXISTS pulse_score FLOAT")
    op.execute("ALTER TABLE cluster_summaries ADD COLUMN IF NOT EXISTS pluralism_score FLOAT")
    op.execute("ALTER TABLE cluster_summaries ADD COLUMN IF NOT EXISTS narrative_diversity FLOAT")
    op.execute("ALTER TABLE cluster_summaries ADD COLUMN IF NOT EXISTS storyline_narrative TEXT")
    op.execute(
        """
        DO $$ BEGIN
            IF to_regclass('cluster_summary_history') IS NOT NULL THEN
                ALTER TABLE cluster_summary_history ADD COLUMN IF NOT EXISTS key_facts JSONB;
                ALTER TABLE cluster_summary_history ADD COLUMN IF NOT EXISTS analyst_entities JSONB;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
