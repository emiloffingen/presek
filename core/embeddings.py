"""Stub: embeddings removed in mk-only simplify."""


def generate_embeddings_batch(texts, *a, **kw):
    """Return one empty embedding per input so ingestion remains index-safe."""
    return [None] * len(texts)


async def get_query_embedding_async(*a, **kw): return []
def generate_query_embedding(*a, **kw): return []
def parse_embedding_value(*a, **kw): return []


def shutdown_embedding_executor(*a, **kw):
    return None
