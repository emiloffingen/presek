"""Quote of the day: find real, attributed direct quotes in article text.

Pure functions only (no database or network). The caller supplies rows of
quoted spans together with a little text on either side, and gets back the
one quote worth showing, or None. Nothing is ever made up or paraphrased:
a quote is shown only when the article names who said it.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

_UPPER = "А-ЯЀЃЅЈЉЊЌЏ"
_LOWER = "а-яѐѓѕјљњќџ"
_CAP = rf"[{_UPPER}][{_LOWER}]+"
_NAME = rf"{_CAP}(?:\s+{_CAP}){{0,2}}"

# Speech verbs, singular and plural, with common gendered forms.
_VERBS = (
    r"рече|рекоа|рекла|рекол|изјави|изјавија|изјавила|изјавил|порача|порачаа|порачала|истакна|истакнаа|истакнала|"
    r"додаде|додадоа|додала|соопшти|соопштија|соопштила|нагласи|нагласија|нагласила|посочи|посочија|посочила|"
    r"појасни|појаснија|објасни|објаснија|напиша|напишаа|оцени|оцениа|потенцира|констатира|предупреди|"
    r"предупредија|вели|велат|коментира|коментираше|реагира|одговори|одговорија|тврди|тврдат|потврди|"
    r"потврдија|заклучи|заклучија|најави|најавија|кажа|кажаа|изрази|апелира|повика"
)

# "…", рече Мицкоски / "…", им рече Трамп на новинарите / "…", рече премиерот Христијан Мицкоски
_AFTER = re.compile(
    rf"^\s*[,.]?\s*(?:(?:им|ѝ|му|ни|ми)\s+)?(?:{_VERBS})\s+"
    rf"(?:за\s+\S+\s+)?"
    rf"(?:(?!дека\b|да\b|како\b|што\b|се\b|не\b|и\b|за\b|на\b|во\b|по\b)[{_LOWER}]+\s+){{0,3}}"
    rf"({_NAME})"
)
# Мицкоски изјави: "…"
_BEFORE = re.compile(rf"({_NAME})\s+(?:{_VERBS})(?:\s+(?:за|на)\s+\S+)?\s*[:,]\s*$")

_NOT_SPEAKERS = {
    "Вчера",
    "Денес",
    "Утре",
    "Потоа",
    "Инаку",
    "Сепак",
    "Исто",
    "Притоа",
    "Според",
    "Меѓутоа",
    "Но",
    "Тој",
    "Таа",
    "Тие",
    "Како",
    "Кога",
    "Дека",
    "Затоа",
    "Пред",
    "Откако",
    "Додека",
    "Секако",
    "Пак",
    "Сè",
    "Сѐ",
}

_QUOTE_MARKS = '„“”"«»'

# A quote addressed to someone ("you owe court costs") is an exchange between two people, not a statement
# about the news. Second-person pronouns and plural "-ете/-ивте" verb forms mark it.
_ADDRESSED = re.compile(
    rf"(?<![{_LOWER}{_UPPER}])(?:ти|тебе|те|ви|вие|вас|вам|твој\w*|твоја|твоите|ваш\w*)(?![{_LOWER}{_UPPER}])"
    rf"|\w+(?:ивте|овте|авте|ете)(?![{_LOWER}{_UPPER}])",
    re.IGNORECASE,
)
MIN_CHARS = 45
MAX_CHARS = 250
MIN_WORDS = 8
MAX_WORDS = 40
MIN_OUTLETS = 2


def _clean_quote(text: str) -> str | None:
    """Return a displayable quote, or None if the span is not a full sentence."""
    q = re.sub(r"\s+", " ", text or "").strip()
    if not (MIN_CHARS <= len(q) <= MAX_CHARS):
        return None
    if any(ch in q for ch in _QUOTE_MARKS):
        return None  # nested or broken quotation marks
    if not re.match(rf"[{_UPPER}]", q):
        return None  # starts mid-sentence
    words = q.split()
    if not (MIN_WORDS <= len(words) <= MAX_WORDS):
        return None
    if _ADDRESSED.search(q):
        return None
    letters = re.findall(r"[A-Za-zА-ЯЀЃЅЈЉЊЌЏа-яѐѓѕјљњќџ]", q)
    cyrillic = re.findall(rf"[{_UPPER}{_LOWER}]", q)
    if not letters or len(cyrillic) / len(letters) < 0.85:
        return None
    return q.rstrip(" ,;:")


def find_speaker(before: str, after: str) -> str | None:
    """The person or body the article says made the quote."""
    m = _AFTER.match(after or "")
    if not m:
        m = _BEFORE.search(before or "")
    if not m:
        return None
    speaker = m.group(1).strip()
    first = speaker.split()[0]
    if first in _NOT_SPEAKERS:
        return None
    return speaker


def _key(quote: str) -> str:
    return re.sub(rf"[^{_LOWER}0-9]+", "", quote.lower())[:70]


def extract_quote(before: str, quote: str, after: str) -> dict[str, str] | None:
    """One quoted span plus its context -> {"quote", "speaker"} or None."""
    clean = _clean_quote(quote)
    if not clean:
        return None
    speaker = find_speaker(before, after)
    if not speaker:
        return None
    return {"quote": clean, "speaker": speaker}


def pick_quote_of_the_day(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose the best quote from rows of quoted spans.

    Each row needs: cluster_id, source, n_sources (outlets covering the story),
    before_text, quote_text, after_text, and optionally title.
    Quotes are grouped per story. A quote must appear in at least MIN_OUTLETS
    outlets within the same story: single-outlet spans are often scraped text
    from a different article on the same page. The best-corroborated quote in
    the most widely covered story wins; the speaker is the most complete form
    seen for that quote.
    """
    groups: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        found = extract_quote(row.get("before_text") or "", row.get("quote_text") or "", row.get("after_text") or "")
        if not found:
            continue
        key = _key(found["quote"])
        if not key:
            continue
        g = groups.setdefault(
            (row.get("cluster_id"), key),
            {
                "quote": found["quote"],
                "speakers": defaultdict(int),
                "sources": set(),
                "cluster_id": row.get("cluster_id"),
                "title": row.get("title"),
                "n_sources": int(row.get("n_sources") or 0),
            },
        )
        g["speakers"][found["speaker"]] += 1
        g["sources"].add(row.get("source"))
        g["n_sources"] = max(g["n_sources"], int(row.get("n_sources") or 0))

    best: tuple[float, dict[str, Any]] | None = None
    for g in groups.values():
        if len(g["sources"]) < MIN_OUTLETS:
            continue
        # Most complete speaker form, then most frequent.
        speaker = max(g["speakers"], key=lambda s: (len(s.split()), g["speakers"][s], s))
        multi = len(speaker.split()) >= 2
        score = (
            3.0 * min(len(g["sources"]), 5)
            + 0.5 * min(g["n_sources"], 15)
            + (1.5 if multi else 0.5)
            + (1.0 if 70 <= len(g["quote"]) <= 170 else 0.0)
        )
        item = {
            "quote": g["quote"],
            "speaker": speaker,
            "cluster_id": g["cluster_id"],
            "title": g["title"],
            "sources": len(g["sources"]),
        }
        if best is None or (score, len(g["quote"])) > (best[0], len(best[1]["quote"])):
            best = (score, item)
    return best[1] if best else None
