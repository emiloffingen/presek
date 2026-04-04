import os
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
    """Log permanently failed tasks for monitoring."""
    log.error(f"[celery-failure] Task {sender.name} (id={task_id}) permanently failed: {exception}")

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
            'task': 'tasks.run_ingestion',
            'schedule': 300.0, # Every 5 minutes: Entry point for unified pipeline
        },
        'prune-database': {
            'task': 'tasks.run_prune_db',
            'schedule': crontab(hour=3, minute=0), # Daily maintenance
        },
        'generate-daily-briefing': {
            'task': 'tasks.generate_daily_brief_task',
            'schedule': crontab(hour=6, minute=0), # 6 AM UTC / 7 AM local
        },
        'send-daily-digest': {
            'task': 'tasks.send_daily_digest_task',
            'schedule': crontab(hour=7, minute=0), # 7 AM UTC / 8 AM local
        },
        'send-telegram-briefing': {
            'task': 'tasks.send_telegram_briefing_task',
            'schedule': crontab(hour=7, minute=5), # 7:05 AM UTC / 8:05 AM local
        },
        'backfill-cover-art': {
            'task': 'tasks.backfill_cover_art_task',
            'schedule': 600.0,  # Every 10 minutes: cover art generator
        },
    }
)