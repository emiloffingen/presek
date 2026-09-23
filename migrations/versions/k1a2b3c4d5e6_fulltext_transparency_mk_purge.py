"""full-text transparency: source flags + MK-only purge

Revision ID: k1a2b3c4d5e6
Revises: j0e1f2a3b4c5

Adds per-source full-text/attribution flags, deactivates non-MK feeds, and
purges non-MK articles (backed up to ``articles_nonmk_backup`` first).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "j0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ORPHAN_CLEANUP = (
    "DELETE FROM cluster_summaries cs WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = cs.cluster_id)",
    "DELETE FROM cluster_metadata cm WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = cm.cluster_id)",
    "DELETE FROM cluster_entities ce WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = ce.cluster_id)",
    "DELETE FROM reactions r WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = r.cluster_id)",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "sources" in tables:
        existing = {c["name"] for c in inspector.get_columns("sources")}
        if "full_text_allowed" not in existing:
            op.add_column(
                "sources",
                sa.Column("full_text_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            )
        if "attribution_name" not in existing:
            op.add_column("sources", sa.Column("attribution_name", sa.Text()))

    # MK-only: stop ingesting non-MK sources.
    op.execute("UPDATE sources SET is_active = FALSE WHERE COALESCE(country, '') <> 'MK'")
    if "feed_sources" in tables:
        op.execute(
            "UPDATE feed_sources SET is_active = FALSE "
            "WHERE name IN (SELECT name FROM sources WHERE COALESCE(country, '') <> 'MK')"
        )

    # Backup then purge non-MK articles; drop orphaned cluster rows.
    if "articles" in tables:
        op.execute(
            "CREATE TABLE IF NOT EXISTS articles_nonmk_backup AS "
            "SELECT * FROM articles WHERE COALESCE(country, '') <> 'MK'"
        )
        op.execute("DELETE FROM articles WHERE COALESCE(country, '') <> 'MK'")
        for stmt in _ORPHAN_CLEANUP:
            try:
                op.execute(stmt)
            except Exception:  # table may not exist on minimal schemas
                pass


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "articles_nonmk_backup" in tables and "articles" in tables:
        op.execute("INSERT INTO articles SELECT * FROM articles_nonmk_backup ON CONFLICT DO NOTHING")

    if "sources" in tables:
        existing = {c["name"] for c in inspector.get_columns("sources")}
        if "attribution_name" in existing:
            op.drop_column("sources", "attribution_name")
        if "full_text_allowed" in existing:
            op.drop_column("sources", "full_text_allowed")
