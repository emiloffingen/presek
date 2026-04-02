"""
health.py — Health check + monitoring for Presek.mk
Add to app.py: from health import register_health_routes; register_health_routes(app, db)
"""

import database
import time
import threading
from datetime import datetime, timezone

# Module-level state
_start_time = time.time()
_last_refresh: dict = {"time": None, "count": 0, "errors": []}
_refresh_lock = threading.Lock()


def record_refresh(article_count: int, errors: list[str] | None = None):
    """Call this after each RSS refresh cycle in your auto_refresh_loop."""
    with _refresh_lock:
        _last_refresh["time"] = datetime.now(timezone.utc).isoformat()
        _last_refresh["count"] = article_count
        _last_refresh["errors"] = errors or []


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

        with _refresh_lock:
            last = dict(_last_refresh)

        overall = "ok" if (db_ok and redis_ok) else "degraded"
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
            "server_time": datetime.now(timezone.utc).isoformat(),
        })

