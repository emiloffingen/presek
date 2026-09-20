"""Jina-based embeddings for semantic search (MK branch).

Uses the Jina Embeddings API (jina-embeddings-v3) with Matryoshka truncation
to 384 dims, matching the articles.embedding vector(384) column. Requires
JINA_API_KEY in the environment.

All entry points degrade gracefully (empty results) when the key is missing
or the API fails, so callers fall back to plain full-text search.
"""

import logging
import os

import httpx

log = logging.getLogger("presek")

JINA_URL = "https://api.jina.ai/v1/embeddings"
JINA_MODEL = "jina-embeddings-v3"
EMBEDDING_DIM = 384
_BATCH_SIZE = 100
_TIMEOUT = 30.0


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
        with httpx.Client(timeout=_TIMEOUT) as client:
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
    vecs = _embed_sync([str(q)], "retrieval.query")
    return vecs[0] or []


async def get_query_embedding_async(q, *a, **kw):
    """Async single-query embedding for request handlers; [] on any failure."""
    if not q or not _api_key():
        return []
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                JINA_URL,
                json=_payload([str(q)[:4000]], "retrieval.query"),
                headers={"Authorization": f"Bearer {_api_key()}"},
            )
            resp.raise_for_status()
            vecs = _parse_response(resp.json(), 1)
            return vecs[0] or []
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


def shutdown_embedding_executor(*a, **kw):
    return None
