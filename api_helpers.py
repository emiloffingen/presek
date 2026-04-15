"""
api_helpers.py — Shared helpers used by the FastAPI backend and background tasks.

Keeping these in one place ensures bug fixes and behavioural changes apply everywhere.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from nlp.keywords import ENTITY_NOISE_WORDS
from utils import get_source_trust_label, build_cluster_source_signals

_EXTRA_NOISE = {"вести", "вест", "извор", "извори", "кластер"}
_GENERIC_ANGLES = {"перспектива", "агол", "точка", "став", "гледиште"}
_SAFE_TOPIC_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _clean_text_block(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "")
    text = re.sub(r"^\s*(summary|резиме|сублимат|статии)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^[•*\-\u2022]+\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _infer_perspective_angle(content: str, fallback: str = "Клучен агол") -> str:
    lowered = content.lower()
    if any(token in lowered for token in ("разлик", "акцент", "формулац", "наглас")):
        return "Различни акценти"
    if any(token in lowered for token in ("заеднич", "повеќето извори", "иста линија", "сите извори")):
        return "Заедничка линија"
    if any(token in lowered for token in ("отворено", "нејас", "непотвр", "сè уште не", "останува")):
        return "Што останува отворено"
    if any(token in lowered for token in ("реакц", "одговор", "коментар", "осуд")):
        return "Реакции"
    if any(token in lowered for token in ("контекст", "позадин", "поширок")):
        return "Поширок контекст"
    return fallback


def normalize_summary_text(raw_summary) -> str:
    if not raw_summary:
        return ""

    text = str(raw_summary).replace("\r", "\n")
    lines = []
    seen = set()

    for raw_line in text.split("\n"):
        clean = _clean_text_block(raw_line)
        if not clean:
            continue
        if clean.lower() == "статии:":
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(clean)

    if not lines:
        return ""

    if len(lines) == 1:
        return lines[0]

    return "\n".join(f"• {line}" for line in lines[:4])


def normalize_perspectives(raw_perspectives) -> list[dict]:
    """
    Normalise a raw perspectives value into a clean list of {angle, content} dicts.

    Accepts:
    - A JSON string (decoded first)
    - A list of dicts (with flexible key names: angle/label/title/name, content/text/description)
    - A list of plain strings
    """
    if not raw_perspectives:
        return []
    if isinstance(raw_perspectives, str):
        try:
            raw_perspectives = json.loads(raw_perspectives)
        except Exception:
            return []
    if not isinstance(raw_perspectives, list):
        return []

    result = []
    seen = set()
    for item in raw_perspectives:
        if isinstance(item, str):
            content = _clean_text_block(item)
            if content:
                angle = _infer_perspective_angle(content)
                key = content.casefold()
                if key not in seen:
                    seen.add(key)
                    result.append({"angle": angle, "content": content})
            continue
        if not isinstance(item, dict):
            continue
        angle = _clean_text_block(
            item.get("angle")
            or item.get("label")
            or item.get("title")
            or item.get("name")
            or ""
        )
        content = _clean_text_block(
            item.get("content")
            or item.get("text")
            or item.get("description")
            or ""
        )
        if not content:
            continue
        if not angle or angle.casefold() in _GENERIC_ANGLES:
            angle = _infer_perspective_angle(content)
        key = content.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append({"angle": angle or "Клучен агол", "content": content})

    return result[:4]


def normalize_server_delivery_subscription(payload) -> dict:
    payload = payload or {}
    raw_channel = str(payload.get("channel") or "ntfy").strip().lower()
    channel = raw_channel if raw_channel == "webpush" else "ntfy"
    
    raw_target = str(payload.get("target") or "").strip()
    
    if channel == "ntfy":
        target = _SAFE_TOPIC_RE.sub("-", raw_target).strip("-._")[:120]
    else:
        # WebPush target is a JSON string of the PushSubscription object
        target = raw_target[:2048]

    is_active = bool(payload.get("isActive")) and bool(target)

    return {
        "channel": channel,
        "target": target,
        "morningBriefing": payload.get("morningBriefing") is not False,
        "weeklyDigest": bool(payload.get("weeklyDigest")),
        "breakingTopics": bool(payload.get("breakingTopics")),
        "breakingSources": bool(payload.get("breakingSources")),
        "isActive": is_active,
    }


