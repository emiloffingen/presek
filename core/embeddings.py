"""Local multilingual embeddings for semantic search and clustering (MK branch).

Runs intfloat/multilingual-e5-small (quantized ONNX via fastembed) in-process: free,
no API quota, native 384 dims to match the articles.embedding vector(384) column.

Raw e5 cosines are compressed (unrelated pairs ~0.8), so every vector is centred on
the corpus mean and re-normalised. That puts similarities on roughly the scale the
old Jina vectors had; ``jina_similarity`` / ``local_distance`` below map the
remaining difference so thresholds tuned on Jina keep their meaning.

All entry points degrade gracefully (empty results) when fastembed or the model is
unavailable, so callers fall back to plain full-text search.
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

log = logging.getLogger("presek")

MODEL_NAME = "intfloat/multilingual-e5-small"
_MODEL_HF_REPO = "Xenova/multilingual-e5-small"
_MODEL_FILE = "onnx/model_quantized.onnx"
EMBEDDING_DIM = 384
_BATCH_SIZE = 32
_MAX_CHARS = 1200
_RETRY_AFTER = 300.0
_MEAN_PATH = Path(__file__).parent / "data" / "e5_small_mean.json"

# In-memory cache for single-query vectors. News queries repeat heavily
# (trending topics), so this skips recomputation on repeats. Process-local.
_QUERY_CACHE_TTL = 3600
_QUERY_CACHE_MAX = 2000
_query_cache: dict[str, tuple[float, list]] = {}
_query_cache_lock = threading.Lock()

_model = None
_model_failed_at = 0.0
_model_lock = threading.Lock()
_mean: list | None = None

# (jina_distance, local_distance) pairs, matched on how many of 4.5M sampled article
# pairs fall under each distance. Lets thresholds tuned on Jina keep their selectivity.
_CALIBRATION = (
    (0.0, 0.0),
    (0.05, 0.131),
    (0.10, 0.213),
    (0.15, 0.278),
    (0.18, 0.313),
    (0.22, 0.358),
    (0.28, 0.427),
    (0.35, 0.501),
    (0.40, 0.555),
    (0.50, 0.643),
    (0.60, 0.715),
    (0.70, 0.802),
    (0.80, 0.893),
    (1.0, 1.074),
    (2.0, 2.0),
)


def _interp(x: float, src: int, dst: int) -> float:
    pts = _CALIBRATION
    if x <= pts[0][src]:
        return pts[0][dst]
    for lo, hi in zip(pts, pts[1:]):
        if x <= hi[src]:
            span = hi[src] - lo[src]
            return lo[dst] + (hi[dst] - lo[dst]) * ((x - lo[src]) / span if span else 0.0)
    return pts[-1][dst]


def local_distance(jina_distance: float) -> float:
    """Cosine distance on local vectors equivalent to ``jina_distance`` on Jina vectors."""
    return _interp(float(jina_distance), 0, 1)


def jina_distance(local_dist: float) -> float:
    return _interp(float(local_dist), 1, 0)


def local_similarity(jina_similarity_value: float) -> float:
    """Local cosine similarity equivalent to a Jina-scale similarity threshold."""
    return 1.0 - local_distance(1.0 - float(jina_similarity_value))


def jina_similarity(local_sim: float) -> float:
    """Express a local cosine similarity on the Jina scale existing thresholds use."""
    return 1.0 - jina_distance(1.0 - float(local_sim))


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


def _cache_dir() -> str:
    explicit = os.environ.get("PRESEK_EMBED_CACHE", "").strip()
    return explicit or str(Path(__file__).resolve().parent.parent / ".cache" / "fastembed")


def _load_mean() -> list:
    global _mean
    if _mean is None:
        _mean = [float(x) for x in json.loads(_MEAN_PATH.read_text())]
    return _mean


def _get_model():
    """Lazy, thread-safe model load; None (retried after a pause) when unavailable."""
    global _model, _model_failed_at
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        if _model_failed_at and time.monotonic() - _model_failed_at < _RETRY_AFTER:
            return None
        try:
            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType

            try:
                TextEmbedding.add_custom_model(
                    model=MODEL_NAME,
                    pooling=PoolingType.MEAN,
                    normalization=True,
                    sources=ModelSource(hf=_MODEL_HF_REPO),
                    dim=EMBEDDING_DIM,
                    model_file=_MODEL_FILE,
                )
            except ValueError:
                pass  # already registered in this process
            _load_mean()
            _model = TextEmbedding(
                MODEL_NAME,
                cache_dir=_cache_dir(),
                threads=int(os.environ.get("PRESEK_EMBED_THREADS", "2")),
            )
            log.info("[embeddings] loaded %s", MODEL_NAME)
        except Exception as e:
            _model_failed_at = time.monotonic()
            log.warning("[embeddings] local model unavailable (%s); semantic search falls back to FTS", e)
            return None
    return _model


def warm_up() -> bool:
    """Load the model now so the first request doesn't pay the load cost."""
    return _get_model() is not None


def _center(vec) -> list:
    mean = _load_mean()
    shifted = [float(x) - m for x, m in zip(vec, mean)]
    norm = sum(x * x for x in shifted) ** 0.5
    if not norm:
        return [0.0] * len(shifted)
    return [round(x / norm, 6) for x in shifted]


def article_text(title, description) -> str:
    """Text embedded for an article: headline plus the start of the description."""
    desc = re.sub(r"<[^>]+>", " ", str(description or ""))
    desc = " ".join(desc.split())[:300]
    return f"{str(title or '').strip()}. {desc}".strip()


def _embed_sync(texts: list, prefix: str) -> list:
    """Embed one batch; index-aligned, None on failure."""
    texts = [(t or "").strip()[:_MAX_CHARS] for t in texts]
    if not texts:
        return []
    model = _get_model()
    if model is None:
        return [None] * len(texts)
    try:
        raw = list(model.embed([prefix + t for t in texts], batch_size=_BATCH_SIZE))
        return [_center(v) for v in raw]
    except Exception as e:
        log.warning("[embeddings] local embedding failed: %s", e)
        return [None] * len(texts)


def generate_embeddings_batch(texts, *a, **kw):
    """Embed article texts (title + description) for ingestion. Index-aligned."""
    texts = list(texts or [])
    if not texts:
        return []
    out: list = []
    for i in range(0, len(texts), 100):
        out.extend(_embed_sync(texts[i : i + 100], "passage: "))
    return out


def generate_query_embedding(q, *a, **kw):
    """Sync single-query embedding; [] when unavailable (FTS fallback)."""
    if not q:
        return []
    text = str(q)[:_MAX_CHARS]
    hit = _query_cache_get(text)
    if hit is not None:
        return hit
    vec = _embed_sync([text], "query: ")[0] or []
    if vec:
        _query_cache_set(text, vec)
    return vec


async def get_query_embedding_async(q, *a, **kw):
    """Async single-query embedding for request handlers; [] on any failure."""
    if not q:
        return []
    try:
        return await asyncio.to_thread(generate_query_embedding, q)
    except Exception as e:
        log.warning("[embeddings] query embedding failed: %s", e)
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

    texts = [article_text(r["title"], r.get("description")) for r in rows]
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
