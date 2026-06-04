import re
import unicodedata

from nlp.keywords import ENTITY_NOISE_WORDS, _extract_capitalized_phrases
from nlp.utils import cleanAndDecode, transliterate


def _strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize_quality_text(title: str, description: str) -> tuple[str, str]:
    raw = cleanAndDecode(f"{title or ''} {description or ''}")
    latin = transliterate(raw)
    folded = _strip_diacritics(latin).casefold()
    folded = re.sub(r"[_/|]+", " ", folded)
    folded = re.sub(r"\s+", " ", folded).strip()
    padded = f" {folded} "
    return raw, padded


def _count_keyword_matches(text: str, keywords: set[str]) -> int:
    count = 0
    for kw in keywords:
        clean_kw = _strip_diacritics(transliterate(kw)).casefold().strip()
        if not clean_kw:
            continue
        if " " in clean_kw:
            if clean_kw in text:
                count += 1
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(clean_kw)}(?![a-z0-9])", text):
            count += 1
    return count


def _count_regex_matches(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE))


def classify_news_quality_locally(title: str, description: str) -> dict:
    """
    Heuristic quality classifier for Serbian and Macedonian ingestion filtering.

    The goal is not to rank every article perfectly; it is to confidently reject
    junk while preserving ordinary hard news in both Cyrillic and Latin scripts.
    """
    raw_text, text = _normalize_quality_text(title, description)

    hard_keywords = {
        # Institutions, politics, law
        "sobranie",
        "parlament",
        "skupstina",
        "skupština",
        "vlada",
        "vladata",
        "minister",
        "ministerstvo",
        "ministerstvoto",
        "ministar",
        "ministarstvo",
        "premier",
        "premijer",
        "pretsedatel",
        "predsednik",
        "opstina",
        "opština",
        "zakon",
        "ustav",
        "referendum",
        "izbori",
        "sud",
        "pravosudje",
        "pravosuđe",
        "obvinitelstvo",
        "tuzilastvo",
        "tužilaštvo",
        "istraga",
        "policija",
        "kriminal",
        "diplomacija",
        "pregovori",
        # Economy, public services, infrastructure
        "budzet",
        "budžet",
        "budzhet",
        "ekonomija",
        "inflacija",
        "berza",
        "trziste",
        "tržište",
        "ceni",
        "cene",
        "plati",
        "plate",
        "penzii",
        "penzije",
        "infrastruktura",
        "izgradba",
        "izgradnja",
        "energetika",
        "zdravstvo",
        "obrazovanie",
        "obrazovanje",
        # International/public-interest actors
        "brisel",
        "vasington",
        "washington",
        "eu",
        "nato",
        "on",
        "sad",
        "un",
    }

    soft_keywords = {
        "horoskop",
        "horoskopot",
        "zvezdite",
        "zvezde",
        "astro",
        "predviduvanja",
        "predvidjanja",
        "predviđanja",
        "fustan",
        "haljina",
        "moda",
        "izgled",
        "razvod",
        "recept",
        "sostojki",
        "kujna",
        "vkusna",
        "dieta",
        "dijeta",
        "estrada",
        "rijaliti",
        "tiktoker",
        "influenser",
        "influencer",
        "foto galerija",
        "galerija",
        "kursna lista",
        "loto rezultati",
    }

    clickbait_patterns = (
        r"\b(necete|ne cete|nećete)\s+verovati\b",
        r"\bnema\s+da\s+veruvate\b",
        r"\beve\s+(sto|što)\b",
        r"\bevo\s+(sta|šta)\b",
        r"\b(shokantno|sokantno|šokantno|skandalozno|senzacionalno)\b",
        r"\b(viralno|hit|gledajte|pogledajte)\b",
        r"\b(foto|video)\s*[:\-]",
        r"\b(zena|žena)\s+otkriva\b",
    )

    public_interest_patterns = (
        r"\b\d+(?:[,.]\d+)?\s*(milion|miliona|milioni|milijard|milijarda|milijardi|evra|eur|denari|dinara|procent|%)\b",
        r"\b\d{1,2}\.\s*\d{1,2}\.\s*\d{2,4}\b",
        r"\b(odluka|sednica|sjednica|rasprava|usvoji|usvojila|donese|donela|najavi|najavila)\b",
        r"\b(gradjani|građani|gragjani|domacinstva|domaćinstva|ucenici|učenici|pacienti|pacijenti)\b",
    )

    hard_matches = _count_keyword_matches(text, hard_keywords)
    soft_matches = _count_keyword_matches(text, soft_keywords)
    clickbait_matches = _count_regex_matches(text, clickbait_patterns)
    public_interest_matches = _count_regex_matches(text, public_interest_patterns)

    literacy_penalty = 0.0
    if "!!!" in raw_text or "???" in raw_text:
        literacy_penalty += 0.18
    if re.search(r"[!?]{4,}", raw_text):
        literacy_penalty += 0.1
    if clickbait_matches:
        literacy_penalty += min(0.35, 0.12 * clickbait_matches)

    potential_entities = _extract_capitalized_phrases(raw_text)
    unique_entities = {
        entity.casefold()
        for entity in potential_entities
        if entity.casefold() not in ENTITY_NOISE_WORDS and len(entity.strip()) >= 3
    }
    entity_count = len(unique_entities)

    base_score = 0.48
    base_score += min(0.3, hard_matches * 0.09)
    base_score += min(0.16, public_interest_matches * 0.06)
    if entity_count >= 2:
        base_score += min(0.14, entity_count * 0.035)

    base_score -= min(0.45, soft_matches * 0.18)
    base_score -= literacy_penalty

    # Rescue civic/public-interest stories from cosmetic penalties such as PHOTO
    # labels, but do not rescue horoscope/recipe/viral junk with no institutions.
    if hard_matches >= 2 and public_interest_matches >= 1:
        base_score = max(base_score, 0.62)
    if hard_matches == 0 and soft_matches >= 2:
        base_score = min(base_score, 0.28)
    if hard_matches == 0 and clickbait_matches >= 2:
        base_score = min(base_score, 0.25)

    score = max(0.0, min(1.0, base_score))

    reason = "Standard"
    if score < 0.3:
        reason = "Low Quality / Junk"
    elif soft_matches > hard_matches and soft_matches > 0:
        reason = "Soft Content"
    elif hard_matches >= 2 and public_interest_matches >= 1:
        reason = "High Value Policy/Event"
    elif hard_matches >= 2:
        reason = "Hard News"
    elif entity_count >= 4:
        reason = "Entity Rich"

    return {
        "score": round(score, 2),
        "is_hard_news": score >= 0.55,
        "reason": reason,
        "entity_count": entity_count,
        "hard_matches": hard_matches,
        "soft_matches": soft_matches,
        "clickbait_matches": clickbait_matches,
        "public_interest_matches": public_interest_matches,
        "penalties": round(literacy_penalty, 2),
    }
