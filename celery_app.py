import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import logging
from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, worker_process_init

log = logging.getLogger("presek_celery")

@worker_process_init.connect
def reset_db_pool(**kwargs):
    """Ensure each worker process gets a fresh DB connection pool after forking."""
    from database import db_manager
    log.info("[celery] Resetting database connection pool for worker process.")
    db_manager._reset_pool()

@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, **kw):
    """Log permanently failed tasks to Dead Letter Queue (DLQ) in database."""
    log.error(f"[celery-failure] Task {sender.name} (id={task_id}) failed: {exception}")
    try:
        from database import db_manager
        import json
        db_manager.execute("""
            INSERT INTO failed_tasks (task_name, args, kwargs, error_message)
            VALUES (%s, %s::jsonb, %s::jsonb, %s)
        """, (sender.name, json.dumps(args or []), json.dumps(kwargs or {}), str(exception)), fetch=False)
    except Exception as e:
        log.error(f"[celery-dlq] Failed to store task error in DB: {e}")

# Initialize Celery
celery_app = Celery(
    'presek',
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=['tasks']
)

celery_app.conf.update(
    timezone='UTC',
    beat_schedule={
        'ingest-regular-feeds': {
            'task': 'tasks.ingestion_task.run_ingestion',
            'schedule': 1200.0, # Every 20 minutes
        },
        'prune-database': {
            'task': 'tasks.maintenance.run_prune_db',
            'schedule': crontab(hour=3, minute=0), # Daily maintenance
        },
        'generate-daily-briefing': {
            'task': 'tasks.delivery.generate_daily_brief_task',
            'schedule': crontab(hour=6, minute=0), # 6 AM UTC / 7 AM local
        },
        'send-daily-digest': {
            'task': 'tasks.delivery.send_daily_digest_task',
            'schedule': crontab(hour=7, minute=0), # 7 AM UTC / 8 AM local
        },
        'send-daily-newsletter': {
            'task': 'tasks.delivery.send_newsletter_task',
            'schedule': crontab(hour=7, minute=0), # 7 AM UTC / 8 AM local
        },

        'send-profile-briefings': {
            'task': 'tasks.delivery.send_profile_briefings_task',
            'schedule': crontab(hour=7, minute=10),
        },
        'send-profile-weekly-digests': {
            'task': 'tasks.delivery.send_profile_weekly_digests_task',
            'schedule': crontab(hour=8, minute=0, day_of_week='sun'),
        },
        'send-profile-breaking-alerts': {
            'task': 'tasks.delivery.send_profile_breaking_alerts_task',
            'schedule': 180.0,
        },
        'backfill-cover-art': {
            'task': 'tasks.intelligence.backfill_cover_art_task',
            'schedule': 1800.0,  # Every 30 minutes
        },
        'auto-repair-sources': {
            'task': 'tasks.ingestion_task.auto_repair_sources_task',
            'schedule': crontab(hour='*/6', minute=30), # Every 6 hours
        },
        'discover-storylines': {
            'task': 'tasks.intelligence.discover_storylines_task',
            'schedule': crontab(minute='15', hour='*/2'), # Every 2 hours
        },
        'validate-cluster-images': {
            'task': 'tasks.maintenance.validate_cluster_images_task',
            'schedule': 3600.0, # Every hour
        },
    }
)
