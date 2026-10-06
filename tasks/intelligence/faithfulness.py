"""Phase 1 (shadow): semantic faithfulness scoring for MK syntheses.

Scores every atomic claim (key_facts + summary bullets) against chunked
source articles using the existing local e5 ONNX stack. Shadow mode only:
computes and logs the score, never blocks publishing. After ~2 weeks of
distributions we calibrate the threshold and enable Phase 2 (judge + block).
"""

from __future__ import annotations

import logging
import math
import os
import re

log = logging.getLogger("presek.faithfulness")

# Cosine floor below which a claim counts as unsupported. Calibrated Oct 2026
# on production pairs: true paraphrased support scores ~0.40, unrelated
# cross-cluster pairs max ~0.27 (mean ~0.02). 0.33 splits them with margin.
SUPPORT_THRESHOLD = float(os.environ.get("FAITHFULNESS_SUPPORT_THRESHOLD", "0.33"))
# Skip scoring for tiny clusters where there is nothing to check against.
MIN_CHUNKS = int(os.environ.get("FAITHFULNESS_MIN_CHUNKS", "2"))
MAX_CLAIMS = 12

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return " ".join(text.split())


def extract_claims(summary, key_facts) -> list[tuple[str, str]]:
    """Atomic checkable claims: (kind, text). Key facts first (they block)."""
    claims: list[tuple[str, str]] = []
    for fact in key_facts or []:
        fact = _clean_text(fact)
        if len(fact) >= 12:
            claims.append(("key_fact", fact))
    if isinstance(summary, list):
        bullets = summary
    else:
        bullets = str(summary or "").split("\n")
    for bullet in bullets:
        bullet = _clean_text(re.sub(r"^[\-\*\d\.\)\s]+", "", str(bullet)))
        if len(bullet) >= 20:
            claims.append(("bullet", bullet))
    return claims[:MAX_CLAIMS]


def chunk_articles(article_rows) -> list[str]:
    """~3-sentence windows from title + full content/description."""
    chunks: list[str] = []
    for row in article_rows or []:
        if not isinstance(row, dict):
            continue
        body = _clean_text(row.get("full_content") or row.get("description") or row.get("summary") or "")
        title = _clean_text(row.get("title") or "")
        if title:
            chunks.append(title)
        sentences = [s for s in _SENT_SPLIT_RE.split(body) if len(s) > 20]
        for i in range(0, len(sentences), 3):
            window = " ".join(sentences[i : i + 3])
            if len(window) > 40:
                chunks.append(window[:1500])
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique = []
    for chunk in chunks:
        if chunk not in seen:
            seen.add(chunk)
            unique.append(chunk)
    return unique


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def score_faithfulness(
    summary,
    key_facts,
    article_rows,
    threshold: float = SUPPORT_THRESHOLD,
) -> tuple[float | None, list[dict]]:
    """Return (faithfulness_score, unsupported_claims).

    Score = share of claims with max chunk-cosine >= threshold. Returns
    (None, []) when scoring is impossible (no claims/chunks/model) so the
    caller treats it as unscored, never as failed.
    """
    claims = extract_claims(summary, key_facts)
    chunks = chunk_articles(article_rows)
    if not claims or len(chunks) < MIN_CHUNKS:
        return None, []
    try:
        from core import embeddings as emb

        claim_vecs = [emb.generate_query_embedding(text) for _, text in claims]
        chunk_vecs = emb.generate_embeddings_batch(chunks)
    except Exception as e:
        log.debug(f"[faithfulness] embedding backend unavailable: {e}")
        return None, []
    if any(not v for v in claim_vecs) or any(not v for v in chunk_vecs):
        return None, []
    unsupported: list[dict] = []
    supported = 0
    for (kind, text), cvec in zip(claims, claim_vecs):
        best = max(_cosine(cvec, chv) for chv in chunk_vecs)
        if best >= threshold:
            supported += 1
        else:
            unsupported.append({"kind": kind, "claim": text[:300], "support": round(best, 3)})
    return round(supported / len(claims), 3), unsupported


def log_faithfulness_shadow(
    cluster_id: str,
    summary,
    key_facts,
    article_rows,
    provider: str | None = None,
) -> float | None:
    """Phase 1 entrypoint: score, log, never raise, never block."""
    try:
        score, unsupported = score_faithfulness(summary, key_facts, article_rows)
    except Exception as e:
        log.debug(f"[faithfulness] shadow scoring failed for {cluster_id}: {e}")
        return None
    if score is None:
        return None
    key_facts_bad = sum(1 for u in unsupported if u["kind"] == "key_fact")
    log.info(
        "[faithfulness:shadow] cluster=%s provider=%s score=%.3f claims=%d unsupported=%d key_facts_bad=%d",
        cluster_id,
        provider or "unknown",
        score,
        len(extract_claims(summary, key_facts)),
        len(unsupported),
        key_facts_bad,
    )
    return score
