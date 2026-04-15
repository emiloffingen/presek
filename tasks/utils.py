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

def record_runtime_event(event: str, **fields):
    """Bridge to the main record_runtime_event in utils."""
    from utils import record_runtime_event as _record
    _record(event, **fields)
