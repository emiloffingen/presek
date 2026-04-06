"""
trending.py — Real trending keywords for Пресек
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
    "во", "на", "од", "со", "за", "до", "по", "при", "над", "под",
    "пред", "зад", "меѓу", "низ", "без", "освен", "покрај", "спроти",
    "помеѓу", "против", "поради", "преку", "наспроти", "наместо",
    # Conjunctions
    "и", "или", "но", "а", "па", "ама", "туку", "ни", "ниту", "дека",
    "оти", "иако", "ако", "кога", "додека", "штом", "бидејќи", "затоа",
    # Pronouns
    "тој", "таа", "тоа", "тие", "овој", "оваа", "ова", "овие", "оние",
    "кој", "која", "кое", "кои", "некој", "некоја", "некое", "некои",
    "секој", "секоја", "секое", "секои", "никој", "никоја",
    "јас", "ти", "ние", "вие", "тие", "сите",
    # Particles / auxiliaries
    "се", "си", "е", "ќе", "би", "да", "не", "ли", "нè", "им",
    "го", "ги", "му", "ја", "ме", "те", "ве", "ни", "нè",
    "сум", "сте", "биле", "бил", "беше", "бевме", "биде",
    # Common adverbs / adjectives with no topic value
    "така", "исто", "уште", "веќе", "само", "многу", "малку", "повеќе",
    "помалку", "особено", "многупати", "пак", "повторно", "прво",
    "второ", "трето", "прв", "прва", "прво", "последен",
    "нов", "нова", "ново", "нови", "стар", "стара", "старо",
    "голем", "голема", "големо", "мал", "мала", "мало",
    "добар", "добра", "добро", "лош", "лоша", "лошо",
    # Question words
    "каде", "кога", "зошто", "зарем", "дали", "колку",
    # Common verbs / verb-like words that carry no entity signal
    "има", "имаат", "имало", "нема", "немаат", "немало",
    "рече", "рекол", "рекла", "изјави", "изјавил", "изјавила",
    "вели", "велат", "истакна", "истакнал", "потврдни", "потврдил",
    "соопшти", "соопштил", "посочи", "посочил", "додаде", "додал",
    "нагласи", "нагласил", "objasni", "објасни", "смета", "сметаат",
    "треба", "трeba", "може", "можат", "мора", "мораат",
    "почна", "почнал", "заврдшил", "завршила", "продолжи",
    # Common question / demonstrative combos
    "дури", "сепак", "меѓутоа", "сосема", "навистина", "очигледно",
    "можеби", "веројатно", "всушност", "главно", "претежно",
    "според", "врз", "откако", "откога", "додека",
    # Misc noise
    "kako", "како", "how", "the", "a", "an", "in", "of", "to", "and", "is",
    "was", "are", "for", "that", "this", "with", "from", "has", "have",
    "МКД", "mkd", "www", "http", "https", "com", "mk", "org", "net",
    "video", "видео", "еден", "напад", "фото", "foto", "галерија", "galerija",
    "интервју", "intervju", "денес", "denas", "утре", "utre", "вчера", "vchera",
    # Serbian / Bosnian overlap
    "nije", "koji", "koja", "koje", "što", "jer", "ali", "ili", "kao",
    "više", "koja", "kada", "gdje", "kako", "samo",
    # Albanian common words
    "dhe", "në", "për", "me", "nga", "si", "por", "që", "është",
    "ka", "të", "një", "се", "po", "kur", "ose",
}

# Minimum word length and frequency to be considered trending
MIN_WORD_LEN   = 4
MIN_COUNT      = 2
MAX_RESULTS    = 12
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
    sentences = re.split(r'[.!?]+', title)
    results: list[tuple[str, bool]] = []

    for sentence in sentences:
        # Tokenise: keep Cyrillic + Latin runs, strip surrounding punctuation
        tokens = re.findall(r"[а-шА-Ш\w''-]+", sentence, re.UNICODE)
        for idx, raw in enumerate(tokens):
            # Strip leading/trailing punctuation characters
            word = raw.strip('\"\'\u201e\u201c\u201f\u00ab\u00bb,;:!?()-\u2013\u2014')
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


def get_trending(hours: int = LOOKBACK_HOURS, limit: int = MAX_RESULTS) -> list[dict]:
    """
    Count word frequency in recent article titles.
    Weights: recency (last 6h = 2×, last 12h = 1.5×, else 1×)
             × proper-noun bonus (4× if capitalised mid-sentence).
    Returns list of {word, count} dicts sorted by weighted score.
    """
    try:
        conn = database.get_db()
        cutoff = datetime.now() - timedelta(hours=hours)
        rows = conn.execute(
            "SELECT title, created_at FROM articles WHERE created_at >= %s ORDER BY created_at DESC LIMIT 2000",
            (cutoff,)
        ).fetchall()
        conn.close()
    except Exception as e:
        log.error(f"DB error: {e}")
        return []

    if not rows:
        return []

    now = datetime.now()
    weighted: Counter = Counter()
    raw: Counter      = Counter()

    for row in rows:
        pairs = extract_words_with_flags(row["title"] or "")
        try:
            # PostgreSQL returns datetime objects for TIMESTAMP
            if isinstance(row["created_at"], datetime):
                age_h = (now - row["created_at"].replace(tzinfo=None)).total_seconds() / 3600
            else:
                age_h = (now - datetime.fromisoformat(row["created_at"].replace("+00:00", ""))).total_seconds() / 3600
        except Exception:
            age_h = 12

        # Recency weight
        if   age_h <  6: recency = 2.0
        elif age_h < 12: recency = 1.5
        else:            recency = 1.0

        for word, is_proper in pairs:
            # Simple normalization for very common dual-script or variations
            normalization = {
                'iran': 'иран', 'iranski': 'иран',
                'trump': 'трамп', 'trampa': 'трамп',
                'putin': 'путин', 'putina': 'путин',
                'biden': 'бајден', 'bajden': 'бајден',
                'zelensky': 'зеленски', 'zelenski': 'зеленски',
                'nato': 'нато', 'eu': 'еу', 'sad': 'сад',
                'video': 'видео', 'vinea': 'видео', 'foto': 'фото',
                'ukraine': 'украина', 'ukraina': 'украина',
                'russia': 'русија', 'rusija': 'русија',
                'skopje': 'скопје', 'macedonia': 'македонија'
            }
            word = normalization.get(word, word)
            
            noun_bonus = PROPER_NOUN_BONUS if is_proper else 1.0
            weighted[word] += recency * noun_bonus
            raw[word]       += 1

    # Filter: must appear at least MIN_COUNT times in raw count
    results = [
        {"word": word.capitalize(), "count": raw[word]}
        for word, score in weighted.most_common(limit * 3)
        if raw[word] >= MIN_COUNT
    ]

    return results[:limit]


def register_trending_route(app):
    """Register /api/trending onto a Flask app."""
    from flask import jsonify
    import time as _time
    _trending_cache: list = [0.0, None]  # [timestamp, data]

    @app.route("/api/trending")
    def trending():
        now = _time.time()
        if _trending_cache[1] is not None and now - _trending_cache[0] < 120:
            return jsonify(_trending_cache[1])
        results = get_trending()
        _trending_cache[0] = now
        _trending_cache[1] = results
        return jsonify(results)
