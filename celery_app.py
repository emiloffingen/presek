import os
from celery import Celery
from celery.schedules import crontab

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
            'schedule': 300.0, # Run every 5 minutes
        },
        'prune-database': {
            'task': 'tasks.run_prune_db',
            'schedule': crontab(hour=3, minute=0), # Run daily at 3 AM
        },
        'send-daily-digest': {
            'task': 'tasks.send_daily_digest_task',
            'schedule': crontab(hour=7, minute=0), # Run daily at 7 AM UTC (8 AM local)
        }
    }
)