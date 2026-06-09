"""
embeddings.py — Vector embedding generation for semantic search in Presek.

Uses a local sentence-transformers model (paraphrase-multilingual-MiniLM-L12-v2,
384 dims, 50+ languages including Macedonian/Cyrillic). Runs entirely offline
on CPU after the model is downloaded once to ~/.cache/huggingface.

No API key, no quota, no network at runtime.
"""

import json
import logging
import threading

from core.hf_cache import configure_huggingface_cache

log = logging.getLogger("presek")

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

# Batch size for encode() — MiniLM is small enough that 64 is comfortable on CPU
BATCH_SIZE = 64

_model = None
_model_lock = threading.Lock()


def _configure_model_cache() -> None:
    configure_huggingface_cache()


_configure_model_cache()


def get_shared_model():
    """Public accessor: returns the loaded SentenceTransformer, or None.
    Other modules (e.g. KeyBERT) can reuse this to avoid double-loading."""
    return _get_model()


def _get_model():
    """Lazy-load the sentence-transformers model on first use."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as e:
            log.error(f"[embeddings] sentence-transformers import failed: {e}")
            return None
        try:
            # Check for GPU availability and use if available
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
            log.info(f"[embeddings] Loading local model '{EMBEDDING_MODEL}' on {device}")
            _model = SentenceTransformer(EMBEDDING_MODEL, device=device)
            log.info(f"[embeddings] Model loaded on {device}, dim={_model.get_embedding_dimension()}")
        except Exception as e:
            log.error(f"[embeddings] Failed to load model: {e}")
            _model = None
        return _model


def generate_embedding(text: str) -> list[float] | None:
    """Generate a single embedding vector for the given text."""
    results = generate_embeddings_batch([text])
    if results and results[0] is not None:
        return results[0]
    return None


def generate_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """Generate embeddings for a list of texts using the local MiniLM model."""
    if not texts:
        return []

    model = _get_model()
    if model is None:
        return [None] * len(texts)

    # Truncate each text defensively — MiniLM has a 512 token cap but we slice
    # characters upstream to match the old pipeline's behaviour.
    cleaned = [str(t or "")[:2000] for t in texts]

    try:
        vectors = model.encode(
            cleaned,
            batch_size=BATCH_SIZE,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vec.tolist() for vec in vectors]
    except Exception as e:
        log.warning(f"[embeddings] Local encode error: {e}")
        return [None] * len(texts)


def embed_recent_articles(hours: int = 24, limit: int = 100) -> int:
    """
    Generate and store embeddings for recent articles that don't have one yet.
    Returns the count of articles embedded.
    """
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

    embedded = 0
    for row, vec in zip(rows, vectors):
        if vec is None:
            continue
        try:
            # pgvector accepts the textual "[v1,v2,...]" form. We don't register
            # a typecaster, so format the list explicitly here (matches the
            # pattern used by database.search_semantic / hybrid_search).
            vec_str = "[" + ",".join(map(str, vec)) + "]"
            db.execute(
                "UPDATE articles SET embedding = %s::vector WHERE id = %s",
                (vec_str, row["id"]),
                fetch=False,
            )
            embedded += 1
        except Exception as e:
            log.warning(f"[embeddings] Failed to store embedding for article {row['id']}: {e}")

    log.info(f"[embeddings] Embedded {embedded}/{len(rows)} recent articles")
    return embedded


def generate_query_embedding(text: str) -> list[float] | None:
    """Generate an embedding for a search query. Same model as documents —
    MiniLM is symmetric, no separate query/document task type needed.
    Includes Redis caching to avoid CPU-heavy re-generation."""
    if not text:
        return None

    clean_text = text.strip().lower()
    if not clean_text:
        return None

    import json

    from utils import redis_client

    cache_key = f"emb:query:{clean_text}"
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        log.warning(f"[embeddings] Cache read error for query '{clean_text}': {e}")

    vector = generate_embedding(text)

    if vector:
        try:
            # Cache query embeddings for 24 hours
            redis_client.setex(cache_key, 86400, json.dumps(vector))
        except Exception as e:
            log.warning(f"[embeddings] Cache write error for query '{clean_text}': {e}")

    return vector


def parse_embedding_value(value) -> list[float] | None:
    """Normalize embeddings loaded from pgvector, JSON, or legacy wrapped payloads."""
    if value is None:
        return None

    if hasattr(value, "tolist"):
        try:
            value = value.tolist()
        except Exception as e:
            log.debug(f"Failed to convert to list: {e}")

    if isinstance(value, dict):
        for key in ("embedding", "vector", "vec", "values", "data"):
            candidate = value.get(key)
            parsed = parse_embedding_value(candidate)
            if parsed:
                return parsed
        for candidate in value.values():
            parsed = parse_embedding_value(candidate)
            if parsed:
                return parsed
        return None

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.startswith("{") or raw.startswith("["):
            try:
                return parse_embedding_value(json.loads(raw))
            except Exception as e:
                log.debug(f"Failed to parse embedding JSON: {e}")
                pass
        cleaned = raw.strip("[]()")
        if not cleaned:
            return None
        try:
            return [float(part.strip()) for part in cleaned.split(",") if part.strip()]
        except Exception as e:
            log.debug(f"Failed to parse embedding string: {e}")
            return None

    if isinstance(value, (list, tuple)):
        if len(value) == 1 and isinstance(value[0], (str, list, tuple, dict)):
            nested = parse_embedding_value(value[0])
            if nested:
                return nested
        try:
            return [float(item) for item in value]
        except Exception as e:
            log.debug(f"Failed to parse embedding list: {e}")
            normalized = []
            for item in value:
                try:
                    normalized.append(float(item))
                except Exception as e2:
                    log.debug(f"Failed to parse embedding item: {e2}")
                    return None
            return normalized or None

    try:
        items = list(value)
        if len(items) == 1 and isinstance(items[0], (str, list, tuple, dict)):
            nested = parse_embedding_value(items[0])
            if nested:
                return nested
        return [float(item) for item in items]
    except Exception as e:
        log.debug(f"Failed to parse embedding iterable: {e}")
        return None


def average_embeddings(values) -> list[float] | None:
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


def get_cluster_embedding(cluster_id: str) -> list[float] | None:
    """Calculate the average embedding vector for all articles in a cluster."""
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


# =============================================================================
# Async Embedding Generation
# =============================================================================
# These async functions run embedding generation in a thread pool to avoid
# blocking the event loop, which is critical for FastAPI performance.

import asyncio
from concurrent.futures import ThreadPoolExecutor

# Thread pool for CPU-bound embedding work
_embedding_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embedding")


async def generate_embedding_async(text: str) -> list[float] | None:
    """Async version: Generate a single embedding vector for the given text."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_embedding_executor, generate_embedding, text)


async def generate_embeddings_batch_async(texts: list[str]) -> list[list[float] | None]:
    """Async version: Generate embeddings for a list of texts.

    Runs the synchronous model.encode() in a thread pool to avoid
    blocking the event loop. This is critical for API responsiveness.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_embedding_executor, generate_embeddings_batch, texts)


async def get_query_embedding_async(text: str) -> list[float] | None:
    """Async version of generate_query_embedding with Redis caching."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_embedding_executor, generate_query_embedding, text)


def shutdown_embedding_executor():
    """Clean shutdown of the embedding thread pool and model."""
    global _model
    _embedding_executor.shutdown(wait=True, cancel_futures=False)
    # Unload model to free memory
    if _model is not None:
        try:
            # Clear model references
            _model = None
            log.info("[embeddings] Model unloaded from memory")
        except Exception as e:
            log.warning(f"[embeddings] Error unloading model: {e}")


def get_model_status():
    """Return whether model is loaded and memory status."""
    return {
        "model_loaded": _model is not None,
        "executor_active": not _embedding_executor._shutdown,
    }
