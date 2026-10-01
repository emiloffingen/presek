"""Jina-based embeddings for semantic search (MK branch).

Uses the Jina Embeddings API (jina-embeddings-v3) with Matryoshka truncation
to 384 dims, matching the articles.embedding vector(384) column. Requires
JINA_API_KEY in the environment.

All entry points degrade gracefully (empty results) when the key is missing
or the API fails, so callers fall back to plain full-text search.
"""

import logging
import os
import threading
import time

from core.http_pool import pooled_async_client, pooled_client

log = logging.getLogger("presek")

JINA_URL = "https://api.jina.ai/v1/embeddings"
JINA_MODEL = "jina-embeddings-v3"
EMBEDDING_DIM = 384
_BATCH_SIZE = 100
_TIMEOUT = 30.0

# In-memory cache for single-query vectors. News queries repeat heavily
# (trending topics), so this skips the ~0.5-1s Jina roundtrip and the token
# spend on repeats. Process-local: safe for the single-worker API.
_QUERY_CACHE_TTL = 3600
_QUERY_CACHE_MAX = 2000
_query_cache: dict[str, tuple[float, list]] = {}
_query_cache_lock = threading.Lock()


def _query_cache_get(text: str) -> list | None:
    now = time.monotonic()
    with _query_cache_lock:
        hit = _query_cache.get(text)
        if hit and now - hit[0] < _QUERY_CACHE_TTL:
            return hit[1]
        if hit:
            del _query_cache[text]
    return None


def _query_cache_set(text: str, vec: list) -> None:
    with _query_cache_lock:
        if len(_query_cache) >= _QUERY_CACHE_MAX:
            oldest = next(iter(_query_cache))
            del _query_cache[oldest]
        _query_cache[text] = (time.monotonic(), vec)


def _api_key() -> str:
    return os.environ.get("JINA_API_KEY", "").strip()


def _payload(texts, task: str) -> dict:
    return {
        "model": JINA_MODEL,
        "task": task,
        "dimensions": EMBEDDING_DIM,
        "late_chunking": False,
        "embedding_type": "float",
        "input": texts,
    }


def _parse_response(data: dict, size: int) -> list:
    out = [None] * size
    for item in data.get("data", []):
        idx = item.get("index")
        vec = item.get("embedding")
        if isinstance(idx, int) and 0 <= idx < size and vec:
            out[idx] = [float(x) for x in vec]
    return out


def _embed_sync(texts: list, task: str) -> list:
    """Embed one batch synchronously; index-aligned, None on per-item failure."""
    texts = [(t or "")[:4000] for t in texts]
    if not texts or not _api_key():
        return [None] * len(texts)
    try:
        with pooled_client(_TIMEOUT) as client:
            resp = client.post(
                JINA_URL,
                json=_payload(texts, task),
                headers={"Authorization": f"Bearer {_api_key()}"},
            )
            resp.raise_for_status()
            return _parse_response(resp.json(), len(texts))
    except Exception as e:
        log.warning("Jina embedding batch failed (%s ...): %s", task, e)
        return [None] * len(texts)


def generate_embeddings_batch(texts, *a, **kw):
    """Embed article texts (title + description) for ingestion. Index-aligned."""
    texts = list(texts or [])
    if not texts:
        return []
    out: list = []
    for i in range(0, len(texts), _BATCH_SIZE):
        out.extend(_embed_sync(texts[i : i + _BATCH_SIZE], "retrieval.passage"))
    return out


def generate_query_embedding(q, *a, **kw):
    """Sync single-query embedding; [] when unavailable (FTS fallback)."""
    if not q:
        return []
    text = str(q)[:4000]
    hit = _query_cache_get(text)
    if hit is not None:
        return hit
    vecs = _embed_sync([text], "retrieval.query")
    vec = vecs[0] or []
    if vec:
        _query_cache_set(text, vec)
    return vec


async def get_query_embedding_async(q, *a, **kw):
    """Async single-query embedding for request handlers; [] on any failure."""
    if not q or not _api_key():
        return []
    text = str(q)[:4000]
    hit = _query_cache_get(text)
    if hit is not None:
        return hit
    try:
        async with pooled_async_client("jina", timeout=_TIMEOUT) as client:
            resp = await client.post(
                JINA_URL,
                json=_payload([text], "retrieval.query"),
                headers={"Authorization": f"Bearer {_api_key()}"},
            )
            resp.raise_for_status()
            vecs = _parse_response(resp.json(), 1)
            vec = vecs[0] or []
            if vec:
                _query_cache_set(text, vec)
            return vec
    except Exception as e:
        log.warning("Jina query embedding failed: %s", e)
        return []


def parse_embedding_value(value, *a, **kw):
    """Normalize a stored embedding (pgvector string, list, or None) to floats."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        s = s.strip()
        if not s:
            return []
        return [float(x) for x in s.split(",")]
    return []


def average_embeddings(values) -> list | None:
    """Compute a centroid from mixed embedding payloads, skipping malformed rows."""
    vectors = []
    for value in values or []:
        parsed = parse_embedding_value(value)
        if parsed:
            vectors.append(parsed)

    if not vectors:
        return None

    dims = len(vectors[0])
    totals = [0.0] * dims
    count = 0

    for vector in vectors:
        if len(vector) != dims:
            continue
        for idx, item in enumerate(vector):
            totals[idx] += float(item)
        count += 1

    if count == 0:
        return None

    return [value / count for value in totals]


def get_cluster_embedding(cluster_id: str) -> list | None:
    """Centroid embedding for all articles in a cluster (None when unavailable)."""
    from core.database import db_manager as db

    try:
        rows = db.execute(
            "SELECT embedding FROM articles WHERE cluster_id = %s AND embedding IS NOT NULL",
            (cluster_id,),
        )
        if not rows:
            return None
        return average_embeddings([r.get("embedding") for r in rows])
    except Exception as e:
        log.warning(f"[embeddings] Failed to calculate cluster embedding for {cluster_id}: {e}")
        return None


def embed_recent_articles(hours: int = 24, limit: int = 100) -> int:
    """Generate and store embeddings for recent articles that lack one."""
    from core.database import db_manager as db

    try:
        rows = db.execute(
            """SELECT id, title, description FROM articles
               WHERE embedding IS NULL
                 AND created_at >= NOW() - (%s * INTERVAL '1 hour')
               ORDER BY created_at DESC
               LIMIT %s""",
            (hours, limit),
        )
    except Exception as e:
        log.error(f"[embeddings] Failed to fetch articles for embedding: {e}")
        return 0

    if not rows:
        return 0

    texts = [f"{r['title']}. {r.get('description') or ''}" for r in rows]
    vectors = generate_embeddings_batch(texts)
    valid_pairs = [
        ("[" + ",".join(map(str, vec)) + "]", row["id"]) for row, vec in zip(rows, vectors) if vec is not None
    ]
    embedded = 0
    if valid_pairs:
        try:
            db.executemany("UPDATE articles SET embedding = %s::vector WHERE id = %s", valid_pairs)
            embedded = len(valid_pairs)
        except Exception as e:
            log.warning(f"[embeddings] Batch embedding store failed: {e}")
    log.info(f"[embeddings] Embedded {embedded}/{len(rows)} recent articles")
    return embedded


def shutdown_embedding_executor(*a, **kw):
    return None
