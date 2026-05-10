import datetime
import secrets
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from database import db_manager as db
from config import PRESEK_ADMIN_TOKEN, PROVIDER_FALLBACK_ORDER
from health import get_source_statuses, _probe_database, _probe_redis
from utils import redis_client
from version import version_payload

log = logging.getLogger("presek.api.admin")
router = APIRouter()


async def verify_admin(request: Request):
    token = (request.headers.get("X-Admin-Token") or "").strip()
    if (
        not PRESEK_ADMIN_TOKEN
        or not token
        or not secrets.compare_digest(token, PRESEK_ADMIN_TOKEN)
    ):
        raise HTTPException(status_code=403, detail="Неовластен пристап")
    return True


@router.get("/admin/dashboard")
async def get_admin_dashboard(authorized: bool = Depends(verify_admin)):
    """Aggregates all operational health metrics for the Presek Cockpit."""

    # 1. AI Usage (Gemini Budget)
    today = datetime.date.today().isoformat()
    gemini_usage = int(redis_client.get(f"ai:gemini:usage:{today}") or 0)

    # 2. Scraper Health
    source_statuses = get_source_statuses()
    total_sources = len(source_statuses)
    degraded_sources = [s for s in source_statuses.values() if s.get("degraded")]

    # 3. Database & Tasks
    db_health = _probe_database()
    redis_health = _probe_redis()
    failed_tasks = db.execute(
        """
        SELECT task_name, error_message, created_at AS failed_at
        FROM failed_tasks 
        ORDER BY created_at DESC LIMIT 5
    """
    )

    # 4. Success Rates (Calculated from Redis)
    # This is an estimate based on the current live status hash
    total_fetched = sum(int(s.get("fetched", 0)) for s in source_statuses.values())
    total_accepted = sum(int(s.get("accepted", 0)) for s in source_statuses.values())
    global_acceptance = (
        round(total_accepted / total_fetched, 2) if total_fetched > 0 else 0
    )

    return {
        "status": "success",
        "timestamp": datetime.datetime.now().isoformat(),
        "ai": {
            "gemini_usage_today": gemini_usage,
            "gemini_daily_limit": 2000000,  # Hand-synced with ai_engine.py for now
            "current_provider": (
                PROVIDER_FALLBACK_ORDER[0] if PROVIDER_FALLBACK_ORDER else "unknown"
            ),
        },
        "scrapers": {
            "total_sources": total_sources,
            "degraded_count": len(degraded_sources),
            "global_acceptance_rate": global_acceptance,
            "statuses": source_statuses,
        },
        "tasks": {"failed_recent": failed_tasks},
        "db": db_health,
        "redis": redis_health,
        "system": version_payload(),
    }


@router.post("/admin/tasks/retry-failed")
async def retry_failed_tasks(authorized: bool = Depends(verify_admin)):
    """Clear failed task records after the operator has handled them."""
    deleted = db.execute("DELETE FROM failed_tasks", fetch=False)
    return {"status": "success", "message": "Failed tasks cleared", "deleted": deleted}
