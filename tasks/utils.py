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
    delete_cache("api:trending")


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
        # Use both the raw prefix and the API prefix to be safe
        delete_cache(f"cluster:detail:{cluster_id}")
        delete_cache(f"api:cluster:detail:v2:{cluster_id}")
    invalidate_public_data_caches()


def get_celery_queue_depth(queue_name="celery"):
    try:
        return int(redis_client.llen(queue_name) or 0)
    except Exception as e:
        log.debug(f"Failed to get queue depth for {queue_name}: {e}")
        return 0


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
