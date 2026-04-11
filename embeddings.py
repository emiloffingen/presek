"""
embeddings.py — Vector embedding generation for semantic search in Presek.

Uses Cloud API (Mistral) for embedding generation to save local RAM.
Replaces the previous local sentence-transformers model.
"""
import logging
import json
import urllib.request
import urllib.error
from config import MISTRAL_API_KEY, CF_AI_URL

log = logging.getLogger("presek")

# Mistral Embedding Configuration
EMBEDDING_MODEL = "mistral-embed"
EMBEDDING_DIM = 1024  # Mistral embed is 1024 dims
MISTRAL_EMBED_URL = "https://api.mistral.ai/v1/embeddings"

def generate_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """Generate embeddings for a list of texts using the Mistral Cloud API."""
    if not texts or not MISTRAL_API_KEY:
        return [None] * len(texts)

    # Truncate and clean texts
    cleaned = [str(t or "").strip()[:4000] for t in texts]
    if not any(cleaned):
        return [None] * len(texts)

    payload = {
        "model": EMBEDDING_MODEL,
        "input": cleaned
    }

    # Call Mistral API directly (Gateway seems to have 403 issues)
    url = MISTRAL_EMBED_URL
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }

    try:
        data_encoded = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_encoded, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # Mistral returns data in order of input
            vectors = [item["embedding"] for item in data["data"]]
            return vectors
    except Exception as e:
        log.warning(f"[embeddings] Mistral Cloud API error: {e}")
        return [None] * len(texts)

def generate_embedding(text: str) -> list[float] | None:
    """Generate a single embedding vector."""
    results = generate_embeddings_batch([text])
    return results[0] if results else None

def generate_query_embedding(text: str) -> list[float] | None:
    """Generate an embedding for a search query with Redis caching."""
    if not text: return None
    clean_text = text.strip().lower()
    if not clean_text: return None

    from utils import redis_client
    cache_key = f"emb:v2:query:{clean_text}" # v2 for 1024 dim
    
    try:
        cached = redis_client.get(cache_key)
        if cached: return json.loads(cached)
    except: pass

    vector = generate_embedding(text)
    if vector:
        try:
            redis_client.setex(cache_key, 86400, json.dumps(vector))
        except: pass
    return vector

def embed_recent_articles(hours: int = 24, limit: int = 50) -> int:
    """Generate and store embeddings for recent articles using Mistral API."""
    from database import db_manager as db

    rows = db.execute(
        """SELECT id, title, description FROM articles
           WHERE (embedding IS NULL OR vector_dims(embedding) != 1024)
             AND created_at >= NOW() - (%s * INTERVAL '1 hour')
           ORDER BY created_at DESC
           LIMIT %s""",
        (hours, limit)
    )
    if not rows: return 0

    texts = [f"{r['title']}. {r.get('description') or ''}" for r in rows]
    vectors = generate_embeddings_batch(texts)

    embedded = 0
    for row, vec in zip(rows, vectors):
        if not vec: continue
        try:
            vec_str = "[" + ",".join(map(str, vec)) + "]"
            db.execute(
                "UPDATE articles SET embedding = %s::vector WHERE id = %s",
                (vec_str, row["id"]),
                fetch=False,
            )
            embedded += 1
        except Exception as e:
            log.warning(f"[embeddings] Failed to store embedding for {row['id']}: {e}")

    log.info(f"[embeddings] Cloud Embedded {embedded}/{len(rows)} articles")
    return embedded

def get_shared_model():
    """No local model anymore."""
    return None
