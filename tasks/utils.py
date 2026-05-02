import os
import json
from datetime import datetime, timezone
import asyncio
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from utils import delete_cache, delete_cache_prefix, redis_client  # noqa: F401
from logging_config import get_logger

log = get_logger("presek_celery")

def send_email(html: str, subject: str,
               smtp_user: str, smtp_pass: str,
               to_address: str,
               smtp_host: str = None,
               smtp_port: int = None) -> bool:
    """Send HTML email via SMTP."""
    host = smtp_host or os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(smtp_port or os.environ.get("SMTP_PORT", 587))
    from_addr = os.environ.get("EMAIL_FROM", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_address
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
    delete_cache_prefix("v4:news:")
    delete_cache_prefix("api:home:")
    delete_cache("ssr:index:top_clusters")
    delete_cache("trending")
    delete_cache("stats:full")

def safe_async_run(coro):
    """Helper to run a coroutine safely across different execution environments (Celery, scripts)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except Exception:
        return asyncio.run(coro)

def invalidate_cluster_caches(cluster_id=None):
    if cluster_id:
        # Use both the raw prefix and the API prefix to be safe
        delete_cache(f"cluster:detail:{cluster_id}")
        delete_cache(f"api:cluster:detail:v2:{cluster_id}")
    invalidate_public_data_caches()

def get_celery_queue_depth(queue_name="celery"):
    try:
        return int(redis_client.llen(queue_name) or 0)
    except Exception:
        return 0

def acquire_task_lock(lock_key: str, ttl_seconds: int = 300) -> bool:
    try:
        return bool(redis_client.set(lock_key, "1", ex=int(ttl_seconds), nx=True))
    except Exception:
        return True

def release_task_lock(lock_key: str):
    try:
        redis_client.delete(lock_key)
    except Exception:
        pass

def record_runtime_event(event: str, **fields):
    """Bridge to the main record_runtime_event in utils."""
    from utils import record_runtime_event as _record
    _record(event, **fields)

_TASK_REDIS_KEY = "presek:task_statuses"

def record_task_event(task_name: str, status: str, detail: str | None = None):
    """Persist a lightweight task-status event for operational visibility."""
    if not task_name or not status:
        return

    payload = {
        "task": task_name,
        "status": status,
        "detail": detail or "",
        "time": datetime.now(timezone.utc).isoformat(),
    }
    try:
        redis_client.hset(_TASK_REDIS_KEY, task_name, json.dumps(payload))
        redis_client.expire(_TASK_REDIS_KEY, 3600 * 12)
    except Exception:
        pass


