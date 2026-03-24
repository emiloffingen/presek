"""
health.py — Health check + monitoring for TimeAI.mk
Add to app.py: from health import register_health_routes; register_health_routes(app, db)
"""

import sqlite3
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


def register_health_routes(app, db_path: str = "timeai.db"):
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
        try:
            conn = sqlite3.connect(db_path, timeout=3)
            row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
            article_count = row[0] if row else 0
            conn.close()
            db_ok = True
        except Exception as e:
            pass

        with _refresh_lock:
            last = dict(_last_refresh)

        return jsonify({
            "status": "ok" if db_ok else "degraded",
            "uptime": f"{hours}h {mins}m {secs}s",
            "uptime_seconds": uptime_s,
            "database": {
                "ok": db_ok,
                "article_count": article_count,
            },
            "last_refresh": {
                "time": last["time"],
                "new_articles": last["count"],
                "errors": last["errors"],
            },
            "server_time": datetime.now(timezone.utc).isoformat(),
        })

    @app.route("/api/stats")
    def stats():
        try:
            conn = sqlite3.connect(db_path, timeout=3)
            total     = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            by_cat    = conn.execute(
                "SELECT category, COUNT(*) as n FROM articles GROUP BY category ORDER BY n DESC"
            ).fetchall()
            by_source = conn.execute(
                "SELECT source, COUNT(*) as n FROM articles GROUP BY source ORDER BY n DESC LIMIT 10"
            ).fetchall()
            recent_24h = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE created_at >= datetime('now', '-1 day')"
            ).fetchone()[0]
            summarized = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''"
            ).fetchone()[0]
            conn.close()
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        return jsonify({
            "total_articles": total,
            "last_24h": recent_24h,
            "summarized": summarized,
            "by_category": [{"category": r[0] or "Македонија", "count": r[1]} for r in by_cat],
            "top_sources": [{"source": r[0], "count": r[1]} for r in by_source],
        })
