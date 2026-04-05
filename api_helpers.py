"""
api_helpers.py — Shared helpers used by both routes/api.py (Flask) and api_fast.py (FastAPI).

Keeping these in one place ensures bug fixes and behavioural changes apply everywhere.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from local_nlp import build_citation_snippet, TAG_NOISE_WORDS

_EXTRA_NOISE = {"вести", "вест", "извор", "извори", "кластер"}


def normalize_perspectives(raw_perspectives) -> list[dict]:
    """
    Normalise a raw perspectives value into a clean list of {angle, content} dicts.

    Accepts:
    - A JSON string (decoded first)
    - A list of dicts (with flexible key names: angle/label/title/name, content/text/description)
    - A list of plain strings
    """
    if not raw_perspectives:
        return []
    if isinstance(raw_perspectives, str):
        try:
            raw_perspectives = json.loads(raw_perspectives)
        except Exception:
            return []
    if not isinstance(raw_perspectives, list):
        return []

    result = []
    for item in raw_perspectives:
        if isinstance(item, str):
            content = item.strip()
            if content:
                result.append({"angle": "Перспектива", "content": content})
            continue
        if not isinstance(item, dict):
            continue
        angle = str(
            item.get("angle")
            or item.get("label")
            or item.get("title")
            or item.get("name")
            or ""
        ).strip()
        content = str(
            item.get("content")
            or item.get("text")
            or item.get("description")
            or ""
        ).strip()
        if not angle and not content:
            continue
        result.append({"angle": angle or "Перспектива", "content": content})

    return result


def default_related_questions(question: str, category: Optional[str] = None) -> list[str]:
    fallback = [
        "Што е главниот развој во оваа приказна?",
        "Како се разликуваат изворите во известувањето?",
        "Што сè уште не е потврдено?",
    ]
    if category:
        fallback[0] = f"Кој е најважниот развој во темата {str(category).lower()}?"
    return [q for q in fallback if q.strip() and q.strip() != question.strip()][:3]


def text_terms(text: str) -> set[str]:
    terms = re.findall(r"[A-Za-zА-Яа-яЀ-ӿ0-9]{3,}", (text or "").lower())
    return {t for t in terms if t not in TAG_NOISE_WORDS and t not in _EXTRA_NOISE}


def rank_cluster_citations(
    question: str,
    answer: str,
    articles: list[dict],
    preferred_numbers: list,
) -> list[dict]:
    question_terms = text_terms(question)
    answer_terms = text_terms(answer)
    combined_terms = question_terms | answer_terms

    preferred_order = []
    for raw in preferred_numbers or []:
        try:
            idx = int(raw)
        except Exception:
            continue
        if idx not in preferred_order:
            preferred_order.append(idx)

    ranked = []
    for idx, article in enumerate(articles, start=1):
        article_text = " ".join([
            str(article.get("title") or ""),
            str(article.get("description") or ""),
            str(article.get("source") or ""),
        ])
        article_terms = text_terms(article_text)
        overlap = len(combined_terms & article_terms)
        preferred_bonus = 5 if idx in preferred_order else 0
        title_bonus = 1 if question_terms & text_terms(str(article.get("title") or "")) else 0
        ranked.append((
            preferred_bonus + overlap + title_bonus,
            -idx,
            {
                "source": article.get("source"),
                "title": article.get("title"),
                "link": article.get("link"),
                "created_at": article.get("created_at"),
                "snippet": build_citation_snippet(article),
            },
        ))

    ranked.sort(reverse=True)
    top = [item[2] for item in ranked if item[0] > 0]
    if top:
        return top[:3]
    return [
        {
            "source": article.get("source"),
            "title": article.get("title"),
            "link": article.get("link"),
            "created_at": article.get("created_at"),
            "snippet": build_citation_snippet(article),
        }
        for article in articles[:2]
    ]
