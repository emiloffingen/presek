"""Shared curation heuristics (single owner).

Section assignment (live_now / wire / developing, hard-news boosts) must agree
between the /home assembly (routes/home.py) and the /news payloads
(routes/news.py). These constants previously lived in both modules and had
already drifted (home.py reassigned _HARD_NEWS_CATEGORIES, dropping
Srbija/Makedonija/Balkan). Import from here instead of redefining.
"""

import re

from .common import cleanAndDecode

_SOFT_EXCLUDE_TOPICS = {"Zivot", "Zabava", "Zdravje"}
_HARD_NEWS_TOPICS = {"Politika", "Ekonomija", "Kriminal", "Sport", "Tehnologija"}
_HARD_NEWS_CATEGORIES = {
    "Srbija",
    "Makedonija",
    "Balkan",
    "Evropa",
    "Germanija",
    "Amerika",
    "Svet",
}
_FEATURE_PATTERNS = [
    re.compile(r"izdanie na", re.IGNORECASE),
    re.compile(r"intervju so", re.IGNORECASE),
    re.compile(r"intervju\b", re.IGNORECASE),
    re.compile(r"proverete dali", re.IGNORECASE),
    re.compile(r"pred da ", re.IGNORECASE),
    re.compile(r"postojano ste umorni", re.IGNORECASE),
    re.compile(r"ovoj mineral", re.IGNORECASE),
    re.compile(r"horoskop", re.IGNORECASE),
    re.compile(r"recept", re.IGNORECASE),
    re.compile(r"foto\b", re.IGNORECASE),
    re.compile(r"video\b", re.IGNORECASE),
    re.compile(r"galerija", re.IGNORECASE),
]


def _title_looks_like_feature(title):
    clean = cleanAndDecode(title)
    if not clean:
        return True
    if len(clean) > 180:
        return True
    if "?" in clean:
        return True
    return any(pattern.search(clean) for pattern in _FEATURE_PATTERNS)
