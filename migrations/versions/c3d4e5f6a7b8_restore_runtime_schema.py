"""restore columns still required by public runtime queries

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("image_caption", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.add_column(
        "cluster_summaries",
        sa.Column("lang", sa.String(8), server_default=sa.text("'mk'"), nullable=False),
    )
    op.execute("UPDATE cluster_summaries SET lang = 'mk' WHERE lang IS NULL")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS advertising_campaigns (
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
        )
        """
    )


def downgrade() -> None:
    op.drop_table("advertising_campaigns")
    op.drop_column("cluster_summaries", "lang")
    op.drop_column("articles", "image_caption")
