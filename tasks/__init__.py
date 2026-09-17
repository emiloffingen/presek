# Explicit imports from each module
from tasks.delivery import (
    send_daily_digest_task,
    send_newsletter_task,
)
from tasks.ingestion_task import auto_repair_sources_task, crawl_article_task, run_ingestion
from tasks.maintenance import run_prune_db

# Explicitly re-export for clarity and auto-discovery
__all__ = [
    "crawl_article_task",
    "run_ingestion",
    "auto_repair_sources_task",
    "send_daily_digest_task",
    "send_newsletter_task",
    "run_prune_db",
]
