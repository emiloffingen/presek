import asyncio
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.logging_config import get_logger
from utils import delete_cache, delete_cache_prefix, redis_client  # noqa: F401

log = get_logger("presek_celery")


def send_email(
    html: str,
    subject: str,
    smtp_user: str,
    smtp_pass: str,
    to_address: str,
    smtp_host: str = None,
    smtp_port: int = None,
) -> bool:
    """Send HTML email via SMTP."""
    host = smtp_host or os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(smtp_port or os.environ.get("SMTP_PORT", 587))
    from_addr = os.environ.get("EMAIL_FROM", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_address
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_address, msg.as_string())
        log.info(f"Email sent to {to_address} via {host}")
        return True
    except Exception as e:
        log.warning(f"SMTP error on {host}: {e}")
        return False


_PUBLIC_SITE_URL = str(os.environ.get("PUBLIC_SITE_URL") or "https://presek.live").rstrip("/")


def invalidate_public_data_caches():
    delete_cache_prefix("api:news:")
    delete_cache_prefix("api:home:")
    delete_cache_prefix("api:intelligence:")
    delete_cache_prefix("api:top-entities:")
    delete_cache_prefix("api:stats:summary:")
    delete_cache_prefix("stats:intel_summary:")
    delete_cache_prefix("api:trending:")


def safe_async_run(coro):
    """Helper to run a coroutine safely across different execution environments (Celery, scripts)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def invalidate_cluster_caches(cluster_id=None):
    if cluster_id:
        delete_cache(f"cluster:detail:{cluster_id}")
        delete_cache_prefix(f"api:cluster:detail:v3:{cluster_id}")
    invalidate_public_data_caches()


def get_celery_queue_depth(queue_name="celery"):
    try:
        if queue_name != "celery":
            return int(redis_client.llen(queue_name) or 0)

        from core.health import MONITORED_CELERY_QUEUES

        depths = [int(redis_client.llen(name) or 0) for name in MONITORED_CELERY_QUEUES]
        return max(depths) if depths else 0
    except Exception as e:
        log.debug(f"Failed to get queue depth for {queue_name}: {e}")
        return 0


INTEL_QUEUE_NAME = "intel-heavy"
INTEL_PRIORITY_TASKS = frozenset(
    {
        "tasks.intelligence.summarize_articles_batch_task",
        "tasks.intelligence.summarize_articles_local_batch_task",
        "tasks.intelligence.summarize_article_task",
    }
)
INTEL_DEFERRABLE_TASKS = frozenset(
    {
        "tasks.intelligence.detect_global_stories_batch_task",
        "tasks.intelligence.standardize_article_styles_batch_task",
        "tasks.intelligence.backfill_cluster_summaries_task",
        "tasks.intelligence.classify_topics_task",
        "tasks.intelligence.recategorize_clusters_task",
        "tasks.intelligence.recluster_recent_articles_task",
        "tasks.intelligence.refine_knowledge_graph_sentiment_task",
        "tasks.intelligence.backfill_cover_art_task",
        "tasks.intelligence.repair_split_clusters_task",
        "tasks.intelligence.extract_entities_task",
        "tasks.intelligence.discover_storylines_task",
        "tasks.intelligence.detect_global_story_task",
        "tasks.intelligence.standardize_article_style_task",
    }
)


def _parse_queue_task_name(raw_message: str) -> str:
    import json

    body = json.loads(raw_message)
    return str((body.get("headers") or {}).get("task") or "")


def reprioritize_intel_queue(*, defer_threshold: int = 150, dry_run: bool = False) -> dict:
    """Drop deferrable intel-heavy tasks and move summarize batches to the queue head."""
    depth_before = get_celery_queue_depth(INTEL_QUEUE_NAME)
    if depth_before < defer_threshold:
        return {
            "skipped": True,
            "reason": "below_threshold",
            "depth_before": depth_before,
            "defer_threshold": defer_threshold,
        }

    raw_items = redis_client.lrange(INTEL_QUEUE_NAME, 0, -1) or []
    priority_items = []
    kept_other = []
    removed = 0

    for raw in raw_items:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        task_name = _parse_queue_task_name(raw)
        if task_name in INTEL_PRIORITY_TASKS:
            priority_items.append(raw)
        elif task_name in INTEL_DEFERRABLE_TASKS:
            removed += 1
        else:
            kept_other.append(raw)

    rebuilt = priority_items + kept_other
    result = {
        "skipped": False,
        "depth_before": depth_before,
        "depth_after": len(rebuilt),
        "removed": removed,
        "priority_count": len(priority_items),
        "kept_other_count": len(kept_other),
        "dry_run": dry_run,
    }

    if dry_run:
        return result

    pipe = redis_client.pipeline()
    pipe.delete(INTEL_QUEUE_NAME)
    if rebuilt:
        pipe.rpush(INTEL_QUEUE_NAME, *rebuilt)
    pipe.execute()
    result["depth_after"] = get_celery_queue_depth(INTEL_QUEUE_NAME)
    return result


def schedule_task_once(lock_key: str, ttl_seconds: int, task, *, args=None, kwargs=None, countdown=0) -> bool:
    """Schedule a Celery task only if no matching lock is already held."""
    if not acquire_task_lock(lock_key, ttl_seconds):
        return False
    task.apply_async(args=args or (), kwargs=kwargs or {}, countdown=max(0, int(countdown)))
    return True


def acquire_task_lock(lock_key: str, ttl_seconds: int = 300) -> bool:
    try:
        return bool(redis_client.set(lock_key, "1", ex=int(ttl_seconds), nx=True))
    except Exception as e:
        log.debug(f"Failed to acquire lock {lock_key}: {e}")
        return True


def release_task_lock(lock_key: str):
    try:
        redis_client.delete(lock_key)
    except Exception as e:
        log.debug(f"Failed to release lock {lock_key}: {e}")


def record_runtime_event(event: str, **fields):
    """Bridge to the main record_runtime_event in utils."""
    from utils import record_runtime_event as _record

    _record(event, **fields)


_TASK_REDIS_KEY = "presek:task_statuses"


def record_task_event(task_name: str, status: str, detail: str | None = None):
    from core.health import record_task_event as _record

    return _record(task_name, status, detail)
