"""
trending.py — Real trending keywords for Presek
Extracts hot topics from recent articles by counting significant words,
weighted by recency and a proper-noun bonus (capitalized mid-sentence words).
"""

import database
import logging
import re
from collections import Counter
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ── Macedonian + Serbian + Albanian stopwords ──────────────────────────────
STOPWORDS = {
    # Prepositions
    "во",
    "на",
    "од",
    "со",
    "за",
    "до",
    "по",
    "при",
    "над",
    "под",
    "пред",
    "зад",
    "меѓу",
    "низ",
    "без",
    "освен",
    "покрај",
    "спроти",
    "помеѓу",
    "против",
    "поради",
    "преку",
    "наспроти",
    "наместо",
    # Conjunctions
    "и",
    "или",
    "но",
    "а",
    "па",
    "ама",
    "туку",
    "ни",
    "ниту",
    "дека",
    "оти",
    "иако",
    "ако",
    "кога",
    "додека",
    "штом",
    "бидејќи",
    "затоа",
    # Pronouns
    "тој",
    "таа",
    "тоа",
    "тие",
    "овој",
    "оваа",
    "ова",
    "овие",
    "оние",
    "кој",
    "која",
    "кое",
    "кои",
    "некој",
    "некоја",
    "некое",
    "некои",
    "секој",
    "секоја",
    "секое",
    "секои",
    "никој",
    "никоја",
    "јас",
    "ти",
    "ние",
    "вие",
    "тие",
    "сите",
    # Particles / auxiliaries
    "се",
    "си",
    "е",
    "ќе",
    "би",
    "да",
    "не",
    "ли",
    "нè",
    "им",
    "го",
    "ги",
    "му",
    "ја",
    "ме",
    "те",
    "ве",
    "ни",
    "нè",
    "сум",
    "сте",
    "биле",
    "бил",
    "беше",
    "бевме",
    "биде",
    # Common adverbs / adjectives with no topic value
    "така",
    "исто",
    "уште",
    "веќе",
    "само",
    "многу",
    "малку",
    "повеќе",
    "помалку",
    "особено",
    "многупати",
    "пак",
    "повторно",
    "прво",
    "второ",
    "трето",
    "прв",
    "прва",
    "прво",
    "последен",
    "нов",
    "нова",
    "ново",
    "нови",
    "стар",
    "стара",
    "старо",
    "голем",
    "голема",
    "големо",
    "мал",
    "мала",
    "мало",
    "добар",
    "добра",
    "добро",
    "лош",
    "лоша",
    "лошо",
    # Question words
    "каде",
    "кога",
    "зошто",
    "зарем",
    "дали",
    "колку",
    # Common verbs / verb-like words that carry no entity signal
    "има",
    "имаат",
    "имало",
    "нема",
    "немаат",
    "немало",
    "рече",
    "рекол",
    "рекла",
    "изјави",
    "изјавил",
    "изјавила",
    "вели",
    "велат",
    "истакна",
    "истакнал",
    "потврдни",
    "потврдил",
    "соопшти",
    "соопштил",
    "посочи",
    "посочил",
    "додаде",
    "додал",
    "нагласи",
    "нагласил",
    "objasni",
    "објасни",
    "смета",
    "сметаат",
    "треба",
    "трeba",
    "може",
    "можат",
    "мора",
    "мораат",
    "почна",
    "почнал",
    "заврдшил",
    "завршила",
    "продолжи",
    # Common question / demonstrative combos
    "дури",
    "сепак",
    "меѓутоа",
    "сосема",
    "навистина",
    "очигледно",
    "можеби",
    "веројатно",
    "всушност",
    "главно",
    "претежно",
    "според",
    "врз",
    "откако",
    "откога",
    "додека",
    # Misc noise
    "kako",
    "како",
    "how",
    "the",
    "a",
    "an",
    "in",
    "of",
    "to",
    "and",
    "is",
    "was",
    "are",
    "for",
    "that",
    "this",
    "with",
    "from",
    "has",
    "have",
    "МКД",
    "mkd",
    "www",
    "http",
    "https",
    "com",
    "mk",
    "org",
    "net",
    "video",
    "видео",
    "еден",
    "напад",
    "фото",
    "foto",
    "галерија",
    "galerija",
    "интервју",
    "intervju",
    "денес",
    "denas",
    "утре",
    "utre",
    "вчера",
    "vchera",
    "mia",
    "миа",
    "макфакс",
    "makfax",
    "сител",
    "телма",
    "канал5",
    "алфа",
    # Serbian / Bosnian overlap
    "nije",
    "koji",
    "koja",
    "koje",
    "što",
    "jer",
    "ali",
    "ili",
    "kao",
    "više",
    "koja",
    "kada",
    "gdje",
    "kako",
    "samo",
    # Albanian common words
    "dhe",
    "në",
    "për",
    "me",
    "nga",
    "si",
    "por",
    "që",
    "është",
    "ka",
    "të",
    "një",
    "се",
    "po",
    "kur",
    "ose",
}

# Minimum word length and frequency to be considered trending
MIN_WORD_LEN = 4
MIN_COUNT = 2
MAX_RESULTS = 12
LOOKBACK_HOURS = 8

# Bonus multiplier for likely proper nouns (capitalized mid-sentence)
PROPER_NOUN_BONUS = 4.0


def extract_words_with_flags(title: str) -> list[tuple[str, bool]]:
    """
    Returns list of (word_lowercase, is_proper_noun) tuples.
    A word is treated as a proper noun if it is capitalised and
    does NOT appear at the start of a sentence.
    """
    # Split into sentences on . ! ? so we can identify sentence-start positions
    sentences = re.split(r"[.!?]+", title)
    results: list[tuple[str, bool]] = []

    for sentence in sentences:
        # Tokenise: keep Cyrillic + Latin runs, strip surrounding punctuation
        tokens = re.findall(r"[а-шА-Ш\w''-]+", sentence, re.UNICODE)
        for idx, raw in enumerate(tokens):
            # Strip leading/trailing punctuation characters
            word = raw.strip("\"'\u201e\u201c\u201f\u00ab\u00bb,;:!?()-\u2013\u2014")
            if not word:
                continue
            is_capitalized = word[0].isupper()
            word_lower = word.lower()
            # Skip short words, stopwords, pure numbers
            if len(word_lower) < MIN_WORD_LEN:
                continue
            if word_lower in STOPWORDS:
                continue
            if word_lower.isdigit():
                continue
            # Proper noun: capitalised and NOT the first token in the sentence
            is_proper = is_capitalized and idx > 0
            results.append((word_lower, is_proper))

    return results


def get_trending(hours: int = 12, limit: int = MAX_RESULTS) -> list[dict]:
    """
    Count word frequency in recent article titles with momentum and velocity calculation.
    """
    try:
        with database.get_db() as conn:
            cutoff = datetime.now() - timedelta(hours=hours)
            # Fetch cluster_id and category to detect cross-category jumps
            rows = conn.execute(
                "SELECT title, created_at, cluster_id, category FROM articles WHERE created_at >= %s ORDER BY created_at DESC LIMIT 3000",
                (cutoff,),
            ).fetchall()
    except Exception as e:
        log.error(f"DB error: {e}")
        return []

    if not rows:
        return []

    now = datetime.now()
    # Velocity windows:
    # 1. Hot (0-1h): Current activity spike
    # 2. Rising (1-4h): Sustained growth
    # 3. Established (4-12h): Baseline
    hot_weighted: Counter = Counter()
    rising_weighted: Counter = Counter()
    baseline_weighted: Counter = Counter()
    raw: Counter = Counter()

    # Track cross-category diversity per word
    word_categories = {}  # word -> set of categories

    # Track which words appear in potentially breaking clusters
    breaking_words = set()
    cluster_source_counts = Counter()
    for row in rows:
        cluster_source_counts[row["cluster_id"]] += 1

    for row in rows:
        pairs = extract_words_with_flags(row["title"] or "")
        try:
            if isinstance(row["created_at"], datetime):
                age_h = (
                    now - row["created_at"].replace(tzinfo=None)
                ).total_seconds() / 3600
            else:
                age_h = (
                    now
                    - datetime.fromisoformat(row["created_at"].replace("+00:00", ""))
                ).total_seconds() / 3600
        except Exception as e:
            log.debug(f"Failed to calculate age: {e}")
            age_h = 12

        # Momentum Windows
        is_hot = age_h <= 1.5
        is_rising = 1.5 < age_h <= 4.5

        is_high_volume_cluster = cluster_source_counts[row["cluster_id"]] >= 4
        cat = row.get("category", "Вести")

        for word, is_proper in pairs:
            # Basic normalization for common entities
            normalization = {
                "iran": "иран",
                "iranski": "иран",
                "trump": "трамп",
                "trampa": "трамп",
                "putin": "путин",
                "putina": "путин",
                "biden": "бајден",
                "bajden": "бајден",
                "zelensky": "зеленски",
                "zelenski": "зеленски",
                "nato": "нато",
                "eu": "еу",
                "sad": "сад",
                "video": "видео",
                "vinea": "видео",
                "foto": "фото",
                "ukraine": "украина",
                "ukraina": "украина",
                "russia": "русија",
                "rusija": "русија",
                "skopje": "скопје",
                "macedonia": "srbija",
                "ormuz": "ормуз",
                "ormuski": "ормуз",
                "ormutski": "ормуз",
                "ормускиот": "ормуз",
                "ормутскиот": "ормуз",
                "теснеце": "теснец",
            }
            word = normalization.get(word, word)

            noun_bonus = PROPER_NOUN_BONUS if is_proper else 1.0

            if is_hot:
                hot_weighted[word] += 3.0 * noun_bonus
            elif is_rising:
                rising_weighted[word] += 2.0 * noun_bonus
            else:
                baseline_weighted[word] += 1.0 * noun_bonus

            raw[word] += 1
            word_categories.setdefault(word, set()).add(cat)

            if is_hot and is_high_volume_cluster:
                breaking_words.add(word)

    # Calculate final scores and trends
    scored_items = []
    all_words = (
        set(hot_weighted.keys())
        | set(rising_weighted.keys())
        | set(baseline_weighted.keys())
    )

    for word in all_words:
        if raw[word] < MIN_COUNT:
            continue

        h = hot_weighted[word]
        r = rising_weighted[word]
        b = baseline_weighted[word]

        # Velocity logic:
        # High velocity if activity in last 1.5h is significantly higher than previous windows
        velocity_score = (h * 2.0) + (r * 1.2) + (b * 0.5)

        # Category diversity boost
        # If a story is jumping across 3+ categories (e.g. Politics -> Economy -> World)
        cats = word_categories.get(word, set())
        cat_boost = 1.0 + (len(cats) * 0.15) if len(cats) >= 2 else 1.0

        final_score = velocity_score * cat_boost

        # Trend indicator
        if h > (r + b) * 0.8 and h > 6:
            trend = "↑↑"  # Breaking velocity
        elif h + r > b * 1.5:
            trend = "↑"
        elif b > (h + r) * 2:
            trend = "↓"
        else:
            trend = "→"

        scored_items.append(
            {
                "word": word.capitalize(),
                "count": raw[word],
                "score": final_score,
                "trend": trend,
                "is_breaking": word in breaking_words or (h > 15 and len(cats) >= 2),
                "categories": list(cats)[:3],
            }
        )

    # Sort by velocity-weighted score
    scored_items.sort(key=lambda x: x["score"], reverse=True)
    return scored_items[:limit]
