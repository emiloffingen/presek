"""Deterministic, LLM-free cluster overview generation.

When the AI kill-switch (`PRESEK_AI_ENABLED=0`) is active, no model is used to
produce a cluster "editorial overview". This module builds an extractive
overview purely from the source articles' own headline + lead text, so cluster
pages render real content instead of a permanent "generating" placeholder.

Output shape mirrors the model-based synthesizer: {headline, summary, key_facts}.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_WS_RE = re.compile(r"\s+")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
# Sentence-ending punctuation used in Macedonian/Cyrillic and Latin text.
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")


def _clean(text: Any) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", str(text)).strip()


def _truncate(text: str, limit: int) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Avoid cutting mid-word.
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def _first_sentences(text: str, max_sentences: int = 2, limit: int = 320) -> str:
    text = _clean(text)
    if not text:
        return ""
    sentences = [s for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    chosen: list[str] = []
    total = 0
    for s in sentences:
        chosen.append(s.strip())
        total += len(s)
        if len(chosen) >= max_sentences or total >= limit:
            break
    return " ".join(chosen).strip()


def _dedupe(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_extractive_synthesis(articles: list[dict[str, Any]], cluster_title: str = "") -> dict[str, Any]:
    """Build an extractive overview from a cluster's source articles.

    Args:
        articles: list of article dicts with keys title/description/summary/source.
        cluster_title: optional representative title for the cluster.

    Returns:
        dict with headline, summary, and key_facts.
    """
    if not articles:
        return {"headline": "", "summary": "", "key_facts": []}

    sources = _dedupe(
        [_clean(a.get("source")) for a in articles if _clean(a.get("source"))]
    )

    # Headline: representative title, or the strongest (longest) source headline.
    headline = _clean(cluster_title)
    if not headline:
        titles = sorted(
            (_clean(a.get("title")) for a in articles if _clean(a.get("title"))),
            key=len,
            reverse=True,
        )
        headline = titles[0] if titles else ""
    headline = _truncate(headline, 140)

    # Overview: lead of the most representative source. Prefer the article whose
    # title matches the chosen headline, then fall back to the most complete.
    def _pick_primary() -> dict[str, Any]:
        if headline:
            for a in articles:
                if _clean(a.get("title")) == headline:
                    return a
        return max(
            articles,
            key=lambda a: len(_clean(a.get("summary") or a.get("description") or "")),
        )

    paragraphs: list[str] = []
    primary = _pick_primary()
    primary_text = " ".join(
        filter(
            None,
            [
                _clean(primary.get("summary")),
                _clean(primary.get("description")),
                _clean(primary.get("title")),
            ],
        )
    )
    primary_lead = _first_sentences(primary_text, max_sentences=3, limit=420)
    if primary_lead:
        paragraphs.append(primary_lead)

    # Add distinct corroborating details from other sources (up to 2 more).
    ordered = sorted(
        articles,
        key=lambda a: len(_clean(a.get("summary") or a.get("description") or "")),
        reverse=True,
    )
    added = 0
    for art in ordered:
        if art is primary:
            continue
        token = _first_sentences(
            art.get("summary") or art.get("description") or "", max_sentences=1, limit=220
        )
        if not token:
            continue
        if any(token[:60].lower() in p.lower() for p in paragraphs):
            continue
        paragraphs.append(token)
        added += 1
        if added >= 2:
            break

    summary = "\n\n".join(paragraphs).strip()

    # Key facts: distinct one-line leads (capped).
    key_facts = _dedupe(
        [
            _first_sentences(a.get("title") or a.get("description") or "", max_sentences=1, limit=160)
            for a in ordered
        ]
    )[:5]

    return {
        "headline": headline,
        "summary": summary,
        "key_facts": key_facts,
        "source_count": len(sources),
    }


def build_extractive_article_summary(title: str, content: str) -> str:
    """Deterministic short article summary (no LLM)."""
    lead = _first_sentences(content or "", max_sentences=2, limit=300)
    if lead:
        return lead
    return _truncate(title or "", 200)
