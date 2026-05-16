import datetime
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from core.database import db_manager as db
from core.config import PROVIDER_FALLBACK_ORDER
from core.health import get_source_statuses, _probe_database, _probe_redis
from utils import redis_client
from core.version import version_payload

log = logging.getLogger("presek.api.admin")
router = APIRouter()


async def verify_admin(request: Request):
    """Verify admin access using JWT token."""
    from core.auth import verify_admin_jwt
    
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=403, detail="Neovlasten pristap")
    
    try:
        token = auth_header.split("Bearer ")[1]
        if not verify_admin_jwt(token):
            raise HTTPException(status_code=403, detail="Neovlasten pristap")
    except Exception:
        raise HTTPException(status_code=403, detail="Neovlasten pristap")
    
    return True


@router.get("/admin/dashboard")
async def get_admin_dashboard(authorized: bool = Depends(verify_admin)):
    """Aggregates all operational health metrics for the Presek Cockpit."""

    # 1. AI Status
    current_provider = PROVIDER_FALLBACK_ORDER[0] if PROVIDER_FALLBACK_ORDER else "unknown"

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
            "current_provider": current_provider,
            "status": "operational" if current_provider != "unknown" else "offline"
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


@router.post("/admin/tasks/trigger-newsletter")
async def trigger_newsletter(authorized: bool = Depends(verify_admin)):
    """Manually trigger the newsletter delivery task."""
    from tasks.delivery import send_newsletter_task

    # We use delay() to run it in background via Celery
    send_newsletter_task.delay()
    return {"status": "success", "message": "Newsletter delivery triggered in background."}


@router.post("/admin/tasks/retry-failed")
async def retry_failed_tasks(authorized: bool = Depends(verify_admin)):
    """Re-dispatch failed tasks to Celery and clear records."""
    from core.celery_app import celery_app

    failed = db.execute("SELECT id, task_name, args, kwargs FROM failed_tasks")
    if not failed:
        return {"status": "success", "message": "Nema neuspešnih zadataka."}

    retry_count = 0
    for task_row in failed:
        try:
            # Re-dispatch by name using send_task to avoid direct imports
            celery_app.send_task(
                task_row["task_name"],
                args=task_row["args"] or [],
                kwargs=task_row["kwargs"] or {},
            )
            db.execute(
                "DELETE FROM failed_tasks WHERE id = %s", (task_row["id"],), fetch=False
            )
            retry_count += 1
        except Exception as e:
            log.error(f"Failed to retry task {task_row['id']}: {e}")

    return {
        "status": "success",
        "message": f"Pokrenuto ponovno izvršavanje {retry_count} zadataka.",
        "retried": retry_count,
    }
