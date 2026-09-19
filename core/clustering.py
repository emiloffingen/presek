"""Stub: clustering removed in mk-only simplify."""
import uuid


VECTOR_THRESHOLD = 0.0
def _cluster_title_overlap(*a, **kw): return 0.0
def _extract_title_entities(*a, **kw): return []
def _meaningful_entity_token_overlap(*a, **kw): return 0.0
def generate_embeddings_batch(*a, **kw): return []


def find_or_create_cluster(conn, title, recent_articles, **kwargs):
    """Create a lightweight cluster identifier for ingestion without local AI."""
    return str(uuid.uuid4())
