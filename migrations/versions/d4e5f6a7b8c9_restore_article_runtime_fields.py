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


def _add_missing_columns(table: str, columns: list[tuple[str, sa.Column]]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns(table)}
    for name, column in columns:
        if name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    _add_missing_columns(
        "articles",
        [
            ("is_redundant", sa.Column("is_redundant", sa.Boolean(), server_default=sa.text("false"), nullable=False)),
            ("reading_time", sa.Column("reading_time", sa.Integer(), server_default=sa.text("1"), nullable=False)),
            (
                "entity_names",
                sa.Column("entity_names", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
            ),
            (
                "source_signal",
                sa.Column("source_signal", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
            ),
            ("is_global", sa.Column("is_global", sa.Boolean(), server_default=sa.text("false"), nullable=False)),
            (
                "coverage_balance",
                sa.Column("coverage_balance", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
            ),
        ],
    )


def downgrade() -> None:
    for column in ("coverage_balance", "is_global", "source_signal", "entity_names", "reading_time", "is_redundant"):
        op.drop_column("articles", column)
