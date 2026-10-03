"""Entity extraction helpers.

The full spaCy/lexicon pipeline was removed in the MK-only simplify pass, but
several intelligence/synthesis and research modules still import these symbols.
Provide dependency-free, regex-based implementations with the same shapes so
those callers keep working (and never crash on import or at runtime).
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("presek.entities")

# Capitalized/Cyrillic tokens (letters + hyphen), length >= 3.
_PROPER_NOUN = re.compile(
    r"\b[A-ZА-ШЌЃЉЊЏЖЧЏШ][A-Za-zА-Яа-яЌќЃѓЉњЊџЏЏЖжЧчШшЏЏ-]{2,}"
    r"(?:\s+[A-ZА-ШЌЃЉЊЏЖЧЏШ][A-Za-zА-Яа-яЌќЃѓЉњЊџЏЏЖжЧчШшЏЏ-]{2,}){0,2}"
)

_STOPWORDS = {
    "The",
    "This",
    "That",
    "With",
    "From",
    "But",
    "And",
    "For",
    "Reuters",
    "Photo",
    "Read",
    "More",
    "News",
    "Video",
}

_KNOWN_PERSON_HINTS = ("Скопје", "Македонија")


def normalize_entity_name(name, *a, **kw):
    return str(name or "").strip()


def _is_name_like_phrase(candidate: str) -> bool:
    parts = candidate.split()
    return 1 <= len(parts) <= 3 and all(len(p) >= 3 for p in parts)


def extract_entities(text: str, max_entities: int = 5) -> list[dict]:
    """Lightweight proper-noun entity extraction (no external NLP deps)."""
    if not text:
        return []
    found: dict[str, str] = {}
    for candidate in _PROPER_NOUN.findall(str(text)[:5000]):
        name = re.sub(r"\s+", " ", candidate).strip()
        if not name or name in _STOPWORDS or len(name) < 3:
            continue
        if name in found:
            continue
        etype = "PERSON" if _is_name_like_phrase(name) else "ENTITY"
        found[name] = etype
        if len(found) >= max_entities:
            break

    result: list[dict] = []
    for name, etype in found.items():
        canonical = normalize_entity_name(name)
        if not canonical or any(r["name"] == canonical for r in result):
            continue
        result.append({"name": canonical, "type": etype})
        if len(result) >= max_entities:
            break
    return result


def validate_person_names(text):
    """Type-preserving pass-through (full name-hallucination fixer was removed)."""
    if text is None:
        return text
    if isinstance(text, list):
        return [str(t) for t in text]
    return str(text)


def determine_relationship_direction(*a, **kw) -> str:
    return "related"


def update_knowledge_graph(entities, context_text: str = "") -> None:
    """No-op: the knowledge-graph tables were removed in the MK-only simplify."""
    return None
