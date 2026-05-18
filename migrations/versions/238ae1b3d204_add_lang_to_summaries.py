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
    # 1. Add lang column to cluster_summaries
    op.add_column("cluster_summaries", sa.Column("lang", sa.Text(), nullable=False, server_default="sr"))

    # 2. Update Primary Key for cluster_summaries
    # Standard PostgreSQL name for PK is {table}_pkey
    op.drop_constraint("cluster_summaries_pkey", "cluster_summaries", type_="primary")
    op.create_primary_key("cluster_summaries_pkey", "cluster_summaries", ["cluster_id", "lang"])

    # 3. Add lang column to cluster_summary_history
    op.add_column("cluster_summary_history", sa.Column("lang", sa.Text(), nullable=False, server_default="sr"))

    # 4. Add index to cluster_summary_history for faster lookups by language
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
