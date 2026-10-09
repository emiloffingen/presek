"""add_analytics_materialized_views

Revision ID: 02daa0cf0002
Revises: 76bc2de2e060
Create Date: 2026-05-19 12:57:34.487920

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "02daa0cf0002"
down_revision: Union[str, Sequence[str], None] = "76bc2de2e060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE MATERIALIZED VIEW mv_article_stats AS
        SELECT 
            DATE(created_at) as day,
            category,
            source,
            COUNT(*) as article_count
        FROM articles
        GROUP BY 1, 2, 3;
        CREATE UNIQUE INDEX ON mv_article_stats (day, category, source);
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW mv_article_stats")
