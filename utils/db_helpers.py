import asyncio
import logging
import threading
import time
from typing import Any, Dict

from core.config import DEFAULT_CREDIBILITY, SOURCE_CATEGORIES, SOURCE_CREDIBILITY

log = logging.getLogger("presek")

_SOURCE_REGISTRY_CACHE = {"time": 0.0, "data": {}}
_SOURCE_REGISTRY_LOCK = threading.Lock()
_SOURCE_REGISTRY_REFRESHING = threading.Event()


def _hardcoded_source_registry() -> Dict[str, Dict[str, Any]]:
    registry = {}
    for name in set(SOURCE_CREDIBILITY.keys()) | set(SOURCE_CATEGORIES.keys()):
        registry[name] = {
            "name": name,
            "credibility": float(SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY)),
            "category": SOURCE_CATEGORIES.get(name, "Lokalni"),
        }
    return registry


def _load_source_registry() -> Dict[str, Dict[str, Any]]:
    """Hardcoded metadata overlaid with the database rows. Blocks on the database."""
    registry = _hardcoded_source_registry()
    try:
        from core.database import db_manager as db

        rows = db.execute("SELECT name, credibility, category FROM sources WHERE is_active = TRUE")
        for row in rows:
            name = row["name"] if isinstance(row, dict) else row[0]
            cred = row["credibility"] if isinstance(row, dict) else row[1]
            cat = row["category"] if isinstance(row, dict) else row[2]

            registry[name] = {
                "name": name,
                "credibility": float(cred if cred is not None else SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY)),
                "category": cat or SOURCE_CATEGORIES.get(name, "Lokalni"),
            }
    except Exception as e:
        log.warning(f"[source_registry] Database metadata unavailable, using hardcoded only: {e}")
    return registry


def _refresh_source_registry_now() -> Dict[str, Dict[str, Any]]:
    registry = _load_source_registry()
    with _SOURCE_REGISTRY_LOCK:
        _SOURCE_REGISTRY_CACHE["time"] = time.time()
        _SOURCE_REGISTRY_CACHE["data"] = registry
    return registry


def _refresh_source_registry_in_background() -> None:
    if _SOURCE_REGISTRY_REFRESHING.is_set():
        return
    _SOURCE_REGISTRY_REFRESHING.set()

    def _run():
        try:
            _refresh_source_registry_now()
        finally:
            _SOURCE_REGISTRY_REFRESHING.clear()

    threading.Thread(target=_run, name="source-registry-refresh", daemon=True).start()


def _on_event_loop_thread() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def get_source_registry(ttl_seconds: int = 300) -> Dict[str, Dict[str, Any]]:
    """
    Returns a unified map of source metadata (credibility, category).
    Prefer database values, fall back to hardcoded config.

    On the asyncio event-loop thread this never touches the database: a blocking
    query there froze the whole API whenever the small PgBouncer pool was busy (the
    connections it waited for could only be released by coroutines needing the very
    loop it was blocking, until the 60 s timeouts fired). There the cached value is
    served (stale if need be), a refresh runs in a background thread, and the
    hardcoded registry covers the cold start. Other threads (Celery, scripts) keep the
    original blocking behaviour.
    """
    now = time.time()
    cached = _SOURCE_REGISTRY_CACHE["data"]
    fresh = bool(cached) and now - _SOURCE_REGISTRY_CACHE["time"] < ttl_seconds
    if fresh:
        return cached

    if _on_event_loop_thread():
        _refresh_source_registry_in_background()
        return cached or _hardcoded_source_registry()

    return _refresh_source_registry_now()
