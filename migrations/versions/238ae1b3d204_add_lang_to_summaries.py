"""add_lang_to_summaries

Revision ID: 238ae1b3d204
Revises: 47af8e3d997a
Create Date: 2026-05-13 20:42:53.841193

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "238ae1b3d204"
down_revision: Union[str, Sequence[str], None] = "47af8e3d997a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. Add lang column to cluster_summaries (+ composite PK) unless a later
    #    mk-only migration already restored it.
    cs_cols = {c["name"] for c in inspector.get_columns("cluster_summaries")}
    if "lang" not in cs_cols:
        op.add_column("cluster_summaries", sa.Column("lang", sa.Text(), nullable=False, server_default="sr"))

        # 2. Update Primary Key for cluster_summaries
        # Standard PostgreSQL name for PK is {table}_pkey
        op.drop_constraint("cluster_summaries_pkey", "cluster_summaries", type_="primary")
        op.create_primary_key("cluster_summaries_pkey", "cluster_summaries", ["cluster_id", "lang"])

    # 3. Add lang column to cluster_summary_history, which the mk-only simplify
    #    migration may have dropped entirely.
    if "cluster_summary_history" in existing_tables:
        h_cols = {c["name"] for c in inspector.get_columns("cluster_summary_history")}
        if "lang" not in h_cols:
            op.add_column("cluster_summary_history", sa.Column("lang", sa.Text(), nullable=False, server_default="sr"))

        # 4. Add index to cluster_summary_history for faster lookups by language
        idx_names = {i["name"] for i in inspector.get_indexes("cluster_summary_history")}
        if "idx_cluster_summary_history_cid_lang" not in idx_names:
            op.create_index("idx_cluster_summary_history_cid_lang", "cluster_summary_history", ["cluster_id", "lang"])


def downgrade() -> None:
    # 1. Remove index
    op.drop_index("idx_cluster_summary_history_cid_lang", table_name="cluster_summary_history")

    # 2. Remove lang column from cluster_summary_history
    op.drop_column("cluster_summary_history", "lang")

    # 3. Restore Primary Key for cluster_summaries
    op.drop_constraint("cluster_summaries_pkey", "cluster_summaries", type_="primary")
    op.create_primary_key("cluster_summaries_pkey", "cluster_summaries", ["cluster_id"])

    # 4. Remove lang column from cluster_summaries
    op.drop_column("cluster_summaries", "lang")
