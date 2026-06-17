import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api_errors import soft_error
from core.config import PROVIDER_FALLBACK_ORDER
from core.database import db_manager as db
from core.health import _probe_database, _probe_redis, get_source_statuses
from core.version import version_payload
from routes.security import verify_csrf_token

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
    # 1. AI Status & Usage
    current_provider = PROVIDER_FALLBACK_ORDER[0] if PROVIDER_FALLBACK_ORDER else "unknown"
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

    from core.ops_snapshot import build_ops_snapshot
    from core.queue_status import queue_status_payload

    ops = await build_ops_snapshot()

    return {
        "status": "success",
        "timestamp": datetime.datetime.now().isoformat(),
        "ai": {
            "current_provider": current_provider,
            "status": "operational" if current_provider != "unknown" else "offline",
            "fallback_order": PROVIDER_FALLBACK_ORDER,
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
        "queues": queue_status_payload(),
        "ops": ops,
        "system": version_payload(),
    }



@router.post("/admin/tasks/trigger-newsletter")
async def trigger_newsletter(
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Manually trigger the newsletter delivery task."""
    from tasks.delivery import send_newsletter_task

    # We use delay() to run it in background via Celery
    send_newsletter_task.delay()
    return {"status": "success", "message": "Newsletter delivery triggered in background."}


@router.post("/admin/tasks/retry-failed")
async def retry_failed_tasks(
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
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


@router.post("/admin/tasks/upgrade-stuck-fast-syntheses")
async def upgrade_stuck_fast_syntheses(
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Force full-quality upgrades for clusters stuck on fast-mode synthesis."""
    from tasks.maintenance import upgrade_stuck_fast_syntheses_task

    result = upgrade_stuck_fast_syntheses_task()
    return {
        "status": "success",
        "message": f"Pokrenuto {result.get('enqueued', 0)} punih nadogradnji sinteze.",
        **result,
    }


@router.post("/admin/tasks/refresh-fallback-syntheses")
async def refresh_fallback_syntheses(
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Re-run full synthesis for provisional and enhanced_fallback summaries."""
    from tasks.maintenance import refresh_fallback_syntheses_task

    result = refresh_fallback_syntheses_task()
    return {
        "status": "success",
        "message": f"Pokrenuto {result.get('enqueued', 0)} osvežavanja fallback sinteze.",
        **result,
    }


@router.post("/admin/tasks/refresh-low-score-syntheses")
async def refresh_low_score_syntheses(
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Re-run full synthesis for recent low-scoring cluster summaries."""
    from tasks.maintenance import refresh_low_score_syntheses_task

    result = refresh_low_score_syntheses_task()
    return {
        "status": "success",
        "message": f"Pokrenuto {result.get('enqueued', 0)} osvežavanja niskog kvaliteta sinteze.",
        **result,
    }


@router.get("/admin/ops/weekly-report")
async def get_weekly_ops_report(authorized: bool = Depends(verify_admin)):
    """Weekly synthesis quality and ops summary for the editorial cockpit."""
    from core.ops_report import build_weekly_ops_report

    return {"status": "success", "report": await build_weekly_ops_report()}


@router.post("/admin/tasks/drain-stale-clusters")
async def drain_stale_clusters(
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Enqueue synthesis refresh for stale active clusters (bounded batch)."""
    from core.celery_app import celery_app
    from core.ops_snapshot import build_ops_snapshot

    ops = await build_ops_snapshot()
    sample_ids = (ops.get("stale_clusters") or {}).get("sample_cluster_ids") or []
    if not sample_ids:
        return {"status": "success", "message": "Nema zastarelih klastera za osvežavanje.", "enqueued": 0}

    celery_app.send_task(
        "tasks.intelligence.auto_summarize_task",
        args=[sample_ids[:40]],
        countdown=5,
    )
    return {
        "status": "success",
        "message": f"Pokrenuto osvežavanje za {min(len(sample_ids), 40)} klastera.",
        "enqueued": min(len(sample_ids), 40),
        "stale_total": (ops.get("stale_clusters") or {}).get("count", 0),
    }


@router.post("/admin/tasks/clear-failed-ingestion")
async def clear_failed_ingestion(
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Clear ingestion failure noise and restart ingestion."""
    from core.celery_app import celery_app

    deleted = await db.async_execute(
        """
        DELETE FROM failed_tasks
        WHERE task_name ILIKE '%ingestion%'
        RETURNING id
        """,
    ) or []
    celery_app.send_task("tasks.ingestion_task.run_ingestion", countdown=3)
    return {
        "status": "success",
        "message": f"Obrisano {len(deleted)} ingestion grešaka i pokrenut refresh.",
        "cleared": len(deleted),
    }


@router.get("/admin/synthesis-traces/recent")
async def list_recent_synthesis_traces(
    lang: str = "sr",
    limit: int = 8,
    authorized: bool = Depends(verify_admin),
):
    """Batch synthesis traces for provisional, fallback, and stale clusters."""
    from core.synthesis_trace import list_recent_synthesis_traces as _list_traces

    traces = await _list_traces(lang=lang, limit=limit)
    return {"status": "success", "traces": traces, "count": len(traces)}


@router.get("/admin/cluster/{cluster_id}/synthesis-trace")
async def get_cluster_synthesis_trace(
    cluster_id: str,
    lang: str = "sr",
    authorized: bool = Depends(verify_admin),
):
    """Per-cluster synthesis debug trace for the admin cockpit."""
    from core.synthesis_trace import build_cluster_synthesis_trace

    trace = await build_cluster_synthesis_trace(cluster_id, lang=lang)
    if not trace.get("article_count"):
        raise HTTPException(status_code=404, detail="Klaster nije pronađen.")
    return {"status": "success", "trace": trace}


@router.get("/admin/localization/rules")
async def get_localization_rules(authorized: bool = Depends(verify_admin)):
    """Fetches the active dynamic localization and tag normalization rules."""
    from core.localization import localization_engine
    return {
        "status": "success",
        "rules": localization_engine.get_rules_dict()
    }


@router.post("/admin/localization/rules")
async def update_localization_rules(
    request: Request,
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Updates and hot-reloads the dynamic localization and tag normalization rules."""
    from core.localization import localization_engine
    try:
        rules_payload = await request.json()
        success = localization_engine.update_rules(rules_payload)
        if success:
            return {"status": "success", "message": "Rules updated and hot-reloaded successfully."}
        return soft_error(message="Invalid rules payload structure or keys.")
    except Exception as e:
        return soft_error(message=f"Failed to update rules: {str(e)}")
