"""restore synthesis fields required by news serialization

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
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
        "cluster_summaries",
        [
            ("key_facts", sa.Column("key_facts", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False)),
            (
                "analyst_entities",
                sa.Column("analyst_entities", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
            ),
            ("pulse_score", sa.Column("pulse_score", sa.Float())),
            ("pluralism_score", sa.Column("pluralism_score", sa.Float())),
            (
                "narrative_diversity",
                sa.Column("narrative_diversity", JSONB(), server_default=sa.text("'{}'::jsonb")),
            ),
            ("generation_provider", sa.Column("generation_provider", sa.Text())),
            ("generation_model", sa.Column("generation_model", sa.Text())),
            ("quality_score", sa.Column("quality_score", sa.Float())),
            ("fallback_reason", sa.Column("fallback_reason", sa.Text())),
        ],
    )


def downgrade() -> None:
    for column in (
        "fallback_reason",
        "quality_score",
        "generation_model",
        "generation_provider",
        "narrative_diversity",
        "pluralism_score",
        "pulse_score",
        "analyst_entities",
        "key_facts",
    ):
        op.drop_column("cluster_summaries", column)
