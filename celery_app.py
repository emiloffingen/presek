import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, worker_process_init
from kombu import Queue

from logging_config import get_logger

log = get_logger("presek_celery")


@worker_process_init.connect
def reset_db_pool(**kwargs):
    """Ensure each worker process gets fresh DB connection pools after forking."""
    from database import db_manager, async_db

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
        from database import db_manager
        import json

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
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks to prevent memory leaks
    task_default_rate_limit="100/m",  # Global rate limit: 100 tasks per minute
    task_queues=(
        Queue("celery"),
        Queue("ingestion"),
        Queue("fast-track"),
        Queue("intel-heavy"),
        Queue("delivery"),
        Queue("maintenance"),
    ),
    task_routes={
        "tasks.ingestion_task.run_ingestion": {"queue": "ingestion"},
        "tasks.ingestion_task.auto_repair_sources_task": {"queue": "maintenance"},
        "tasks.ingestion_task.crawl_article_task": {"queue": "ingestion"},
        "tasks.intelligence.synthesize_cluster_task": {"queue": "fast-track"},
        "tasks.intelligence.auto_summarize_task": {"queue": "fast-track"},
        "tasks.intelligence.*": {"queue": "intel-heavy"},
        "tasks.delivery.send_profile_breaking_alerts_task": {"queue": "fast-track"},
        "tasks.delivery.*": {"queue": "delivery"},
        "tasks.maintenance.*": {"queue": "maintenance"},
    },
    beat_schedule={
        "ingest-regular-feeds": {
            "task": "tasks.ingestion_task.run_ingestion",
            "schedule": 120.0,  # Every 2 minutes
        },
        "auto-summarize-clusters": {
            "task": "tasks.intelligence.auto_summarize_task",
            "schedule": 180.0,  # Every 3 minutes
        },
        "recluster-recent-articles": {
            "task": "tasks.intelligence.recluster_recent_articles_task",
            "schedule": 300.0,  # Every 5 minutes
        },
        "prune-database": {
            "task": "tasks.maintenance.run_prune_db",
            "schedule": crontab(hour=3, minute=0),  # Daily maintenance
        },
        "generate-daily-briefing-sr": {
            "task": "tasks.delivery.generate_daily_brief_task",
            "kwargs": {"lang": "sr"},
            "schedule": crontab(hour="6,12,18", minute=0),
        },
        "generate-daily-briefing-mk": {
            "task": "tasks.delivery.generate_daily_brief_task",
            "kwargs": {"lang": "mk"},
            "schedule": crontab(hour="6,12,18", minute=5),
        },
        "send-daily-digest": {
            "task": "tasks.delivery.send_daily_digest_task",
            "schedule": crontab(hour=7, minute=0),  # 7 AM UTC / 8 AM local
        },
        "send-daily-newsletter": {
            "task": "tasks.delivery.send_newsletter_task",
            "schedule": crontab(hour=7, minute=0),  # 7 AM UTC / 8 AM local
        },
        "send-profile-briefings": {
            "task": "tasks.delivery.send_profile_briefings_task",
            "schedule": crontab(hour=7, minute=10),
        },
        "send-profile-weekly-digests": {
            "task": "tasks.delivery.send_profile_weekly_digests_task",
            "schedule": crontab(hour=8, minute=0, day_of_week="sun"),
        },
        "send-profile-breaking-alerts": {
            "task": "tasks.delivery.send_profile_breaking_alerts_task",
            "schedule": 180.0,
        },
        "backfill-cover-art": {
            "task": "tasks.intelligence.backfill_cover_art_task",
            "schedule": 1800.0,  # Every 30 minutes
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
    },
    # Worker prefetch multiplier - reduce from default 4 to 1 to prevent memory over-commitment
    worker_prefetch_multiplier=1,
    # Disable result persistence for tasks that don't need it (reduces memory/RPC overhead)
    result_expires=3600,  # Results expire after 1 hour
    # Concurrent task execution limits per worker
    worker_concurrency=4,  # Increased from 2 to allow more parallel processing
)

# Setup logging for Celery workers
from logging_config import setup_logging

setup_logging()
