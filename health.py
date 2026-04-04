"""
health.py — Health check + monitoring for Presek.mk
Add to app.py: from health import register_health_routes; register_health_routes(app, db)
"""

import database
import time
import json
from datetime import datetime, timezone

_start_time = time.time()
_REDIS_KEY = "presek:last_refresh"
_TASK_REDIS_KEY = "presek:task_statuses"
_SOURCE_REDIS_KEY = "presek:source_statuses"


def _get_redis():
    import os, redis as _redis
    return _redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))


def record_refresh(article_count: int, errors: list[str] | None = None):
    """Call this after each RSS refresh cycle. Writes to Redis so all workers see it."""
    payload = {
        "time": datetime.now(timezone.utc).isoformat(),
        "count": article_count,
        "errors": errors or [],
    }
    try:
        _get_redis().set(_REDIS_KEY, json.dumps(payload), ex=3600)
    except Exception:
        pass  # Non-critical; health endpoint falls back gracefully


def record_task_event(task_name: str, status: str, detail: str | None = None):
    """Persist a lightweight task-status event for operational visibility."""
    if not task_name or not status:
        return

    payload = {
        "task": task_name,
        "status": status,
        "detail": detail or "",
        "time": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _get_redis().hset(_TASK_REDIS_KEY, task_name, json.dumps(payload))
        _get_redis().expire(_TASK_REDIS_KEY, 3600 * 12)
    except Exception:
        pass


def record_source_fetch(source_name: str, status: str, fetched: int = 0, accepted: int = 0, error: str | None = None):
    """Persist per-source fetch results for operational visibility."""
    if not source_name or not status:
        return

    payload = {
        "source": source_name,
        "status": status,
        "fetched": int(fetched or 0),
        "accepted": int(accepted or 0),
        "error": (error or "")[:300],
        "time": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _get_redis().hset(_SOURCE_REDIS_KEY, source_name, json.dumps(payload))
        _get_redis().expire(_SOURCE_REDIS_KEY, 3600 * 12)
    except Exception:
        pass


def _freshness_payload(last_refresh_time: str | None):
    if not last_refresh_time:
        return {"status": "stale", "age_minutes": None, "label": "Нема скоро освежување"}

    try:
        refresh_dt = datetime.fromisoformat(last_refresh_time.replace("Z", "+00:00"))
        age_minutes = max(0, int((datetime.now(timezone.utc) - refresh_dt).total_seconds() // 60))
    except Exception:
        return {"status": "stale", "age_minutes": None, "label": "Непознато освежување"}

    if age_minutes <= 15:
        return {"status": "fresh", "age_minutes": age_minutes, "label": "Освежено скоро"}
    if age_minutes <= 45:
        return {"status": "aging", "age_minutes": age_minutes, "label": "Мало доцнење"}
    return {"status": "stale", "age_minutes": age_minutes, "label": "Освежувањето доцни"}


def register_health_routes(app):
    """Register /api/health and /api/stats routes onto a Flask app."""

    from flask import jsonify

    @app.route("/api/health")
    def health():
        uptime_s = int(time.time() - _start_time)
        hours, rem = divmod(uptime_s, 3600)
        mins, secs = divmod(rem, 60)

        # Quick DB probe
        db_ok = False
        article_count = 0
        db_size_mb = 0.0
        try:
            conn = database.get_db()
            row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
            article_count = row[0] if row else 0
            conn.close()
            db_size_mb = database.get_db_size()
            db_ok = True
        except Exception:
            pass

        # Redis probe
        redis_ok = False
        try:
            import os, redis as _redis
            r = _redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
            r.ping()
            redis_ok = True
        except Exception:
            pass

        last = {"time": None, "count": 0, "errors": []}
        try:
            raw = _get_redis().get(_REDIS_KEY)
            if raw:
                last = json.loads(raw)
        except Exception:
            pass

        task_statuses = {}
        try:
            raw_tasks = _get_redis().hgetall(_TASK_REDIS_KEY) or {}
            task_statuses = {
                (key.decode() if isinstance(key, bytes) else key): json.loads(
                    value.decode() if isinstance(value, bytes) else value
                )
                for key, value in raw_tasks.items()
            }
        except Exception:
            task_statuses = {}

        source_statuses = {}
        try:
            raw_sources = _get_redis().hgetall(_SOURCE_REDIS_KEY) or {}
            source_statuses = {
                (key.decode() if isinstance(key, bytes) else key): json.loads(
                    value.decode() if isinstance(value, bytes) else value
                )
                for key, value in raw_sources.items()
            }
        except Exception:
            source_statuses = {}

        freshness = _freshness_payload(last.get("time"))

        overall = "ok" if (db_ok and redis_ok) else "degraded"
        if overall == "ok" and freshness["status"] == "stale":
            overall = "degraded"
        return jsonify({
            "status": overall,
            "uptime": f"{hours}h {mins}m {secs}s",
            "uptime_seconds": uptime_s,
            "database": {
                "ok": db_ok,
                "article_count": article_count,
                "size_mb": db_size_mb,
            },
            "redis": {"ok": redis_ok},
            "last_refresh": {
                "time": last["time"],
                "new_articles": last["count"],
                "errors": last["errors"],
            },
            "freshness": freshness,
            "tasks": task_statuses,
            "sources": source_statuses,
            "server_time": datetime.now(timezone.utc).isoformat(),
        })
