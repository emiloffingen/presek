"""restore article fields used by news and homepage responses

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("is_redundant", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("articles", sa.Column("reading_time", sa.Integer(), server_default=sa.text("1"), nullable=False))
    op.add_column(
        "articles",
        sa.Column("entity_names", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column("articles", sa.Column("source_signal", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("articles", sa.Column("is_global", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column(
        "articles",
        sa.Column("coverage_balance", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )


def downgrade() -> None:
    for column in ("coverage_balance", "is_global", "source_signal", "entity_names", "reading_time", "is_redundant"):
        op.drop_column("articles", column)
