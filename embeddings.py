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

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 3072
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
    Generate embeddings for a batch of texts using Google's embedding API.
    Returns a list of embedding vectors (or None for failed items).
    """
    if not GOOGLE_API_KEY:
        log.warning("[embeddings] No GOOGLE_API_KEY configured")
        return [None] * len(texts)

    if not texts:
        return []

    results: list[list[float] | None] = [None] * len(texts)

    # Process in chunks of BATCH_SIZE
    for chunk_start in range(0, len(texts), BATCH_SIZE):
        chunk = texts[chunk_start:chunk_start + BATCH_SIZE]
        chunk_results = _embed_chunk(chunk)
        for i, vec in enumerate(chunk_results):
            results[chunk_start + i] = vec

    return results


def _embed_chunk(texts: list[str]) -> list[list[float] | None]:
    """Embed a single chunk (up to BATCH_SIZE texts) via the API."""
    # Truncate texts to ~2000 chars to stay within token limits
    truncated = [t[:2000] if t else "" for t in texts]

    requests_list = [
        {
            "model": f"models/{EMBEDDING_MODEL}",
            "content": {"parts": [{"text": t}]},
            "taskType": "RETRIEVAL_DOCUMENT",
        }
        for t in truncated
    ]

    payload = json.dumps({"requests": requests_list}).encode("utf-8")
    url = f"{EMBEDDING_URL}?key={GOOGLE_API_KEY}"

    delays = [2, 5]
    for attempt, delay in enumerate([0] + delays):
        if delay:
            time.sleep(delay)

        try:
            t0 = time.time()
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            elapsed = round(time.time() - t0, 2)

            embeddings = data.get("embeddings", [])
            if len(embeddings) != len(texts):
                log.warning(f"[embeddings] Expected {len(texts)} embeddings, got {len(embeddings)}")
                return [None] * len(texts)

            log.info(f"[embeddings] Generated {len(texts)} embeddings in {elapsed}s (attempt {attempt + 1})")
            return [e.get("values") for e in embeddings]

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e else ""
            if e.code == 429:
                log.info(f"[embeddings] 429 rate-limited (attempt {attempt + 1}), retrying...")
                continue
            log.warning(f"[embeddings] HTTP {e.code}: {err_body[:200]}")
            return [None] * len(texts)
        except Exception as e:
            log.warning(f"[embeddings] Error: {e}")
            return [None] * len(texts)

    return [None] * len(texts)


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
        }]
    }).encode("utf-8")

    url = f"{EMBEDDING_URL}?key={GOOGLE_API_KEY}"

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        embeddings = data.get("embeddings", [])
        if embeddings:
            return embeddings[0].get("values")
    except Exception as e:
        log.warning(f"[embeddings] Query embedding error: {e}")

    return None
