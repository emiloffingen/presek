"""functional + trigram indexes for entity lookups

Entity hover-cards/searches run LOWER(col) = LOWER(%s) and ILIKE %...% scans
over knowledge_entities, cluster_entities and knowledge_relationships with no
supporting indexes. Add functional btree indexes for the exact lookups and
pg_trgm GIN indexes for the LIKE/ILIKE patterns used by the entity branch of
/news. Tables are small; plain (transactional) CREATE INDEX is fine.

Revision ID: p6f7a8b9c0d1
Revises: o5e6f7a8b9c0
"""

from typing import Sequence, Union

from alembic import op

revision: str = "p6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "o5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_entities_lower_name ON knowledge_entities (LOWER(name))")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cluster_entities_lower_name ON cluster_entities (LOWER(entity_name))")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_relationships_lower_a ON knowledge_relationships (LOWER(entity_a))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_relationships_lower_b ON knowledge_relationships (LOWER(entity_b))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_entities_name_trgm ON knowledge_entities USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cluster_entities_name_trgm ON cluster_entities USING gin (entity_name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cluster_entities_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_entities_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_relationships_lower_b")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_relationships_lower_a")
    op.execute("DROP INDEX IF EXISTS ix_cluster_entities_lower_name")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_entities_lower_name")
