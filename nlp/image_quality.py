"""Shared image URL quality heuristics — keep in sync with web/shared/image_quality.json."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "web" / "shared" / "image_quality.json"


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    with _CONFIG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def weak_patterns() -> tuple[str, ...]:
    return tuple(_config()["weak_patterns"])


def min_url_length() -> int:
    return int(_config()["min_url_length"])


def generated_exempt_path() -> str:
    return str(_config()["generated_exempt_path"])


def source_bonuses() -> dict[str, int]:
    return {str(k): int(v) for k, v in _config()["source_bonuses"].items()}


def is_weak_image(url: str | None) -> bool:
    value = str(url or "").strip().lower()
    if not value:
        return True
    if generated_exempt_path() in value:
        return False
    if len(value) < min_url_length():
        return True
    return any(pattern in value for pattern in weak_patterns())


def classify_image_url(url: str | None) -> tuple[str, str]:
    value = str(url or "").strip()
    if not value:
        return "missing", "no representative image"
    lowered = value.lower()
    if generated_exempt_path() in lowered:
        return "ok", "generated cover art"
    if is_weak_image(value):
        for pattern in weak_patterns():
            if pattern in lowered:
                return "weak", f"matches {pattern}"
        return "weak", "url too short"
    if not re.match(r"^https?://|^/static/", value, re.I):
        return "weak", "unsupported scheme"
    return "ok", "usable candidate"


def _extract_image_dimensions(url: str) -> tuple[int, int]:
    try:
        parsed = urlparse(url)
    except Exception:
        parsed = None

    haystack = f"{getattr(parsed, 'path', '')} {getattr(parsed, 'query', '')} {url}".lower()
    match = re.search(r"(^|[^0-9])(\d{2,5})x(\d{2,5})([^0-9]|$)", haystack)
    if match:
        return int(match.group(2)), int(match.group(3))

    params = parse_qs(getattr(parsed, "query", "") or "")
    width = int(params.get("w", params.get("width", params.get("max_width", ["0"])))[0] or 0)
    height = int(params.get("h", params.get("height", params.get("max_height", ["0"])))[0] or 0)
    return width, height


def score_image_url(url: str, source: str | None = None) -> float:
    val = url.lower()
    width, height = _extract_image_dimensions(url)
    area = width * height
    score = 0.0

    if is_weak_image(url):
        score -= 12

    if ".avif" in val:
        score += 3
    if ".jpg" in val or ".jpeg" in val:
        score += 2
    if ".webp" in val:
        score += 2
    if ".png" in val:
        score -= 1

    if any(token in val for token in ("cdn", "imgix", "cloudinary")):
        score += 1

    if area:
        score += min(area / 240000, 10)
    if width >= 1400 or height >= 1400:
        score += 4
    elif width >= 1000 or height >= 1000:
        score += 2.5
    elif width >= 700 or height >= 700:
        score += 1.25
    if width and width < 180:
        score -= 6
    if height and height < 180:
        score -= 6

    if re.search(r"(thumb|thumbnail|sprite|logo|icon|avatar|favicon|pixel|small)", val):
        score -= 7
    if re.search(r"(hero|lead|main|large|full|original)", val):
        score += 2

    if source:
        lowered_source = source.lower()
        for token, bonus in source_bonuses().items():
            if token in lowered_source:
                score += bonus
                break

    return score


def rank_image_candidates(candidates: list[tuple[str, str | None]]) -> list[str]:
    ranked: list[tuple[float, int, int, str]] = []
    seen: set[str] = set()

    for index, (url, source) in enumerate(candidates):
        if not url or url in seen:
            continue
        seen.add(url)
        if is_weak_image(url):
            continue
        width, height = _extract_image_dimensions(url)
        ranked.append((score_image_url(url, source), width * height, -index, url))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [url for _, _, _, url in ranked]


def pick_best_image_url(candidates: list[tuple[str, str | None]]) -> str | None:
    ranked = rank_image_candidates(candidates)
    return ranked[0] if ranked else None


def select_representative_image(db: Any, cluster_id: str) -> str | None:
    rows = db.execute(
        """
        SELECT image_url, source
        FROM articles
        WHERE cluster_id = %s
          AND image_url IS NOT NULL
        ORDER BY created_at DESC
        """,
        (cluster_id,),
    )
    if not rows:
        return None
    return pick_best_image_url([(row.get("image_url"), row.get("source")) for row in rows if row.get("image_url")])
