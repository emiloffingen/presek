"""Synthesis headline/article/summary quality scoring."""

from __future__ import annotations

import re

from core.editorial_quality import weak_editorial_abstraction_count

def _paragraph_fingerprint(text: str) -> str:
    return re.sub(r"\W+", " ", str(text or "").casefold()).strip()

def _expected_article_paragraphs() -> int:
    from core.runtime_limits import LOCAL_SYNTHESIS_SIMPLIFIED_SCHEMA

    return 3 if LOCAL_SYNTHESIS_SIMPLIFIED_SCHEMA else 5


def _score_synthesis_quality(headline: str, article: str, key_facts: list, lang: str = "sr") -> float:
    """
    Evaluates synthesis quality, returning a score between 0.0 and 1.0.
    Docks points for repetition, poor citation/fact density, and broken paragraph structure.
    """
    score = 1.0
    if not headline or not article:
        return 0.0

    expected_paragraphs = _expected_article_paragraphs()
    min_citations_or_facts = 3 if expected_paragraphs == 3 else 4

    # 1. Headline repetition in body
    h_clean = headline.lower().strip()
    a_clean = article.lower().strip()
    if h_clean in a_clean:
        score -= 0.4

    # 2. Source-grounded facts/citations density
    citations = re.findall(r'\[\d+\]', article)
    facts_count = len(key_facts) if isinstance(key_facts, list) else 0
    if len(citations) < min_citations_or_facts and facts_count < min_citations_or_facts:
        score -= 0.3

    # 3. Paragraph structure check (3 for compact Gemma schema, 5 for full schema)
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', article) if p.strip()]
    if len(paragraphs) != expected_paragraphs:
        score -= 0.3

    weak_count = weak_editorial_abstraction_count(article)
    if weak_count:
        score -= min(0.35, weak_count * 0.18)

    return max(0.0, min(1.0, score))


_EDITORIAL_VAGUE_PATTERNS = (
    r"\brazvoj događaja\b",
    r"\bsituacija (?:je |ostaje )?dinamična\b",
    r"\bizvori izveštavaju\b",
    r"\bprivukao je pažnju\b",
    r"\bostaje da se vidi\b",
    r"\bširi kontekst\b",
    r"\bmedijski izvori\b",
    r"\bразвојот на настаните\b",
    r"\bситуацијата (?:е |останува )?динамична\b",
    r"\bизворите известуваат\b",
    r"\bпривлече внимание\b",
    r"\bостанува да се види\b",
    r"\bпоширок контекст\b",
    r"\bмедиумски извори\b",
)


def _split_summary_items(summary) -> list[str]:
    if isinstance(summary, list):
        raw_items = summary
    else:
        raw_items = str(summary or "").splitlines()

    items = []
    for item in raw_items:
        clean = re.sub(r"^[\s\-•*\d.)]+", "", str(item or "")).strip()
        clean = re.sub(r"^(šta se desilo|što se slučilo|што се случи|značaj|значење|otvoreno|отворено)\s*:\s*", "", clean, flags=re.IGNORECASE)
        if clean:
            items.append(clean)
    return items


def _score_editorial_summary(summary, article: str = "", lang: str = "sr") -> float:
    """
    Scores whether synthesis bullets read like editorial judgement rather than
    generic extraction. The target is 3-4 differentiated bullets: development,
    significance, source agreement/difference, and uncertainty/next signal.
    """
    items = _split_summary_items(summary)
    if not items:
        return 0.0

    score = 1.0
    if len(items) < 3:
        score -= 0.35
    if len(items) > 4:
        score -= 0.15

    all_text = " ".join(items)
    lowered = all_text.casefold()
    item_terms = []
    for item in items:
        words = set(re.findall(r"[A-Za-zÀ-žА-џ0-9]{4,}", item.casefold()))
        item_terms.append(words)

    # Repetition check: bullets should not be paraphrases of the same headline.
    for idx, current in enumerate(item_terms):
        for previous in item_terms[:idx]:
            if not current or not previous:
                continue
            overlap = len(current & previous) / max(1, min(len(current), len(previous)))
            if overlap > 0.72:
                score -= 0.18
                break

    vague_hits = sum(1 for pattern in _EDITORIAL_VAGUE_PATTERNS if re.search(pattern, lowered, flags=re.IGNORECASE))
    score -= min(0.3, vague_hits * 0.1)

    significance_markers = (
        "zato", "jer", "znač", "posled", "utic", "rizik", "ulog", "instituc", "budžet", "bezbed",
        "поради", "затоа", "знач", "послед", "влија", "ризик", "влог", "институц", "буџет", "безбед",
    )
    verification_markers = (
        "potvr", "saglas", "razlik", "nejas", "nepotvr", "otvoren", "izvor", "naredn", "sledeć",
        "потврд", "соглас", "разлик", "нејас", "непотврд", "отворен", "извор", "следн",
    )
    if not any(marker in lowered for marker in significance_markers):
        score -= 0.2
    if not any(marker in lowered for marker in verification_markers):
        score -= 0.2

    # Avoid summary bullets that simply duplicate article opening sentences.
    article_start = _paragraph_fingerprint(" ".join(str(article or "").split()[:80]))
    duplicate_bullets = 0
    for item in items:
        item_key = _paragraph_fingerprint(item)
        if item_key and len(item_key) > 50 and item_key in article_start:
            duplicate_bullets += 1
    score -= min(0.2, duplicate_bullets * 0.1)

    return max(0.0, min(1.0, score))


def _compute_lightweight_quality_score(synthetic_headline, summary, generated_article, key_facts, lang="sr"):
    article_score = _score_synthesis_quality(synthetic_headline, generated_article, key_facts, lang)
    summary_score = _score_editorial_summary(summary, generated_article, lang)
    return round((article_score * 0.65) + (summary_score * 0.35), 3)
