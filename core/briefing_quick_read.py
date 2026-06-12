"""Condensed briefing payload for the 5-minute read mode."""

from __future__ import annotations

import re


_BULLET_RE = re.compile(r"^[-*•]\s+(.+)$")


def build_quick_read_payload(
    content: str,
    metadata: dict | None = None,
    *,
    lang: str = "sr",
) -> dict:
    metadata = metadata or {}
    narratives = metadata.get("key_narratives") or []
    bullets: list[str] = []

    for line in str(content or "").splitlines():
        match = _BULLET_RE.match(line.strip())
        if not match:
            continue
        text = match.group(1).strip()
        if len(text) < 12:
            continue
        bullets.append(text)
        if len(bullets) >= 5:
            break

    stats = metadata.get("stats") or {}
    read_minutes = max(3, min(8, 2 + len(bullets) + len(narratives)))

    if lang == "mk":
        headline = "5-минутно читање"
        subline = "Краток преглед на денешното издание."
    else:
        headline = "5-minutno čitanje"
        subline = "Kratak pregled današnjeg izdanja."

    return {
        "headline": headline,
        "subline": subline,
        "read_minutes": read_minutes,
        "bullets": bullets[:5],
        "narratives": narratives[:3],
        "stats": {
            "total_articles": stats.get("total_articles"),
            "intl_share": stats.get("intl_share"),
            "pluralism_score": stats.get("pluralism_score"),
        },
    }
