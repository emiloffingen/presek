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


def upgrade() -> None:
    op.add_column("cluster_summaries", sa.Column("key_facts", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column(
        "cluster_summaries",
        sa.Column("analyst_entities", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column("cluster_summaries", sa.Column("pulse_score", sa.Float()))
    op.add_column("cluster_summaries", sa.Column("pluralism_score", sa.Float()))
    op.add_column("cluster_summaries", sa.Column("narrative_diversity", JSONB(), server_default=sa.text("'{}'::jsonb")))
    op.add_column("cluster_summaries", sa.Column("generation_provider", sa.Text()))
    op.add_column("cluster_summaries", sa.Column("generation_model", sa.Text()))
    op.add_column("cluster_summaries", sa.Column("quality_score", sa.Float()))
    op.add_column("cluster_summaries", sa.Column("fallback_reason", sa.Text()))


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
