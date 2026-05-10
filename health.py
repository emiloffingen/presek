"""
health.py — Health check + monitoring for Presek.mk
Used by api_fast.py for /api/health and per-source policy tracking.
"""

import database
import logging
import time
import json
import os
from datetime import datetime, timezone

from utils import redis_client as _shared_redis_client

log = logging.getLogger(__name__)

_start_time = time.time()
_REDIS_KEY = "presek:last_refresh"
_TASK_REDIS_KEY = "presek:task_statuses"
_SOURCE_REDIS_KEY = "presek:source_statuses"
_SOURCE_POLICY_REDIS_KEY = "presek:source_policies"
AUTO_PAUSE_ERROR_STREAK = 3
AUTO_FLAG_LOW_ACCEPT_STREAK = 3
LOW_ACCEPTANCE_THRESHOLD = 0.2
LOW_ACCEPTANCE_MIN_FETCHED = 4


def _get_redis():
    """Return the shared Redis client (decode_responses=True)."""
    return _shared_redis_client


def _probe_database():
    result = {
        "ok": False,
        "article_count": 0,
        "size_mb": 0.0,
        "error": "",
    }

    conn = None
    try:
        conn = database.get_db()
        row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
        result["article_count"] = row[0] if row else 0
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
        return result
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    try:
        result["size_mb"] = database.get_db_size()
    except Exception as exc:
        result["error"] = f"db_size probe failed: {exc}"

    return result


def _probe_redis():
    result = {
        "ok": False,
        "url": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        "error": "",
    }
    try:
        _get_redis().ping()
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _source_quality_payload(status: str, fetched: int, accepted: int, error: str | None = None):
    fetched = max(0, int(fetched or 0))
    accepted = max(0, int(accepted or 0))
    acceptance_ratio = (accepted / fetched) if fetched else 0.0
    base_score = 1.0

    if status == "error":
        base_score = 0.35
    elif status == "warning":
        base_score = 0.7

    score = base_score
    if fetched > 0:
        score *= max(0.45, min(1.0, 0.55 + acceptance_ratio))
    score = round(max(0.2, min(1.0, score)), 2)

    if score >= 0.85:
        label = "Стабилен извор"
    elif score >= 0.6:
        label = "Намален квалитет"
    else:
        label = "Проблематичен извор"

    return {
        "quality_score": score,
        "quality_label": label,
        "acceptance_ratio": round(acceptance_ratio, 2) if fetched else 0.0,
        "degraded": score < 0.6 or status == "error" or bool(error),
    }


def update_source_policy(source_name: str, status: str, fetched: int = 0, accepted: int = 0):
    fetched = max(0, int(fetched or 0))
    accepted = max(0, int(accepted or 0))
    acceptance_ratio = (accepted / fetched) if fetched else 0.0
    now = datetime.now(timezone.utc)

    state = {
        "source": source_name,
        "consecutive_errors": 0,
        "low_accept_streak": 0,
        "auto_flagged": False,
        "should_auto_pause": False,
        "last_status": status,
        "updated_at": now.isoformat(),
    }
    try:
        raw = _get_redis().hget(_SOURCE_POLICY_REDIS_KEY, source_name)
        if raw:
            state.update(json.loads(raw.decode() if isinstance(raw, bytes) else raw))
    except Exception:
        pass

    if status == "error":
        state["consecutive_errors"] = int(state.get("consecutive_errors", 0)) + 1
    else:
        state["consecutive_errors"] = 0

    low_accept = (
        fetched >= LOW_ACCEPTANCE_MIN_FETCHED
        and acceptance_ratio < LOW_ACCEPTANCE_THRESHOLD
        and status != "error"
    )
    if low_accept:
        state["low_accept_streak"] = int(state.get("low_accept_streak", 0)) + 1
    elif fetched > 0:
        state["low_accept_streak"] = 0

    state["auto_flagged"] = state["low_accept_streak"] >= AUTO_FLAG_LOW_ACCEPT_STREAK
    state["should_auto_pause"] = state["consecutive_errors"] >= AUTO_PAUSE_ERROR_STREAK
    state["last_status"] = status
    state["updated_at"] = now.isoformat()

    try:
        _get_redis().hset(_SOURCE_POLICY_REDIS_KEY, source_name, json.dumps(state))
        _get_redis().expire(_SOURCE_POLICY_REDIS_KEY, 3600 * 24 * 7)
    except Exception:
        pass
    return state


def reset_source_policy(source_name: str):
    try:
        _get_redis().hdel(_SOURCE_POLICY_REDIS_KEY, source_name)
    except Exception:
        pass


def record_refresh(article_count: int, errors: list[str] | None = None):
    """Call this after each RSS refresh cycle. Writes to Redis so all workers see it."""
    payload = {
        "time": datetime.now(timezone.utc).isoformat(),
        "count": article_count,
        "errors": errors or [],
    }
    try:
        _get_redis().set(_REDIS_KEY, json.dumps(payload), ex=3600)
    except Exception as e:
        # Non-critical; health endpoint falls back gracefully
        log.debug(f"Failed to record refresh in Redis: {e}")


def record_source_fetch(
        source_name: str,
        status: str,
        fetched: int = 0,
        accepted: int = 0,
        error: str | None = None,
):
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
    payload.update(_source_quality_payload(status, fetched, accepted, error=error))
    payload.update(update_source_policy(source_name, status, fetched, accepted))
    try:
        _get_redis().hset(_SOURCE_REDIS_KEY, source_name, json.dumps(payload))
        _get_redis().expire(_SOURCE_REDIS_KEY, 3600 * 12)
    except Exception:
        pass


def get_source_statuses():
    try:
        raw_sources = _get_redis().hgetall(_SOURCE_REDIS_KEY) or {}
        return {
            (key.decode() if isinstance(key, bytes) else key): json.loads(
                value.decode() if isinstance(value, bytes) else value
            )
            for key, value in raw_sources.items()
        }
    except Exception:
        return {}


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
