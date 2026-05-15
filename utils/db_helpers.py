import time
import logging
from typing import Dict, Any
from core.config import SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY, SOURCE_CATEGORIES

log = logging.getLogger("presek")

_SOURCE_REGISTRY_CACHE = {"time": 0.0, "data": {}}

def get_source_registry(ttl_seconds: int = 300) -> Dict[str, Dict[str, Any]]:
    """
    Returns a unified map of source metadata (credibility, category).
    Prefer database values, fall back to hardcoded config.
    """
    now = time.time()
    if (
        _SOURCE_REGISTRY_CACHE["data"]
        and now - _SOURCE_REGISTRY_CACHE["time"] < ttl_seconds
    ):
        return _SOURCE_REGISTRY_CACHE["data"]

    registry = {}
    all_names = set(SOURCE_CREDIBILITY.keys()) | set(SOURCE_CATEGORIES.keys())

    for name in all_names:
        registry[name] = {
            "name": name,
            "credibility": float(SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY)),
            "category": SOURCE_CATEGORIES.get(name, "Lokalni"),
        }

    try:
        from core.database import db_manager as db

        rows = db.execute("SELECT name, credibility, category FROM sources WHERE is_active = TRUE")
        for row in rows:
            name = row["name"] if isinstance(row, dict) else row[0]
            cred = row["credibility"] if isinstance(row, dict) else row[1]
            cat = row["category"] if isinstance(row, dict) else row[2]

            registry[name] = {
                "name": name,
                "credibility": float(
                    cred
                    if cred is not None
                    else SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY)
                ),
                "category": cat or SOURCE_CATEGORIES.get(name, "Lokalni"),
            }
    except Exception as e:
        log.warning(
            f"[source_registry] Database metadata unavailable, using hardcoded only: {e}"
        )

    _SOURCE_REGISTRY_CACHE["time"] = now
    _SOURCE_REGISTRY_CACHE["data"] = registry
    return registry
