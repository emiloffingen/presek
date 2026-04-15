"""
embeddings.py — Vector embedding generation for semantic search in Presek.

Uses a local sentence-transformers model (paraphrase-multilingual-MiniLM-L12-v2,
384 dims, 50+ languages including Macedonian/Cyrillic). Runs entirely offline
on CPU after the model is downloaded once to ~/.cache/huggingface.

No API key, no quota, no network at runtime.
"""
import logging
import threading

log = logging.getLogger("presek")

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

# Batch size for encode() — MiniLM is small enough that 64 is comfortable on CPU
BATCH_SIZE = 64

_model = None
_model_lock = threading.Lock()


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
        except ImportError:
            log.error("[embeddings] sentence-transformers is not installed. Run: pip install sentence-transformers")
            return None
        try:
            log.info(f"[embeddings] Loading local model '{EMBEDDING_MODEL}' (first run downloads ~120 MB)")
            _model = SentenceTransformer(EMBEDDING_MODEL)
            log.info(f"[embeddings] Model loaded, dim={_model.get_sentence_embedding_dimension()}")
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
    from database import db_manager as db

    try:
        rows = db.execute(
            """SELECT id, title, description FROM articles
               WHERE embedding IS NULL
                 AND created_at >= NOW() - (%s * INTERVAL '1 hour')
               ORDER BY created_at DESC
               LIMIT %s""",
            (hours, limit)
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

    from utils import redis_client
    import json

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

def get_cluster_embedding(cluster_id: str) -> list[float] | None:
    """Calculate the average embedding vector for all articles in a cluster."""
    from database import db_manager as db
    import json
    import numpy as np

    try:
        rows = db.execute(
            "SELECT embedding FROM articles WHERE cluster_id = %s AND embedding IS NOT NULL",
            (cluster_id,)
        )
        if not rows:
            return None
        
        vecs = []
        for r in rows:
            emb = r["embedding"]
            if isinstance(emb, str):
                try: emb = json.loads(emb)
                except: continue
            if isinstance(emb, list) and len(emb) > 0:
                vecs.append(emb)
        
        if not vecs:
            return None
        
        # Centroid calculation via numpy
        avg = np.mean(vecs, axis=0).tolist()
        return avg
    except Exception as e:
        log.warning(f"[embeddings] Failed to calculate cluster embedding for {cluster_id}: {e}")
        return None

