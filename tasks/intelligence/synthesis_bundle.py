"""Synthesis bundle helpers: normalization, citations, and source context blocks."""

from __future__ import annotations

import re

from core.api_helpers import normalize_citation_sources, normalize_perspectives, normalize_summary_text
from core.text_extraction import clean_extracted_article_text
from nlp import deShout, synthesize_cluster_fallback
from nlp.categories import normalize_headline

def _normalize_cluster_synthesis(summary, perspectives, article_rows, lang="mk"):
    clean_summary = normalize_summary_text(summary)
    clean_perspectives = normalize_perspectives(perspectives)

    if clean_summary and clean_perspectives:
        return clean_summary, clean_perspectives

    fallback = synthesize_cluster_fallback(article_rows, lang=lang)
    fallback_summary = normalize_summary_text(fallback.get("summary", ""))
    fallback_perspectives = normalize_perspectives(fallback.get("perspectives", []))

    if not clean_summary:
        clean_summary = fallback_summary
    if not clean_perspectives:
        clean_perspectives = fallback_perspectives

    return clean_summary, clean_perspectives


def _ensure_dict(value):
    return value if isinstance(value, dict) else {}


def _fallback_key_facts(article_rows, summary="", limit=4):
    facts = []
    seen = set()

    for article in article_rows or []:
        source = str(article.get("source") or "izvor").strip()
        title = deShout(str(article.get("title") or "").strip())
        if not title:
            continue
        fact = f"{source}: {title}"
        key = fact.casefold()
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact[:220])
        if len(facts) >= limit:
            break
    return facts


def _build_citation_sources(article_rows):
    ordered = []
    for item in article_rows or []:
        ordered.append(
            {
                "source": str(item.get("source") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "link": str(item.get("link") or "").strip(),
                "created_at": str(item.get("created_at") or "").strip(),
                "category": str(item.get("category") or "").strip(),
            }
        )
    return normalize_citation_sources(ordered)


def _extract_one_quote_or_fact(text: str) -> str | None:
    if not text:
        return None
    # Look for quotes in text
    quote_patterns = [
        r'["“„»]([^"“„»]{15,})["”„«]',
        r'\'([^\']{15,})\''
    ]
    for pattern in quote_patterns:
        matches = re.findall(pattern, text)
        if matches:
            return matches[0].strip()
    
    # If no quotes, find a sentence containing a number/fact
    sentences = re.split(r'[.!?]\s+', text)
    for s in sentences:
        if any(c.isdigit() for c in s) and len(s) > 20:
            return s.strip()
            
    # Default to the first sentence
    if sentences:
        first = sentences[0].strip()
        if len(first) > 10:
            return first
    return None


def _build_synthesis_source_context(article_rows, lang: str = "sr"):
    # Group and deduplicate by source, preserving order of first occurrence
    seen_sources = set()
    deduped_rows = []
    for row in (article_rows or []):
        source = str(row.get("source") or "").strip().lower()
        if source and source not in seen_sources:
            seen_sources.add(source)
            deduped_rows.append(row)
            
    # Feed only top 4-6 articles (we use 5)
    top_rows = deduped_rows[:5]
    
    blocks = []
    for idx, row in enumerate(top_rows, start=1):
        title = deShout(normalize_headline(str(row.get("title") or "").strip()))
        source = str(row.get("source") or "izvor").strip()
        created_at = str(row.get("created_at") or "").strip()
        category = str(row.get("category") or "").strip()
        topic = str(row.get("topic") or "").strip()
        description = clean_extracted_article_text(str(row.get("description") or "").strip())
        full_content = clean_extracted_article_text(str(row.get("full_content") or "").strip())
        
        evidence = full_content if len(full_content or "") > len(description or "") else description
        evidence = evidence[:1600].strip()
        
        extracted_fact = _extract_one_quote_or_fact(full_content or description)
        
        parts = [f"[{idx}] {source}"]
        if created_at:
            parts.append(f"{'Objavljeno' if lang == 'sr' else 'Објавено'}: {created_at}")
        if category:
            parts.append(f"{'Kategorija' if lang == 'sr' else 'Категорија'}: {category}")
        if topic:
            parts.append(f"{'Tema' if lang == 'sr' else 'Тема'}: {topic}")
        if title:
            parts.append(f"{'Naslov' if lang == 'sr' else 'Наслов'}: {title}")
        if evidence:
            parts.append(f"{'Opis' if lang == 'sr' else 'Опис'}:\n{evidence}")
        if extracted_fact:
            parts.append(f"{'Ključna izjava/činjenica' if lang == 'sr' else 'Клучна изјава/факт'}: {extracted_fact}")
            
        blocks.append("\n".join(parts))
        
    source_count = len(top_rows)
    if lang == "mk":
        header = (
            f"Достапни се {source_count} различни извори. Спореди ги по факти, акценти и пропусти; "
            "не претпоставувај мотиви и не користи податоци што не се во изворите."
        )
    else:
        header = (
            f"Dostupno je {source_count} različitih izvora. Uporedi ih po činjenicama, akcentima i propustima; "
            "ne pretpostavljaj motive i ne koristi podatke koji nisu u izvorima."
        )
    return f"{header}\n\n" + "\n\n".join(blocks) if blocks else ""
