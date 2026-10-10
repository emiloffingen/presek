"""local visitor tracking: privacy-friendly page visits

Revision ID: q7a8b9c0d1e2
Revises: p6f7a8b9c0d1
Create Date: 2026-10-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "p6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "page_visits" not in tables:
        op.create_table(
            "page_visits",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column(
                "visited_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            # sha256(ip + ua + daily salt) — no raw IP stored (privacy policy)
            sa.Column("visitor_hash", sa.Text(), nullable=False),
            sa.Column("host", sa.Text(), nullable=True),
            sa.Column("path", sa.Text(), nullable=True),
            sa.Column("lang", sa.Text(), nullable=True),
            sa.Column("referrer", sa.Text(), nullable=True),
            sa.Column("ua_hash", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_page_visits_visited_at", "page_visits", ["visited_at"])
        op.create_index(
            "ix_page_visits_visitor_visited",
            "page_visits",
            ["visitor_hash", "visited_at"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_page_visits_visitor_visited", table_name="page_visits")
    op.drop_index("ix_page_visits_visited_at", table_name="page_visits")
    op.drop_table("page_visits")
