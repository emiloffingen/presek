"""
trending.py — Real trending keywords for Пресек
Extracts hot topics from recent articles by counting significant words,
weighted by recency and source credibility signals.
"""

import sqlite3
import re
from collections import Counter
from datetime import datetime, timedelta

# ── Macedonian stopwords ──────────────────────────────────────────
# Common words that carry no topic signal
STOPWORDS = {
    "во", "на", "од", "со", "за", "до", "по", "при", "над", "под",
    "пред", "зад", "меѓу", "низ", "без", "освен", "покрај", "спроти",
    "и", "или", "но", "а", "па", "ама", "туку", "ни", "ниту",
    "се", "си", "е", "ќе", "би", "да", "не", "ли", "нè", "им",
    "го", "ги", "му", "и", "ја", "ме", "те", "не", "ве", "ни",
    "тој", "таа", "тоа", "тие", "тие", "овој", "оваа", "ова",
    "кој", "која", "кое", "кои", "што", "каде", "кога", "зошто",
    "how", "the", "a", "an", "in", "of", "to", "and", "is", "was",
    "дека", "оти", "how", "со", "еден", "една", "едно", "еден",
    "исто", "така", "уште", "веќе", "само", "многу", "малку",
    "нов", "нова", "ново", "нови", "овие", "оние", "некои",
    "МКД", "mkd", "www", "http", "com", "mk",
    # Macedonian verb forms that are meaningless alone
    "има", "имаат", "нема", "немаат", "бил", "биле", "bila",
    "рече", "рекол", "рекла", "изјави", "изјавил",
    "според", "исто", "друго", "други", "секој", "секоја",
    "меѓу", "помеѓу", "против", "поради", "преку",
}

# Minimum word length and frequency to be considered trending
MIN_WORD_LEN  = 4
MIN_COUNT     = 2
MAX_RESULTS   = 15
LOOKBACK_HOURS = 24


def extract_words(text: str) -> list[str]:
    """Extract meaningful words from a title."""
    # Keep Cyrillic, Latin letters and digits, split on everything else
    words = re.findall(r'[а-шА-Ш\w]{' + str(MIN_WORD_LEN) + r',}', text, re.UNICODE)
    return [w.lower() for w in words if w.lower() not in STOPWORDS and not w.isdigit()]


def get_trending(db_path: str, hours: int = LOOKBACK_HOURS, limit: int = MAX_RESULTS) -> list[dict]:
    """
    Count word frequency in recent article titles.
    Weight by: raw count × recency bonus (last 6h = 2×, last 12h = 1.5×, else 1×).
    Returns list of {word, count} dicts sorted by weighted score.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT title, created_at FROM articles WHERE created_at >= ? ORDER BY created_at DESC LIMIT 2000",
            (cutoff,)
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"[trending] DB error: {e}")
        return []

    if not rows:
        return []

    now = datetime.now()
    weighted: Counter = Counter()
    raw: Counter      = Counter()

    for row in rows:
        words = extract_words(row["title"] or "")
        try:
            age_h = (now - datetime.fromisoformat(row["created_at"].replace("+00:00", ""))).total_seconds() / 3600
        except Exception:
            age_h = 12

        # Recency weight
        if   age_h <  6: weight = 2.0
        elif age_h < 12: weight = 1.5
        else:            weight = 1.0

        for w in words:
            weighted[w] += weight
            raw[w]       += 1

    # Filter: must appear at least MIN_COUNT times in raw count
    results = [
        {"word": word, "count": raw[word]}
        for word, score in weighted.most_common(limit * 3)
        if raw[word] >= MIN_COUNT
    ]

    return results[:limit]


def register_trending_route(app, db_path: str):
    """Register /api/trending onto a Flask app."""
    from flask import jsonify

    @app.route("/api/trending")
    def trending():
        results = get_trending(db_path)
        return jsonify(results)
