"""restore cluster_summaries primary key (cluster_id, lang)

Revision ID: l2b3c4d5e6f7
Revises: k1a2b3c4d5e6

Migration ``a1b2c3d4e5f6`` ran ``ALTER TABLE cluster_summaries DROP COLUMN lang``.
Because ``lang`` participated in the composite primary key
``(cluster_id, lang)``, dropping the column also dropped the primary key, and
nothing ever restored it. With no unique constraint left, every
``INSERT ... ON CONFLICT`` into ``cluster_summaries`` fails with
"there is no unique or exclusion constraint matching the ON CONFLICT
specification", so cluster synthesis was never persisted (the table stayed
empty and every cluster page showed a placeholder).

This migration restores the ``(cluster_id, lang)`` primary key. The application
uses ``ON CONFLICT (cluster_id, lang)`` for this table. ``lang`` defaults to
``'mk'`` for any pre-existing rows.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "k1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cluster_summaries" not in set(inspector.get_table_names()):
        return

    cols = {c["name"] for c in inspector.get_columns("cluster_summaries")}

    # Ensure lang exists (some deployments had the column dropped).
    if "lang" not in cols:
        op.add_column(
            "cluster_summaries",
            sa.Column("lang", sa.Text(), nullable=False, server_default=sa.text("'mk'")),
        )

    # Already has the right PK? nothing to do.
    existing_pks = inspector.get_pk_constraint("cluster_summaries")
    if existing_pks and existing_pks.get("constrained_columns"):
        return

    # Dedupe on (cluster_id, lang) before adding the PK, keeping the newest row.
    op.execute(
        """
        DELETE FROM cluster_summaries a
        USING cluster_summaries b
        WHERE a.ctid < b.ctid
          AND a.cluster_id = b.cluster_id
          AND a.lang = b.lang
        """
    )
    op.create_primary_key("cluster_summaries_pkey", "cluster_summaries", ["cluster_id", "lang"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cluster_summaries" not in set(inspector.get_table_names()):
        return
    existing_pks = inspector.get_pk_constraint("cluster_summaries")
    if existing_pks and existing_pks.get("constrained_columns"):
        op.drop_constraint("cluster_summaries_pkey", "cluster_summaries", type_="primary")
