import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Redis 8 / redis-py 8 compatibility patch
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

    except Exception as e:
        log.error(f"[celery-dlq] Failed to store task error in DB: {e}")


# Initialize Celery
celery_app = Celery(
    "presek",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        "tasks.ingestion_task",
        "tasks.summarization",
        "tasks.delivery",
        "tasks.maintenance",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    task_default_queue="celery",
    task_queues=(
        Queue("celery", routing_key="celery"),
        Queue("ingestion", routing_key="ingestion"),
        Queue("ingestion-crawl", routing_key="ingestion-crawl"),
        Queue("summarization", routing_key="summarization"),
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
        "tasks.summarization.*": {"queue": "summarization"},
        "tasks.delivery.email.*": {"queue": "delivery"},
        "tasks.delivery.*": {"queue": "delivery"},
        "tasks.maintenance.*": {"queue": "maintenance"},
    },
    beat_schedule={
        "ingest-regular-feeds": {
            "task": "tasks.ingestion_task.run_ingestion",
            "schedule": 600.0,  # Every 10 minutes
            "options": {"expires": 540},
        },
        "auto-summarize-clusters": {
            "task": "tasks.summarization.auto_summarize_task",
            "schedule": 900.0,  # Every 15 minutes
        },
        "prune-database": {
            "task": "tasks.maintenance.run_prune_db",
            "schedule": crontab(hour=3, minute=0),  # Daily maintenance
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
        "auto-repair-sources": {
            "task": "tasks.ingestion_task.auto_repair_sources_task",
            "schedule": crontab(hour="*/6", minute=30),  # Every 6 hours
        },
        "send-daily-digest": {
            "task": "tasks.delivery.email.send_daily_digest_task",
            "schedule": crontab(hour=7, minute=0),  # 7 AM UTC / 8 AM local
        },
        "send-daily-newsletter": {
            "task": "tasks.delivery.email.send_newsletter_task",
            "schedule": crontab(hour=7, minute=0),  # 7 AM UTC / 8 AM local
        },
    },
    # Task-specific rate limits
    task_annotations={
        "tasks.ingestion_task.crawl_article_task": {"rate_limit": "100/m"},
    },
    # Worker prefetch multiplier - reduce from default 4 to 1
    worker_prefetch_multiplier=1,
    # Disable result persistence for tasks that don't need it
    result_expires=3600,  # Results expire after 1 hour
    # Default when workers omit --concurrency
    worker_concurrency=int(os.environ.get("CELERY_WORKER_CONCURRENCY", "2")),
)

# Setup logging for Celery workers
from core.logging_config import setup_logging

setup_logging()
