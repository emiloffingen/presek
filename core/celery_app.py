import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, worker_process_init
from kombu import Queue

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
        Queue("fast-track", routing_key="fast-track"),
        Queue("intel-heavy", routing_key="intel-heavy"),
        Queue("delivery", routing_key="delivery"),
        Queue("maintenance", routing_key="maintenance"),
    ),
    task_routes={
        "tasks.ingestion_task.run_ingestion": {"queue": "ingestion"},
        "tasks.ingestion_task.auto_repair_sources_task": {"queue": "maintenance"},
        "tasks.ingestion_task.repair_single_source_task": {"queue": "maintenance"},
        "tasks.ingestion_task.crawl_article_task": {"queue": "ingestion"},
        "tasks.ingestion_task.process_article_image_task": {"queue": "ingestion"},
        "tasks.ingestion_task.post_crawl_invalidation_task": {"queue": "ingestion"},
        "tasks.intelligence.synthesize_cluster_task": {"queue": "fast-track"},
        "tasks.intelligence.auto_summarize_task": {"queue": "fast-track"},
        "tasks.intelligence.refresh_cluster_centroid_task": {"queue": "maintenance"},
        "tasks.intelligence.generate_embeddings_task": {"queue": "maintenance"},
        "tasks.intelligence.generate_cluster_metadata_task": {"queue": "maintenance"},
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
        },
        "auto-summarize-clusters": {
            "task": "tasks.intelligence.auto_summarize_task",
            "schedule": 900.0,  # Increased from 3m to 15m
        },
        "recluster-recent-articles": {
            "task": "tasks.intelligence.recluster_recent_articles_task",
            "schedule": 1800.0,  # Increased from 5m to 30m
        },
        "repair-split-clusters": {
            "task": "tasks.intelligence.repair_split_clusters_task",
            "schedule": 3600.0,  # Cluster-level duplicate merge after metadata catches up
        },
        "refine-knowledge-graph-sentiment": {
            "task": "tasks.intelligence.refine_knowledge_graph_sentiment_task",
            "schedule": 1800.0,  # Every 30 minutes
        },
        "backfill-cluster-summaries-sr": {
            "task": "tasks.intelligence.schedule_backfill_cluster_summaries_task",
            "kwargs": {"lang": "sr"},
            "schedule": crontab(hour="*/6"),  # Every 6 hours for Serbian
        },
        "backfill-cluster-summaries-mk": {
            "task": "tasks.intelligence.schedule_backfill_cluster_summaries_task",
            "kwargs": {"lang": "mk"},
            "schedule": crontab(hour="*/6"),  # Every 6 hours for Macedonian
        },
        "prune-database": {
            "task": "tasks.maintenance.run_prune_db",
            "schedule": crontab(hour=3, minute=0),  # Daily maintenance
        },
        "prune-intel-queue": {
            "task": "tasks.maintenance.prune_intel_queue_task",
            "schedule": 900.0,  # Every 15 minutes
        },
        "refresh-synthesis-quality": {
            "task": "tasks.maintenance.refresh_synthesis_quality_task",
            "schedule": 900.0,  # Every 15 minutes
        },
        "catch-up-recent-summaries": {
            "task": "tasks.maintenance.catch_up_recent_summaries_task",
            "schedule": 1800.0,  # Every 30 minutes
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
            "task": "tasks.intelligence.backfill_cover_art_task",
            "schedule": 3600.0,  # Increased from 30m to 1h
        },
        "auto-repair-sources": {
            "task": "tasks.ingestion_task.auto_repair_sources_task",
            "schedule": crontab(hour="*/6", minute=30),  # Every 6 hours
        },
        "discover-storylines": {
            "task": "tasks.intelligence.discover_storylines_task",
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
            "soft_time_limit": 600,
            "time_limit": 900,
        },
    },
    # Worker prefetch multiplier - reduce from default 4 to 1 to prevent memory over-commitment
    worker_prefetch_multiplier=1,
    # Disable result persistence for tasks that don't need it (reduces memory/RPC overhead)
    result_expires=3600,  # Results expire after 1 hour
    # Default when workers omit --concurrency (production units set this explicitly).
    worker_concurrency=int(os.environ.get("CELERY_WORKER_CONCURRENCY", "4")),
)

# Setup logging for Celery workers
from core.logging_config import setup_logging

setup_logging()
