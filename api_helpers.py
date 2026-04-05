"""
api_helpers.py — Shared helpers used by both routes/api.py (Flask) and api_fast.py (FastAPI).

Keeping these in one place ensures bug fixes and behavioural changes apply everywhere.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from local_nlp import build_citation_snippet, TAG_NOISE_WORDS
from utils import get_source_trust_label, build_cluster_source_signals

_EXTRA_NOISE = {"вести", "вест", "извор", "извори", "кластер"}
_GENERIC_ANGLES = {"перспектива", "агол", "точка", "став", "гледиште"}


def _clean_text_block(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "")
    text = re.sub(r"^\s*(summary|резиме|сублимат|статии)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^[•*\-\u2022]+\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _infer_perspective_angle(content: str, fallback: str = "Клучен агол") -> str:
    lowered = content.lower()
    if any(token in lowered for token in ("разлик", "акцент", "формулац", "наглас")):
        return "Различни акценти"
    if any(token in lowered for token in ("заеднич", "повеќето извори", "иста линија", "сите извори")):
        return "Заедничка линија"
    if any(token in lowered for token in ("отворено", "нејас", "непотвр", "сè уште не", "останува")):
        return "Што останува отворено"
    if any(token in lowered for token in ("реакц", "одговор", "коментар", "осуд")):
        return "Реакции"
    if any(token in lowered for token in ("контекст", "позадин", "поширок")):
        return "Поширок контекст"
    return fallback


def normalize_summary_text(raw_summary) -> str:
    if not raw_summary:
        return ""

    text = str(raw_summary).replace("\r", "\n")
    lines = []
    seen = set()

    for raw_line in text.split("\n"):
        clean = _clean_text_block(raw_line)
        if not clean:
            continue
        if clean.lower() == "статии:":
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(clean)

    if not lines:
        return ""

    if len(lines) == 1:
        return lines[0]

    return "\n".join(f"• {line}" for line in lines[:4])


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
    seen = set()
    for item in raw_perspectives:
        if isinstance(item, str):
            content = _clean_text_block(item)
            if content:
                angle = _infer_perspective_angle(content)
                key = content.casefold()
                if key not in seen:
                    seen.add(key)
                    result.append({"angle": angle, "content": content})
            continue
        if not isinstance(item, dict):
            continue
        angle = _clean_text_block(
            item.get("angle")
            or item.get("label")
            or item.get("title")
            or item.get("name")
            or ""
        )
        content = _clean_text_block(
            item.get("content")
            or item.get("text")
            or item.get("description")
            or ""
        )
        if not content:
            continue
        if not angle or angle.casefold() in _GENERIC_ANGLES:
            angle = _infer_perspective_angle(content)
        key = content.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append({"angle": angle or "Клучен агол", "content": content})

    return result[:4]


def default_related_questions(question: str, category: Optional[str] = None) -> list[str]:
    fallback = [
        "Што е главниот развој во оваа приказна?",
        "Како се разликуваат изворите во известувањето?",
        "Што сè уште не е потврдено?",
    ]
    if category:
        fallback[0] = f"Кој е најважниот развој во темата {str(category).lower()}?"
    return [q for q in fallback if q.strip() and q.strip() != question.strip()][:3]


def related_questions_from_context(
    question: str,
    category: Optional[str] = None,
    *,
    has_perspectives: bool = False,
    has_multiple_sources: bool = False,
    has_unclear_points: bool = False,
) -> list[str]:
    suggestions = []
    lowered = (question or "").strip().lower()

    def add(text: str):
        text = str(text or "").strip()
        if text and text.casefold() != lowered and text not in suggestions:
            suggestions.append(text)

    if not any(token in lowered for token in ("разлику", "извор", "перспектив")) and (has_perspectives or has_multiple_sources):
        add("Како се разликуваат изворите во известувањето?")
    if not any(token in lowered for token in ("нејас", "непотвр", "отворено")):
        add("Што останува нејасно или непотврдено?")
    if not any(token in lowered for token in ("следно", "понатаму", "последиц", "реакц")):
        add("Што следува понатаму во оваа приказна?")
    if has_multiple_sources and not any(token in lowered for token in ("најваж", "ново", "главно")):
        add("Што е најважното ново во оваа вест?")

    for item in default_related_questions(question, category):
        add(item)

    if has_unclear_points:
        add("Кои детали сè уште зависат од следни потврди?")

    return suggestions[:3]


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

    source_signals = build_cluster_source_signals(articles)
    signal_by_key = {}
    for article, signal in zip(articles, source_signals):
        key = (
            str(article.get("source") or ""),
            str(article.get("title") or ""),
            str(article.get("link") or ""),
        )
        signal_by_key[key] = signal

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
        trust_bonus = 1 if get_source_trust_label(str(article.get("source") or "")) == "Висока доверба" else 0
        signal = signal_by_key.get((
            str(article.get("source") or ""),
            str(article.get("title") or ""),
            str(article.get("link") or ""),
        )) or {}
        ranked.append((
            preferred_bonus + overlap + title_bonus + trust_bonus,
            -idx,
            {
                "source": article.get("source"),
                "title": article.get("title"),
                "link": article.get("link"),
                "created_at": article.get("created_at"),
                "snippet": build_citation_snippet(article),
                "trust_label": signal.get("trust_label") or get_source_trust_label(str(article.get("source") or "")),
                "role_label": signal.get("role_label", ""),
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
            "trust_label": get_source_trust_label(str(article.get("source") or "")),
            "role_label": "",
        }
        for article in articles[:2]
    ]
