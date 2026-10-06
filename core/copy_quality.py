"""Language copy purity gates for published synthesis (SR Latin / MK Cyrillic)."""

from __future__ import annotations

import os
import re

_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_WORD_RE = re.compile(r"[A-Za-z\u0400-\u04FF]{2,}")
# Cyrillic letters that do not exist in the Macedonian alphabet
# (Bulgarian/Russian/Ukrainian/Serbian drift). Any word containing one of
# these fails the MK publish gate so the synthesis is retried, not published.
_MK_FOREIGN_LETTERS_RE = re.compile(r"[йяюыэёђћіїєґъ]")
_MK_FOREIGN_WORD_RE = re.compile(r"[A-Za-z\u0400-\u04FF]*[йяюыэёђћіїєґъ][A-Za-z\u0400-\u04FF]*")
_EXEMPT_TOKEN = re.compile(
    r"^(?:\[\d+\]|[A-Z]{2,6}|\d+(?:[.,]\d+)?%?|vs\.?|FIFA|UEFA|NBA|NFL|GDP|IMF|EU|UN|USA|UK|NATO|EXPO)$",
    re.IGNORECASE,
)

_SERBIAN_LATIN_LEAKS = frozenset(
    {
        "vo",
        "mez",
        "pomedju",
        "izmedju",
        "rezultat",
        "rezultatot",
        "poluvreme",
        "poluvremeto",
        "gol",
        "golovi",
        "fudbal",
        "utakmica",
        "izmedu",
        "beše",
        "bese",
        "odigrasha",
        "odigrano",
        "izramni",
        "izramnija",
        "intenziven",
        "dogadjaj",
        "vesti",
        "izvor",
        "izvori",
        "mediji",
        "redakcija",
        "premijer",
        "predsednik",
        "ministar",
        "izvještaj",
        "izvestaj",
        "tokom",
        "takođe",
        "takodje",
        "zbog",
        "između",
        "izmedju",
    }
)

# Cyrillic words that often leak into Serbian Latin copy.
_SERBIAN_CYRILLIC_LEAKS = frozenset(
    {
        "влада",
        "избори",
        "министар",
        "председник",
        "премијер",
        "србија",
        "извештај",
        "полиција",
        "тужилаштво",
        "догађај",
        "резултат",
        "утакмица",
        "фудбал",
        "македонија",
        "вести",
        "извор",
    }
)


def _count_letters(text: str, *, exempt_latin: bool = True) -> tuple[int, int]:
    cyrillic = len(_CYRILLIC_RE.findall(text or ""))
    latin = 0
    for match in _LATIN_RE.finditer(text or ""):
        if exempt_latin:
            start = max(0, match.start() - 12)
            end = min(len(text), match.end() + 12)
            token = re.sub(r"[^\w]", "", text[start:end])
            if _EXEMPT_TOKEN.match(token):
                continue
        latin += 1
    return cyrillic, latin


def assess_mk_copy_purity(text: str) -> dict:
    clean = str(text or "").strip()
    if not clean:
        return {
            "ok": False,
            "score": 0.0,
            "lang": "mk",
            "reason": "empty",
            "latin_share": 1.0,
            "cyrillic_letters": 0,
            "latin_letters": 0,
            "leaks": [],
        }

    cyrillic, latin = _count_letters(clean)
    total = cyrillic + latin
    latin_share = (latin / total) if total else 1.0
    leaks = sorted({word.casefold() for word in _WORD_RE.findall(clean) if word.casefold() in _SERBIAN_LATIN_LEAKS})
    foreign_words = sorted({_m.group(0) for _m in _MK_FOREIGN_WORD_RE.finditer(clean)})

    min_cyrillic = int(os.environ.get("MK_COPY_MIN_CYRILLIC_LETTERS", "24"))
    max_latin_share = float(os.environ.get("MK_COPY_MAX_LATIN_SHARE", "0.28"))
    max_leaks = int(os.environ.get("MK_COPY_MAX_SERBIAN_LEAKS", "0"))

    ok = cyrillic >= min_cyrillic and latin_share <= max_latin_share and len(leaks) <= max_leaks and not foreign_words
    reason = "ok"
    if cyrillic < min_cyrillic:
        reason = "low_cyrillic"
    elif latin_share > max_latin_share:
        reason = "high_latin_share"
    elif leaks:
        reason = "serbian_latin_leaks"
    elif foreign_words:
        reason = "non_mk_letters"

    score = max(
        0.0,
        min(
            1.0,
            (cyrillic / max(1, min_cyrillic)) * 0.45
            + (1.0 - min(1.0, latin_share / max(0.01, max_latin_share))) * 0.4
            + (0.15 if not leaks else max(0.0, 0.15 - len(leaks) * 0.08)),
        ),
    )
    return {
        "ok": ok,
        "score": round(score, 3),
        "lang": "mk",
        "reason": reason,
        "cyrillic_letters": cyrillic,
        "latin_letters": latin,
        "latin_share": round(latin_share, 3),
        "leaks": leaks[:8],
        "foreign_words": foreign_words[:8],
    }


def assess_sr_copy_purity(text: str) -> dict:
    clean = str(text or "").strip()
    if not clean:
        return {
            "ok": False,
            "score": 0.0,
            "lang": "sr",
            "reason": "empty",
            "cyrillic_share": 1.0,
            "cyrillic_letters": 0,
            "latin_letters": 0,
            "leaks": [],
        }

    cyrillic, latin = _count_letters(clean, exempt_latin=True)
    total = cyrillic + latin
    cyrillic_share = (cyrillic / total) if total else 0.0
    leaks = sorted({word.casefold() for word in _WORD_RE.findall(clean) if word.casefold() in _SERBIAN_CYRILLIC_LEAKS})

    min_latin = int(os.environ.get("SR_COPY_MIN_LATIN_LETTERS", "24"))
    max_cyrillic_share = float(os.environ.get("SR_COPY_MAX_CYRILLIC_SHARE", "0.22"))
    max_leaks = int(os.environ.get("SR_COPY_MAX_CYRILLIC_LEAKS", "1"))

    ok = latin >= min_latin and cyrillic_share <= max_cyrillic_share and len(leaks) <= max_leaks
    reason = "ok"
    if latin < min_latin:
        reason = "low_latin"
    elif cyrillic_share > max_cyrillic_share:
        reason = "high_cyrillic_share"
    elif leaks:
        reason = "cyrillic_leaks"

    score = max(
        0.0,
        min(
            1.0,
            (latin / max(1, min_latin)) * 0.45
            + (1.0 - min(1.0, cyrillic_share / max(0.01, max_cyrillic_share))) * 0.4
            + (0.15 if not leaks else max(0.0, 0.15 - len(leaks) * 0.08)),
        ),
    )
    return {
        "ok": ok,
        "score": round(score, 3),
        "lang": "sr",
        "reason": reason,
        "cyrillic_letters": cyrillic,
        "latin_letters": latin,
        "cyrillic_share": round(cyrillic_share, 3),
        "leaks": leaks[:8],
    }


def assess_copy_purity(text: str, lang: str = "sr") -> dict:
    if str(lang or "").strip().lower().startswith("mk"):
        return assess_mk_copy_purity(text)
    return assess_sr_copy_purity(text)


def copy_bundle_passes_publish_gate(
    *,
    lang: str,
    headline: str = "",
    summary: str = "",
    article: str = "",
    key_facts: list | None = None,
) -> tuple[bool, dict]:
    parts: list[str] = [headline, summary, article]
    if isinstance(key_facts, list):
        parts.extend(str(item) for item in key_facts if item)
    combined = "\n".join(part.strip() for part in parts if str(part or "").strip())
    diagnostics = assess_copy_purity(combined, lang=lang)
    return bool(diagnostics.get("ok")), diagnostics


# Backwards-compatible aliases
def mk_copy_passes_publish_gate(text):
    return assess_mk_copy_purity(text).get("ok", False)


def mk_bundle_passes_publish_gate(
    *,
    headline: str = "",
    summary: str = "",
    article: str = "",
    key_facts: list | None = None,
) -> tuple[bool, dict]:
    return copy_bundle_passes_publish_gate(
        lang="mk",
        headline=headline,
        summary=summary,
        article=article,
        key_facts=key_facts,
    )
