"""Sanitize cluster synthesis outputs before persistence."""

from __future__ import annotations

import re

from core.api_helpers import normalize_perspectives, normalize_summary_text
from core.editorial_quality import normalize_serbian_editorial_text
from core.entities import validate_person_names
from nlp.generation import synthesize_cluster_fallback
from nlp.utils import (
    extract_clean_summary_text,
    looks_like_leaked_json_fragment,
    paragraph_fingerprint as _paragraph_fingerprint,
)


def dedupe_generated_article(text: str) -> str:
    parts = [part.strip() for part in re.split(r"\n{2,}", str(text or "")) if part.strip()]
    kept = []
    seen = set()
    for part in parts:
        key = _paragraph_fingerprint(part)
        if not key or key in seen:
            continue
        if any(key and (key in prev or prev in key) and min(len(key), len(prev)) > 120 for prev in seen):
            continue
        seen.add(key)
        kept.append(part)
    return "\n\n".join(kept).strip()


def polish_generated_article(text: str, lang: str = "mk") -> str:
    clean = str(text or "").strip()
    if not clean:
        return ""

    heading_patterns = (
        r"^\s*(синтеза|уреднички преглед|уредничка синтеза|анализа|article)\s*:?\s*$",
        r"^\s*(sinteza|urednički pregled|urednicki pregled|urednička sinteza|urednicka sinteza|analiza|article)\s*:?\s*$",
    )
    meta_leads = (
        (r"^\s*Овој кластер(?:\s+вести)?\s+", ""),
        (r"^\s*Оваа синтеза\s+", ""),
        (r"^\s*Според медиумските извештаи,\s*", ""),
        (r"^\s*Во вестите се наведува дека\s+", ""),
        (r"^\s*Ovaj klaster(?:\s+vesti)?\s+", ""),
        (r"^\s*Ova sinteza\s+", ""),
        (r"^\s*Prema medijskim izveštajima,\s*", ""),
        (r"^\s*U vestima se navodi da\s+", ""),
    )

    polished_parts = []
    for part in re.split(r"\n{2,}", clean):
        paragraph = re.sub(r"\s+", " ", part).strip()
        if not paragraph:
            continue
        if any(re.match(pattern, paragraph, flags=re.IGNORECASE) for pattern in heading_patterns):
            continue
        for pattern, replacement in meta_leads:
            paragraph = re.sub(pattern, replacement, paragraph, flags=re.IGNORECASE).strip()
        if paragraph:
            polished_parts.append(paragraph)

    return "\n\n".join(polished_parts).strip()


def sanitize_text_field(text: str) -> str:
    return extract_clean_summary_text(text or "")


def _clean_macedonian(text: str) -> str:
    from tasks.intelligence.synthesis_mk_cleanup import _clean_macedonian_spelling_and_script

    return _clean_macedonian_spelling_and_script(text)


def sanitize_synthesis_outputs(summary, generated_article, perspectives, article_rows, lang="mk"):
    fallback = None
    if isinstance(summary, list):
        clean_summary = normalize_summary_text([sanitize_text_field(str(item or "")) for item in summary])
    else:
        clean_summary = normalize_summary_text(sanitize_text_field(str(summary or "")))
    clean_article = polish_generated_article(
        dedupe_generated_article(validate_person_names(generated_article or "")),
        lang=lang,
    )

    if looks_like_leaked_json_fragment(clean_summary):
        fallback = fallback or synthesize_cluster_fallback(article_rows, lang=lang)
        clean_summary = normalize_summary_text(sanitize_text_field(fallback.get("summary", "")))

    if looks_like_leaked_json_fragment(clean_article) or len(clean_article) < 80:
        fallback = fallback or synthesize_cluster_fallback(article_rows, lang=lang)
        clean_article = polish_generated_article(
            dedupe_generated_article(fallback.get("generated_article", "")),
            lang=lang,
        )

    clean_perspectives = normalize_perspectives(perspectives, lang=lang)
    if not clean_perspectives:
        fallback = fallback or synthesize_cluster_fallback(article_rows, lang=lang)
        clean_perspectives = normalize_perspectives(fallback.get("perspectives", []), lang=lang)

    if lang == "mk":
        if isinstance(clean_summary, str):
            clean_summary = _clean_macedonian(clean_summary)
        elif isinstance(clean_summary, list):
            clean_summary = [_clean_macedonian(item) for item in clean_summary]

        clean_article = _clean_macedonian(clean_article)

        if isinstance(clean_perspectives, list):
            for perspective in clean_perspectives:
                if isinstance(perspective, dict):
                    if "angle" in perspective:
                        perspective["angle"] = _clean_macedonian(perspective["angle"])
                    if "content" in perspective:
                        perspective["content"] = _clean_macedonian(perspective["content"])
    elif lang == "sr":
        if isinstance(clean_summary, str):
            clean_summary = normalize_serbian_editorial_text(clean_summary)
        elif isinstance(clean_summary, list):
            clean_summary = [normalize_serbian_editorial_text(item) for item in clean_summary]

        clean_article = normalize_serbian_editorial_text(clean_article)

        if isinstance(clean_perspectives, list):
            for perspective in clean_perspectives:
                if isinstance(perspective, dict):
                    if "angle" in perspective:
                        perspective["angle"] = normalize_serbian_editorial_text(perspective["angle"])
                    if "content" in perspective:
                        perspective["content"] = normalize_serbian_editorial_text(perspective["content"])

    return clean_summary, clean_article, clean_perspectives
