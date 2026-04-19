import os
import logging
from database import db_manager as db
from utils import delete_cache, delete_cache_prefix, redis_client
from health import record_task_event

log = logging.getLogger("presek_celery")

_PUBLIC_SITE_URL = str(os.environ.get("PUBLIC_SITE_URL") or "https://presek.live").rstrip("/")

def invalidate_public_data_caches():
    delete_cache_prefix("v4:news:")
    delete_cache("ssr:index:top_clusters")
    delete_cache("trending")
    delete_cache("stats:full")

def invalidate_cluster_caches(cluster_id=None):
    if cluster_id:
        delete_cache(f"cluster:detail:{cluster_id}")
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
