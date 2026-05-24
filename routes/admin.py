import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from core.config import PROVIDER_FALLBACK_ORDER
from core.database import db_manager as db
from core.health import _probe_database, _probe_redis, get_source_statuses
from core.version import version_payload

log = logging.getLogger("presek.api.admin")
router = APIRouter()


async def verify_admin(request: Request):
    """Verify admin access using a JWT or the configured static admin token."""
    from core.auth import verify_admin_jwt
    from routes.common import _static_admin_token_authorized

    if _static_admin_token_authorized(request):
        return True

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
    from utils import redis_client

    # 1. AI Status & Usage
    current_provider = PROVIDER_FALLBACK_ORDER[0] if PROVIDER_FALLBACK_ORDER else "unknown"
    today = datetime.date.today().isoformat()
    try:
        gemini_usage = int(redis_client.get(f"ai:gemini:usage:{today}") or 0)
    except Exception:
        gemini_usage = 0

    # 2. Scraper Health
    source_statuses = get_source_statuses()
    total_sources = len(source_statuses)
    degraded_sources = [s for s in source_statuses.values() if s.get("degraded")]
    healthy_feeds = sum(1 for s in source_statuses.values() if not s.get("degraded", False))

    recent_activity = []
    for s in source_statuses.values():
        recent_activity.append({
            "source": s.get("source", "Unknown"),
            "is_active": not s.get("degraded", False),
            "last_fetched": s.get("time") or datetime.datetime.now().isoformat(),
            "recent_count": s.get("accepted", 0)
        })
    recent_activity.sort(key=lambda x: x.get("last_fetched", ""), reverse=True)

    # 3. Database & Tasks
    db_health = _probe_database()
    redis_health = _probe_redis()
    
    # Failed tasks lists
    failed_tasks_db = await db.async_execute(
        """
        SELECT task_name, error_message, created_at AS failed_at
        FROM failed_tasks
        ORDER BY created_at DESC LIMIT 5
        """
    ) or []

    recent_failures_db = [
        {"task_name": t.get("task_name"), "error": t.get("error_message")}
        for t in failed_tasks_db
    ]

    failed_tasks_count_row = await db.async_execute("SELECT COUNT(*) as count FROM failed_tasks")
    failed_tasks_count = failed_tasks_count_row[0]["count"] if failed_tasks_count_row else 0

    # 4. Success Rates (Calculated from Redis)
    total_fetched = sum(int(s.get("fetched", 0)) for s in source_statuses.values())
    total_accepted = sum(int(s.get("accepted", 0)) for s in source_statuses.values())
    global_acceptance = round(total_accepted / total_fetched, 2) if total_fetched > 0 else 0

    # 5. Articles Volume
    last_24h_res = await db.async_execute("SELECT COUNT(*) as count FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'")
    last_24h = last_24h_res[0]["count"] if last_24h_res else 0

    last_1h_res = await db.async_execute("SELECT COUNT(*) as count FROM articles WHERE created_at >= NOW() - INTERVAL '1 hour'")
    last_1h = last_1h_res[0]["count"] if last_1h_res else 0

    # 6. Clusters Stats
    total_summaries_row = await db.async_execute("SELECT COUNT(*) as count FROM cluster_summaries")
    total_summaries = total_summaries_row[0]["count"] if total_summaries_row else 0

    total_clusters_row = await db.async_execute("SELECT COUNT(DISTINCT cluster_id) as count FROM articles")
    total_clusters = total_clusters_row[0]["count"] if total_clusters_row else 0

    return {
        "status": "success",
        "timestamp": datetime.datetime.now().isoformat(),
        "ai": {
            "current_provider": current_provider,
            "status": "operational" if current_provider != "unknown" else "offline",
            "gemini_usage_today": gemini_usage,
            "gemini_daily_limit": 2000000,
        },
        "scrapers": {
            "total_sources": total_sources,
            "degraded_count": len(degraded_sources),
            "global_acceptance_rate": global_acceptance,
            "statuses": source_statuses,
            "healthy_feeds": healthy_feeds,
            "total_feeds": total_sources,
            "recent_activity": recent_activity,
        },
        "tasks": {
            "failed_recent": failed_tasks_db,
            "failed_tasks": failed_tasks_count,
            "recent_failures": recent_failures_db,
        },
        "db": db_health,
        "redis": {
            "ok": redis_health.get("ok", False),
            "ping": "PONG" if redis_health.get("ok", False) else "offline",
            "error": redis_health.get("error", ""),
        },
        "articles": {
            "last_24h": last_24h,
            "last_1h": last_1h,
        },
        "clusters": {
            "total_summaries": total_summaries,
            "total_clusters": total_clusters,
        },
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

    failed = await db.async_execute("SELECT id, task_name, args, kwargs FROM failed_tasks")
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
            await db.async_execute("DELETE FROM failed_tasks WHERE id = %s", (task_row["id"],), fetch=False)
            retry_count += 1
        except Exception as e:
            log.error(f"Failed to retry task {task_row['id']}: {e}")

    return {
        "status": "success",
        "message": f"Pokrenuto ponovno izvršavanje {retry_count} zadataka.",
        "retried": retry_count,
    }


@router.get("/admin/localization/rules")
async def get_localization_rules(authorized: bool = Depends(verify_admin)):
    """Fetches the active dynamic localization and tag normalization rules."""
    from core.localization import localization_engine
    return {
        "status": "success",
        "rules": localization_engine.get_rules_dict()
    }


@router.post("/admin/localization/rules")
async def update_localization_rules(request: Request, authorized: bool = Depends(verify_admin)):
    """Updates and hot-reloads the dynamic localization and tag normalization rules."""
    from core.localization import localization_engine
    try:
        rules_payload = await request.json()
        success = localization_engine.update_rules(rules_payload)
        if success:
            return {"status": "success", "message": "Rules updated and hot-reloaded successfully."}
        else:
            return {"status": "error", "message": "Invalid rules payload structure or keys."}
    except Exception as e:
        return {"status": "error", "message": f"Failed to update rules: {str(e)}"}
