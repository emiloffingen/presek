"""
embeddings.py — Vector embedding generation for semantic search in Presek.

Uses Google's text-embedding-004 model (free tier, multilingual, 768 dimensions).
Supports batch embedding for efficient processing of multiple articles.
"""
import json
import logging
import urllib.request
import urllib.error
import time

from config import GOOGLE_API_KEY

log = logging.getLogger("presek")

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIM = 768
EMBEDDING_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:batchEmbedContents"

# Max texts per batch (Google API limit is 100)
BATCH_SIZE = 100


def generate_embedding(text: str) -> list[float] | None:
    """Generate a single embedding vector for the given text."""
    results = generate_embeddings_batch([text])
    if results and results[0] is not None:
        return results[0]
    return None


def generate_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """
    Generate embeddings for a list of texts using Google's Batch API.
    """
    if not GOOGLE_API_KEY or not texts:
        return [None] * len(texts)

    all_vectors = []
    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i : i + BATCH_SIZE]
        vectors = _embed_chunk(chunk)
        all_vectors.extend(vectors)
        # Small delay to respect free-tier rate limits if needed
        if len(texts) > BATCH_SIZE:
            time.sleep(0.5)

    return all_vectors


def _embed_chunk(texts: list[str]) -> list[list[float] | None]:
    if not GOOGLE_API_KEY:
        return [None] * len(texts)

    requests = []
    for text in texts:
        # Truncate text to stay within model limits (~2048 tokens or ~10k chars)
        truncated = str(text or "")[:2000]
        requests.append({
            "model": f"models/{EMBEDDING_MODEL}",
            "content": {"parts": [{"text": truncated}]},
            "taskType": "RETRIEVAL_DOCUMENT",
            "outputDimensionality": EMBEDDING_DIM
        })

    payload = json.dumps({"requests": requests}).encode("utf-8")
    url = f"{EMBEDDING_URL}?key={GOOGLE_API_KEY}"

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        embeddings = data.get("embeddings", [])
        return [e.get("values") for e in embeddings]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        log.warning(f"[embeddings] Batch error {e.code}: {body}")
    except Exception as e:
        log.warning(f"[embeddings] Unexpected error: {e}")

    return [None] * len(texts)


def embed_recent_articles(hours: int = 24, limit: int = 100) -> int:
    """
    Generate and store embeddings for recent articles that don't have one yet.
    Returns the count of articles embedded.
    """
    from database import db_manager as db

    if not GOOGLE_API_KEY:
        log.warning("[embeddings] Skipping embed_recent_articles: no GOOGLE_API_KEY")
        return 0

    try:
        rows = db.execute(
            """SELECT id, title, description FROM articles
               WHERE embedding IS NULL
                 AND created_at >= NOW() - INTERVAL '%s hours'
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
            db.execute(
                "UPDATE articles SET embedding = %s WHERE id = %s",
                (vec, row["id"]),
                fetch=False,
            )
            embedded += 1
        except Exception as e:
            log.warning(f"[embeddings] Failed to store embedding for article {row['id']}: {e}")

    log.info(f"[embeddings] Embedded {embedded}/{len(rows)} recent articles")
    return embedded


def generate_query_embedding(text: str) -> list[float] | None:
    """Generate an embedding optimized for search queries (uses RETRIEVAL_QUERY task type)."""
    if not GOOGLE_API_KEY or not text:
        return None

    truncated = text[:2000]
    payload = json.dumps({
        "requests": [{
            "model": f"models/{EMBEDDING_MODEL}",
            "content": {"parts": [{"text": truncated}]},
            "taskType": "RETRIEVAL_QUERY",
            "outputDimensionality": EMBEDDING_DIM
        }]
    }).encode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent?key={GOOGLE_API_KEY}"

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        embedding = data.get("embedding", {})
        if embedding:
            return embedding.get("values")
    except Exception as e:
        log.warning(f"[embeddings] Query embedding error: {e}")

    return None
