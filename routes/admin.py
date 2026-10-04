import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api_errors import soft_error
from core.config import PROVIDER_FALLBACK_ORDER
from core.database import db_manager as db
from core.db_monitoring import check_db_pool_health, get_current_pool_stats, get_database_health
from core.health import _probe_database, _probe_redis, get_source_statuses
from core.queue_monitoring import (
    check_queue_health,
    get_current_queue_stats,
    get_queue_health,
    get_scaling_recommendation,
)
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
        recent_activity.append(
            {
                "source": s.get("source", "Unknown"),
                "is_active": not s.get("degraded", False),
                "last_fetched": s.get("time") or datetime.datetime.now().isoformat(),
                "recent_count": s.get("accepted", 0),
            }
        )
    recent_activity.sort(key=lambda x: x.get("last_fetched", ""), reverse=True)

    # 3. Database & Tasks
    db_health = _probe_database()
    redis_health = _probe_redis()

    # Failed tasks lists
    failed_tasks_db = (
        await db.async_execute(
            """
        SELECT task_name, error_message, created_at AS failed_at
        FROM failed_tasks
        ORDER BY created_at DESC LIMIT 5
        """
        )
        or []
    )

    recent_failures_db = [{"task_name": t.get("task_name"), "error": t.get("error_message")} for t in failed_tasks_db]

    failed_tasks_count_row = await db.async_execute("SELECT COUNT(*) as count FROM failed_tasks")
    failed_tasks_count = failed_tasks_count_row[0]["count"] if failed_tasks_count_row else 0

    # 4. Success Rates (Calculated from Redis)
    total_fetched = sum(int(s.get("fetched", 0)) for s in source_statuses.values())
    total_accepted = sum(int(s.get("accepted", 0)) for s in source_statuses.values())
    global_acceptance = round(total_accepted / total_fetched, 2) if total_fetched > 0 else 0

    # 5. Articles Volume
    last_24h_res = await db.async_execute(
        "SELECT COUNT(*) as count FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'"
    )
    last_24h = last_24h_res[0]["count"] if last_24h_res else 0

    last_1h_res = await db.async_execute(
        "SELECT COUNT(*) as count FROM articles WHERE created_at >= NOW() - INTERVAL '1 hour'"
    )
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
    registered_tasks = set(celery_app.tasks.keys())
    for task_row in failed:
        task_name = str(task_row.get("task_name") or "").strip()
        if not task_name or task_name not in registered_tasks:
            log.warning("Skipping unknown or unregistered failed task: %s", task_name or task_row.get("id"))
            continue
        try:
            # Re-dispatch by name using send_task to avoid direct imports
            celery_app.send_task(
                task_name,
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
        "tasks.summarization.build_extractive_clusters_task",
        kwargs={"hours": 168, "limit": 60},
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

    deleted = (
        await db.async_execute(
            """
        DELETE FROM failed_tasks
        WHERE task_name ILIKE '%ingestion%'
        RETURNING id
        """,
        )
        or []
    )
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
        raise HTTPException(status_code=404, detail="Кластерот не е пронајден.")
    return {"status": "success", "trace": trace}


@router.post("/admin/tokens/create")
async def create_admin_token_endpoint(
    subject: str = "admin",
    scope: str = "full-access",
    expiry_hours: Optional[int] = None,
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Create a new admin token with specified parameters."""
    from core.admin_tokens import create_admin_token

    try:
        token, token_info = create_admin_token(subject=subject, scope=scope, expiry_hours=expiry_hours)
        return {
            "status": "success",
            "token": token,
            "token_id": token_info.token_id,
            "subject": token_info.subject,
            "scope": token_info.scope,
            "expires_at": token_info.expires_at.isoformat(),
            "created_at": token_info.created_at.isoformat(),
        }
    except ValueError as e:
        log.warning(f"Invalid admin token payload: {e}")
        return {"status": "error", "message": "Invalid admin token payload"}
    except Exception as e:
        log.error(f"Failed to create admin token: {e}")
        return {"status": "error", "message": "Failed to create admin token"}


@router.post("/admin/tokens/revoke")
async def revoke_admin_token_endpoint(
    token_id: str,
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Revoke an admin token by its ID."""
    from core.admin_tokens import revoke_admin_token

    success = revoke_admin_token(token_id)
    if success:
        return {"status": "success", "message": f"Token {token_id} revoked successfully"}
    else:
        return {"status": "error", "message": f"Token {token_id} not found or already revoked"}


@router.post("/admin/tokens/revoke-all")
async def revoke_all_tokens_for_subject_endpoint(
    subject: str = "admin",
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Revoke all tokens for a specific subject."""
    from core.admin_tokens import revoke_all_tokens_for_subject

    count = revoke_all_tokens_for_subject(subject)
    return {"status": "success", "message": f"Revoked {count} tokens for subject {subject}", "revoked_count": count}


@router.get("/admin/tokens/list")
async def list_admin_tokens_endpoint(
    authorized: bool = Depends(verify_admin),
):
    """List all active admin tokens."""
    from core.admin_tokens import list_active_admin_tokens

    tokens = list_active_admin_tokens()
    return {
        "status": "success",
        "tokens": [
            {
                "token_id": token.token_id,
                "subject": token.subject,
                "scope": token.scope,
                "expires_at": token.expires_at.isoformat(),
                "created_at": token.created_at.isoformat(),
                "revoked_at": token.revoked_at.isoformat() if token.revoked_at else None,
                "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
                "is_active": token.is_active,
            }
            for token in tokens
        ],
        "count": len(tokens),
    }


@router.post("/admin/tokens/cleanup")
async def cleanup_expired_tokens_endpoint(
    authorized: bool = Depends(verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """Clean up expired admin tokens."""
    from core.admin_tokens import cleanup_expired_tokens

    count = cleanup_expired_tokens()
    return {"status": "success", "message": f"Cleaned up {count} expired tokens", "cleaned_count": count}


@router.get("/admin/db/health")
async def get_database_health_endpoint(authorized: bool = Depends(verify_admin)):
    """Get comprehensive database health information."""
    health = get_database_health()
    return {"status": "success", "database_health": health}


@router.get("/admin/db/pool")
async def get_db_pool_health_endpoint(authorized: bool = Depends(verify_admin)):
    """Get database connection pool health."""
    health = check_db_pool_health()
    return {"status": "success", "pool_health": health}


@router.get("/admin/db/pool/stats")
async def get_db_pool_stats_endpoint(authorized: bool = Depends(verify_admin)):
    """Get detailed database connection pool statistics."""
    stats = get_current_pool_stats()
    if stats:
        return {
            "status": "success",
            "stats": {
                "current_connections": stats.current_connections,
                "max_connections": stats.max_connections,
                "idle_connections": stats.idle_connections,
                "waiting_requests": stats.waiting_requests,
                "utilization": round(stats.utilization, 3),
                "queue_size": stats.queue_size,
                "is_healthy": stats.is_healthy(),
                "is_critical": stats.is_critical(),
            },
        }
    else:
        return {"status": "error", "message": "Unable to retrieve pool statistics"}


@router.get("/admin/queues/health")
async def get_queue_health_endpoint(authorized: bool = Depends(verify_admin)):
    """Get comprehensive queue health information."""
    health = get_queue_health()
    return {"status": "success", "queue_health": health}


@router.get("/admin/queues/status")
async def get_queue_status_endpoint(authorized: bool = Depends(verify_admin)):
    """Get current queue status."""
    status = check_queue_health()
    return {"status": "success", "queue_status": status}


@router.get("/admin/queues/stats")
async def get_queue_stats_endpoint(authorized: bool = Depends(verify_admin)):
    """Get detailed queue statistics."""
    stats = get_current_queue_stats()
    return {
        "status": "success",
        "queues": [
            {
                "name": queue.name,
                "active": queue.active,
                "scheduled": queue.scheduled,
                "reserved": queue.reserved,
                "total": queue.total,
                "is_backlogged": queue.is_backlogged(),
                "is_critical": queue.is_critical(),
            }
            for queue in stats
        ],
    }


@router.get("/admin/queues/scaling")
async def get_scaling_recommendation_endpoint(authorized: bool = Depends(verify_admin)):
    """Get worker scaling recommendation."""
    recommendation = get_scaling_recommendation()
    return {"status": "success", "scaling_recommendation": recommendation}


@router.get("/admin/localization/rules")
async def get_localization_rules(authorized: bool = Depends(verify_admin)):
    """Fetches the active dynamic localization and tag normalization rules."""
    from core.localization import localization_engine

    return {"status": "success", "rules": localization_engine.get_rules_dict()}


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
        log.error(f"Failed to update rules: {e}", exc_info=True)
        return soft_error(message="Failed to update rules")
