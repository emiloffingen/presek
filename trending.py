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
    "vo",
    "na",
    "od",
    "so",
    "za",
    "do",
    "po",
    "pri",
    "nad",
    "pod",
    "pred",
    "zad",
    "medju",
    "niz",
    "bez",
    "osven",
    "pokraj",
    "sproti",
    "pomedju",
    "protiv",
    "poradi",
    "preku",
    "nasproti",
    "namesto",
    # Conjunctions
    "i",
    "ili",
    "no",
    "a",
    "pa",
    "ama",
    "tuku",
    "ni",
    "nitu",
    "deka",
    "oti",
    "iako",
    "ako",
    "koga",
    "dodeka",
    "stom",
    "bidejci",
    "zatoa",
    # Pronouns
    "toj",
    "taa",
    "toa",
    "tie",
    "ovoj",
    "ova",
    "ova",
    "ovie",
    "onie",
    "koj",
    "koja",
    "koe",
    "koi",
    "nekoj",
    "nekoja",
    "nekoe",
    "nekoi",
    "sekoj",
    "sekoja",
    "sekoe",
    "sekoi",
    "nikoj",
    "nikoja",
    "jas",
    "ti",
    "nie",
    "vie",
    "tie",
    "site",
    # Particles / auxiliaries
    "se",
    "si",
    "e",
    "ce",
    "bi",
    "da",
    "ne",
    "li",
    "nè",
    "im",
    "go",
    "gi",
    "mu",
    "ja",
    "me",
    "te",
    "ve",
    "ni",
    "nè",
    "sum",
    "ste",
    "bile",
    "bil",
    "bese",
    "bevme",
    "bide",
    # Common adverbs / adjectives with no topic value
    "taka",
    "isto",
    "jos",
    "vece",
    "samo",
    "mnogu",
    "malku",
    "povece",
    "pomalku",
    "osobeno",
    "mnogupati",
    "pak",
    "povtorno",
    "prvo",
    "vtoro",
    "treto",
    "prv",
    "prva",
    "prvo",
    "posleden",
    "nov",
    "nova",
    "novo",
    "novi",
    "star",
    "stara",
    "staro",
    "golem",
    "golema",
    "golemo",
    "mal",
    "mala",
    "malo",
    "dobar",
    "dobra",
    "dobro",
    "los",
    "losa",
    "loso",
    # Question words
    "kade",
    "koga",
    "zosto",
    "zarem",
    "dali",
    "kolku",
    # Common verbs / verb-like words that carry no entity signal
    "ima",
    "imaat",
    "imalo",
    "nema",
    "nemaat",
    "nemalo",
    "rece",
    "rekol",
    "rekla",
    "izjavi",
    "izjavil",
    "izjavila",
    "veli",
    "velat",
    "istakna",
    "istaknal",
    "potvrdni",
    "potvrdil",
    "soopsti",
    "soopstil",
    "posoci",
    "posocil",
    "dodade",
    "dodal",
    "naglasi",
    "naglasil",
    "objasni",
    "objasni",
    "smeta",
    "smetaat",
    "treba",
    "treba",
    "moze",
    "mozat",
    "mora",
    "moraat",
    "pocna",
    "pocnal",
    "zavrdsil",
    "zavrsila",
    "prodolzi",
    # Common question / demonstrative combos
    "duri",
    "sepak",
    "medjutoa",
    "sosema",
    "navistina",
    "ocigledno",
    "mozebi",
    "verojatno",
    "vsusnost",
    "glavno",
    "pretezno",
    "spored",
    "vrz",
    "otkako",
    "otkoga",
    "dodeka",
    # Misc noise
    "kako",
    "kako",
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
    "MKD",
    "mkd",
    "www",
    "http",
    "https",
    "com",
    "mk",
    "org",
    "net",
    "video",
    "video",
    "eden",
    "napad",
    "foto",
    "foto",
    "galerija",
    "galerija",
    "intervju",
    "intervju",
    "danas",
    "denas",
    "sutra",
    "utre",
    "juce",
    "vchera",
    "mia",
    "mia",
    "makfaks",
    "makfax",
    "sitel",
    "telma",
    "kanal5",
    "alfa",
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
    "se",
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
        tokens = re.findall(r"[a-sA-S\w''-]+", sentence, re.UNICODE)
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
        cat = row.get("category", "vesti")

        for word, is_proper in pairs:
            # Basic normalization for common entities
            normalization = {
                "iran": "iran",
                "iranski": "iran",
                "trump": "tramp",
                "trampa": "tramp",
                "putin": "putin",
                "putina": "putin",
                "biden": "bajden",
                "bajden": "bajden",
                "zelensky": "zelenski",
                "zelenski": "zelenski",
                "nato": "nato",
                "eu": "eu",
                "sad": "sad",
                "video": "video",
                "vinea": "video",
                "foto": "foto",
                "ukraine": "ukraina",
                "ukraina": "ukraina",
                "russia": "rusija",
                "rusija": "rusija",
                "skopje": "Beograd",
                "srbija": "srbija",
                "ormuz": "ormuz",
                "ormuski": "ormuz",
                "ormutski": "ormuz",
                "ormuskiot": "ormuz",
                "ormutskiot": "ormuz",
                "tesnece": "tesnec",
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
