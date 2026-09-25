import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Redis 8 / redis-py 8 compatibility patch
# redis-py 8.0 defaults to RESP3 and requires the HELLO command to carry
# AUTH credentials simultaneously.  kombu 5.6 builds a ConnectionPool via
# redis.ConnectionPool(**params) without a `protocol` kwarg, so the pool
# defaults to RESP3 and hits "HELLO must be called with the client already
# authenticated" on startup.  We patch _get_pool to inject protocol=2
# (RESP2) before the pool is constructed.  This must happen before the
# `Celery(broker=...)` call below.
# ---------------------------------------------------------------------------
import redis as _redis
import kombu.transport.redis as _kombu_redis

_orig_get_pool = _kombu_redis.Channel._get_pool


def _resp2_get_pool(self, asynchronous=False):
    params = self._connparams(asynchronous=asynchronous)
    params.setdefault("protocol", 2)
    return _redis.ConnectionPool(**params)


_kombu_redis.Channel._get_pool = _resp2_get_pool
# ---------------------------------------------------------------------------

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, worker_process_init
from kombu import Queue

from core.config import (
    HOMEPAGE_SYNTHESIS_PRIORITIZE_INTERVAL_SECONDS,
    HOMEPAGE_SYNTHESIS_PRIORITIZE_LIMIT,
)
from core.logging_config import get_logger

log = get_logger("presek_celery")


@worker_process_init.connect
def reset_db_pool(**kwargs):
    """Ensure each worker process gets fresh DB connection pools after forking."""
    from core.database import async_db, db_manager

    log.info(
        "Resetting database connection pools for worker process",
        extra={"action": "worker_init"},
    )
    db_manager._reset_pool()
    async_db._reset_pool()


@task_failure.connect
def on_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    **kw,
):
    """Log permanently failed tasks to Dead Letter Queue (DLQ) in database."""
    log.error(
        "Task failed",
        extra={
            "task_name": sender.name,
            "task_id": task_id,
            "exception": str(exception),
            "action": "task_failure",
        },
    )
    try:
        import json

        from core.database import db_manager

        db_manager.execute(
            """
            INSERT INTO failed_tasks (task_name, args, kwargs, error_message)
            VALUES (%s, %s::jsonb, %s::jsonb, %s)
        """,
            (
                sender.name,
                json.dumps(args or []),
                json.dumps(kwargs or {}),
                str(exception),
            ),
            fetch=False,
        )

        # Proactively check and log the recent failure context
        from scripts.monitor_errors import check_failed_tasks

        check_failed_tasks()

    except Exception as e:
        log.error(f"[celery-dlq] Failed to store task error in DB: {e}")


# Initialize Celery
celery_app = Celery(
    "presek",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        "tasks.ingestion_task",
        "tasks.intelligence",
        "tasks.summarization",
        "tasks.extractive_maintenance",
        "tasks.delivery",
        "tasks.maintenance",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    task_default_queue="celery",
    # Memory protection: restart workers after processing N tasks or M memory
    worker_max_memory_per_child=2_000_000,  # 2GB memory limit per worker process
    worker_max_tasks_per_child=1000,  # Increased from 100 to 1000 to minimize model reload overhead
    task_default_rate_limit="100/m",  # Global rate limit: 100 tasks per minute
    task_queues=(
        Queue("celery", routing_key="celery"),
        Queue("ingestion", routing_key="ingestion"),
        Queue("ingestion-crawl", routing_key="ingestion-crawl"),
        Queue("fast-track", routing_key="fast-track"),
        Queue("synthesis", routing_key="synthesis"),
        Queue("intel-heavy", routing_key="intel-heavy"),
        Queue("delivery", routing_key="delivery"),
        Queue("maintenance", routing_key="maintenance"),
    ),
    task_routes={
        "tasks.ingestion_task.run_ingestion": {"queue": "ingestion"},
        "tasks.ingestion_task.auto_repair_sources_task": {"queue": "maintenance"},
        "tasks.ingestion_task.repair_single_source_task": {"queue": "maintenance"},
        "tasks.ingestion_task.crawl_article_task": {"queue": "ingestion-crawl"},
        "tasks.ingestion_task.process_article_image_task": {"queue": "ingestion-crawl"},
        "tasks.ingestion_task.post_crawl_invalidation_task": {"queue": "ingestion-crawl"},
        "tasks.intelligence.synthesize_cluster_task": {"queue": "synthesis"},
        "tasks.intelligence.synthesize_urgent_task": {"queue": "fast-track"},
        "tasks.intelligence.auto_summarize_task": {"queue": "fast-track"},
        "tasks.intelligence.refresh_cluster_centroid_task": {"queue": "maintenance"},
        "tasks.intelligence.generate_embeddings_task": {"queue": "maintenance"},
        "tasks.intelligence.generate_cluster_metadata_task": {"queue": "maintenance"},
        "tasks.intelligence.upgrade_fast_synthesis_task": {"queue": "synthesis"},
        "tasks.intelligence.*": {"queue": "intel-heavy"},
        "tasks.delivery.briefing.send_profile_breaking_alerts_task": {"queue": "fast-track"},
        "tasks.delivery.email.*": {"queue": "delivery"},
        "tasks.delivery.briefing.*": {"queue": "delivery"},
        "tasks.delivery.*": {"queue": "delivery"},
        "tasks.maintenance.*": {"queue": "maintenance"},
    },
    beat_schedule={
        "ingest-regular-feeds": {
            "task": "tasks.ingestion_task.run_ingestion",
            "schedule": 600.0,  # Increased from 2m to 10m
            "options": {"expires": 540},
        },
        "auto-summarize-clusters": {
            "task": "tasks.intelligence.auto_summarize_task",
            "schedule": 900.0,  # Increased from 3m to 15m
        },
        "build-extractive-overviews": {
            # Deterministic, LLM-free cluster overviews (AI kill-switch path).
            "task": "tasks.summarization.build_extractive_clusters_task",
            "schedule": 600.0,  # Every 10 minutes
            "options": {"expires": 540},
        },
        "recluster-recent-articles": {
            "task": "tasks.extractive.recluster_recent_articles_task",
            "schedule": 1200.0,
        },
        "repair-split-clusters": {
            "task": "tasks.extractive.repair_split_clusters_task",
            "schedule": 1800.0,
        },
        "refine-knowledge-graph-sentiment": {
            "task": "tasks.extractive.refine_knowledge_graph_sentiment_task",
            "schedule": 1800.0,  # Every 30 minutes
        },
        "backfill-cluster-summaries-sr": {
            "task": "tasks.extractive.schedule_backfill_cluster_summaries_task",
            "kwargs": {"lang": "sr"},
            "schedule": crontab(hour="*/6"),  # Every 6 hours for Serbian
        },
        "backfill-cluster-summaries-mk": {
            "task": "tasks.extractive.schedule_backfill_cluster_summaries_task",
            "kwargs": {"lang": "mk"},
            "schedule": crontab(hour="*/6"),  # Every 6 hours for Macedonian
        },
        "prune-database": {
            "task": "tasks.maintenance.run_prune_db",
            "schedule": crontab(hour=3, minute=0),  # Daily maintenance
        },
        "prune-intel-queue": {
            "task": "tasks.maintenance.prune_intel_queue_task",
            "schedule": 600.0,  # Every 10 minutes
            "options": {"expires": 540},
        },
        "prune-fast-track-queue": {
            "task": "tasks.maintenance.prune_fast_track_queue_task",
            "schedule": 600.0,
            "options": {"expires": 540},
        },
        "prune-maintenance-queue": {
            "task": "tasks.maintenance.prune_maintenance_queue_task",
            "schedule": 900.0,
            "options": {"expires": 810},
        },
        "refresh-synthesis-quality": {
            "task": "tasks.maintenance.refresh_synthesis_quality_task",
            "schedule": 900.0,  # Every 15 minutes
            "options": {"expires": 810},
        },
        "upgrade-stuck-fast-syntheses": {
            "task": "tasks.maintenance.upgrade_stuck_fast_syntheses_task",
            "schedule": 1800.0,  # Every 30 minutes
            "options": {"expires": 1620},
        },
        "refresh-fallback-syntheses": {
            "task": "tasks.maintenance.refresh_fallback_syntheses_task",
            "schedule": 3600.0,  # Every hour
            "options": {"expires": 3300},
        },
        "catch-up-recent-summaries": {
            "task": "tasks.maintenance.catch_up_recent_summaries_task",
            "schedule": 1800.0,  # Every 30 minutes
            "options": {"expires": 1620},
        },
        "catch-up-cluster-syntheses": {
            "task": "tasks.maintenance.catch_up_cluster_syntheses_task",
            "schedule": 1800.0,
            "options": {"expires": 1620},
        },
        "prioritize-homepage-syntheses": {
            "task": "tasks.maintenance.prioritize_homepage_syntheses_task",
            "schedule": HOMEPAGE_SYNTHESIS_PRIORITIZE_INTERVAL_SECONDS,
            "kwargs": {"limit": HOMEPAGE_SYNTHESIS_PRIORITIZE_LIMIT},
            "options": {"expires": max(60, HOMEPAGE_SYNTHESIS_PRIORITIZE_INTERVAL_SECONDS - 30)},
        },
        "boost-homepage-cluster-supply": {
            "task": "tasks.maintenance.boost_homepage_cluster_supply_task",
            "schedule": 1800.0,
            "options": {"expires": 1620},
        },
        "refresh-low-score-syntheses": {
            "task": "tasks.maintenance.refresh_low_score_syntheses_task",
            "schedule": 3600.0,
            "options": {"expires": 3300},
        },
        "prune-ingestion-queue": {
            "task": "tasks.maintenance.prune_ingestion_queue_task",
            "schedule": 900.0,
            "options": {"expires": 810},
        },
        "prune-crawl-queue": {
            "task": "tasks.maintenance.prune_crawl_queue_task",
            "schedule": 900.0,
            "options": {"expires": 810},
        },
        "catch-up-deferred-crawls": {
            "task": "tasks.maintenance.catch_up_deferred_crawls_task",
            "schedule": 1800.0,
            "options": {"expires": 1620},
        },
        "ensure-ingestion-freshness": {
            "task": "tasks.maintenance.ensure_ingestion_freshness_task",
            "schedule": 900.0,
            "options": {"expires": 810},
        },
        "backfill-historical-summaries": {
            "task": "tasks.extractive.schedule_backfill_historical_summaries_task",
            "schedule": 1800.0,  # Every 30 minutes, Gemma-only
        },
        "generate-daily-briefing-sr": {
            "task": "tasks.delivery.briefing.generate_daily_brief_task",
            "kwargs": {"lang": "sr"},
            "schedule": crontab(hour=6, minute=0),
        },
        "generate-daily-briefing-mk": {
            "task": "tasks.delivery.briefing.generate_daily_brief_task",
            "kwargs": {"lang": "mk"},
            "schedule": crontab(hour=6, minute=5),
        },
        "send-daily-digest": {
            "task": "tasks.delivery.email.send_daily_digest_task",
            "schedule": crontab(hour=7, minute=0),  # 7 AM UTC / 8 AM local
        },
        "send-daily-newsletter": {
            "task": "tasks.delivery.email.send_newsletter_task",
            "schedule": crontab(hour=7, minute=0),  # 7 AM UTC / 8 AM local
        },
        "send-profile-briefings": {
            "task": "tasks.delivery.briefing.send_profile_briefings_task",
            "schedule": crontab(hour=7, minute=10),
        },
        "send-profile-weekly-digests": {
            "task": "tasks.delivery.email.send_profile_weekly_digests_task",
            "schedule": crontab(hour=8, minute=0, day_of_week="sun"),
        },
        "send-profile-breaking-alerts": {
            "task": "tasks.delivery.briefing.send_profile_breaking_alerts_task",
            "schedule": 600.0,  # Increased from 3m to 10m
        },
        "backfill-cover-art": {
            "task": "tasks.extractive.backfill_cover_art_task",
            "schedule": 3600.0,  # Increased from 30m to 1h
        },
        "auto-repair-sources": {
            "task": "tasks.ingestion_task.auto_repair_sources_task",
            "schedule": crontab(hour="*/6", minute=30),  # Every 6 hours
        },
        "discover-storylines": {
            "task": "tasks.extractive.discover_storylines_task",
            "schedule": crontab(minute="15", hour="*/2"),  # Every 2 hours
        },
        "validate-cluster-images": {
            "task": "tasks.maintenance.validate_cluster_images_task",
            "schedule": 3600.0,  # Every hour
        },
        "repair-knowledge-graph": {
            "task": "tasks.maintenance.repair_knowledge_graph_task",
            "schedule": crontab(hour=4, minute=0),  # Daily at 4 AM UTC
        },
    },
    # Task-specific rate limits
    task_annotations={
        "tasks.ingestion_task.crawl_article_task": {"rate_limit": "100/m"},
        "tasks.intelligence.generate_embeddings_task": {"rate_limit": "30/m"},
        "tasks.intelligence.generate_cluster_metadata_task": {
            "rate_limit": "30/m",
            "soft_time_limit": 600,
            "time_limit": 900,
        },
        "tasks.intelligence.backfill_cluster_summaries_task": {
            # No rate_limit: backlog gating handles load; a low limit blocks prefetch slots
            # and stalls the entire intel-heavy worker when many chained backfills exist.
            "soft_time_limit": 900,
            "time_limit": 1200,
        },
        "tasks.intelligence.summarize_articles_batch_task": {
            "soft_time_limit": 600,
            "time_limit": 900,
        },
        "tasks.intelligence.synthesize_cluster_task": {
            "soft_time_limit": 1500,
            "time_limit": 1800,
        },
        "tasks.intelligence.upgrade_fast_synthesis_task": {
            "soft_time_limit": 1500,
            "time_limit": 1800,
        },
    },
    # Worker prefetch multiplier - reduce from default 4 to 1 to prevent memory over-commitment
    worker_prefetch_multiplier=1,
    # Disable result persistence for tasks that don't need it (reduces memory/RPC overhead)
    result_expires=3600,  # Results expire after 1 hour
    # Default when workers omit --concurrency (production units set this explicitly).
    worker_concurrency=int(os.environ.get("CELERY_WORKER_CONCURRENCY", "4")),
)

# The Android MK-only deployment uses deterministic clustering and ingestion.
# Keep expensive synthesis, intelligence backfills, and email delivery opt-in
# so a fresh worker does not spend memory on disabled AI paths.
if os.environ.get("ENABLE_AI_SCHEDULES", "false").lower() != "true":
    for _schedule_name in (
        "auto-summarize-clusters",
        "recluster-recent-articles",
        "repair-split-clusters",
        "refine-knowledge-graph-sentiment",
        "backfill-cluster-summaries-sr",
        "backfill-cluster-summaries-mk",
        "backfill-historical-summaries",
        "generate-daily-briefing-sr",
        "generate-daily-briefing-mk",
        "send-daily-digest",
        "send-daily-newsletter",
        "send-profile-briefings",
        "send-profile-weekly-digests",
        "send-profile-breaking-alerts",
        "backfill-cover-art",
        "discover-storylines",
        # Synthesis-quality / homepage-synthesis maintenance: all no-ops or
        # crashing stubs on the MK-only (minimal-AI) deployment.
        "refresh-synthesis-quality",
        "upgrade-stuck-fast-syntheses",
        "refresh-fallback-syntheses",
        "refresh-low-score-syntheses",
        "catch-up-recent-summaries",
        "catch-up-cluster-syntheses",
        "prioritize-homepage-syntheses",
        "boost-homepage-cluster-supply",
    ):
        celery_app.conf.beat_schedule.pop(_schedule_name, None)

# Setup logging for Celery workers
from core.logging_config import setup_logging

setup_logging()
