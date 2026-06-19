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
_PUBLIC_CACHE_INVALIDATION_DEBOUNCE_KEY = "debounce:public_cache_invalidation"
_PUBLIC_CACHE_INVALIDATION_DEBOUNCE_SECONDS = int(
    os.environ.get("PUBLIC_CACHE_INVALIDATION_DEBOUNCE_SECONDS", "45")
)


def invalidate_public_data_caches():
    delete_cache_prefix("api:news:")
    delete_cache_prefix("api:home:")
    delete_cache_prefix("api:intelligence:")
    delete_cache_prefix("api:top-entities:")
    delete_cache_prefix("api:stats:summary:")
    delete_cache_prefix("stats:intel_summary:")
    delete_cache_prefix("api:trending:")


def invalidate_public_data_caches_debounced(force: bool = False) -> bool:
    """Invalidate public caches at most once per debounce window during bulk crawls."""
    if force:
        invalidate_public_data_caches()
        return True
    try:
        acquired = redis_client.set(
            _PUBLIC_CACHE_INVALIDATION_DEBOUNCE_KEY,
            "1",
            nx=True,
            ex=_PUBLIC_CACHE_INVALIDATION_DEBOUNCE_SECONDS,
        )
    except Exception as e:
        log.warning(f"Cache invalidation debounce check failed, invalidating anyway: {e}")
        invalidate_public_data_caches()
        return True
    if not acquired:
        return False
    invalidate_public_data_caches()
    return True


def safe_async_run(coro_or_factory):
    """Run an awaitable safely from sync code, even when an event loop is active."""
    coro = coro_or_factory() if callable(coro_or_factory) else coro_or_factory
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
    from core.queue_status import get_celery_queue_depth as _get_depth

    return _get_depth(queue_name)


INTEL_QUEUE_NAME = "intel-heavy"
FAST_TRACK_QUEUE_NAME = "fast-track"
MAINTENANCE_QUEUE_NAME = "maintenance"
INGESTION_QUEUE_NAME = "ingestion"
INGESTION_CRAWL_QUEUE_NAME = "ingestion-crawl"
INGESTION_TASK_NAME = "tasks.ingestion_task.run_ingestion"
INGESTION_CRAWL_TASKS = frozenset(
    {
        "tasks.ingestion_task.crawl_article_task",
        "tasks.ingestion_task.process_article_image_task",
        "tasks.ingestion_task.post_crawl_invalidation_task",
    }
)
INTEL_PRIORITY_TASKS = frozenset(
    {
        "tasks.intelligence.summarize_articles_batch_task",
        "tasks.intelligence.summarize_articles_local_batch_task",
        "tasks.intelligence.summarize_article_task",
        "tasks.intelligence.synthesize_cluster_task",
        "tasks.intelligence.synthesize_urgent_task",
        "tasks.intelligence.upgrade_fast_synthesis_task",
    }
)
FAST_TRACK_PRIORITY_TASKS = frozenset(
    {
        "tasks.intelligence.synthesize_urgent_task",
        "tasks.delivery.briefing.send_profile_breaking_alerts_task",
    }
)
FAST_TRACK_MISROUTED_TASKS = frozenset(
    {
        "tasks.intelligence.synthesize_cluster_task",
        "tasks.intelligence.auto_summarize_task",
    }
)
MAINTENANCE_HEAVY_TASKS = frozenset(
    {
        "tasks.maintenance.boost_homepage_cluster_supply_task",
        "tasks.intelligence.refresh_cluster_centroid_task",
        "tasks.intelligence.recluster_recent_articles_task",
        "tasks.intelligence.repair_split_clusters_task",
    }
)
MAINTENANCE_DEFERRABLE_TASKS = frozenset(
    {
        "tasks.intelligence.generate_cluster_metadata_task",
        "tasks.intelligence.upgrade_fast_synthesis_task",
        "tasks.intelligence.generate_embeddings_task",
    }
)
MAINTENANCE_QUEUE_GROOM_TASKS = frozenset(
    {
        "tasks.maintenance.prune_maintenance_queue_task",
        "tasks.maintenance.prune_fast_track_queue_task",
        "tasks.maintenance.prune_intel_queue_task",
        "tasks.maintenance.prune_ingestion_queue_task",
        "tasks.maintenance.prune_crawl_queue_task",
        "tasks.maintenance.refresh_synthesis_quality_task",
        "tasks.maintenance.ensure_ingestion_freshness_task",
    }
)
MAINTENANCE_MISROUTED_TASKS = frozenset(
    {
        "tasks.intelligence.upgrade_fast_synthesis_task",
    }
)
MAINTENANCE_SINGLETON_TASKS = frozenset(
    {
        "tasks.maintenance.prune_intel_queue_task",
        "tasks.maintenance.prune_fast_track_queue_task",
        "tasks.maintenance.prune_maintenance_queue_task",
        "tasks.maintenance.prune_ingestion_queue_task",
        "tasks.maintenance.prune_crawl_queue_task",
        "tasks.maintenance.refresh_synthesis_quality_task",
        "tasks.maintenance.prioritize_homepage_syntheses_task",
        "tasks.maintenance.ensure_ingestion_freshness_task",
        "tasks.maintenance.catch_up_cluster_syntheses_task",
        "tasks.maintenance.catch_up_recent_summaries_task",
        "tasks.maintenance.catch_up_deferred_crawls_task",
        "tasks.maintenance.upgrade_stuck_fast_syntheses_task",
        "tasks.maintenance.refresh_fallback_syntheses_task",
        "tasks.maintenance.refresh_low_score_syntheses_task",
        "tasks.maintenance.boost_homepage_cluster_supply_task",
        "tasks.intelligence.generate_cluster_metadata_task",
        "tasks.intelligence.generate_embeddings_task",
        "tasks.ingestion_task.repair_single_source_task",
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
        "tasks.intelligence.schedule_backfill_historical_summaries_task",
        "tasks.intelligence.backfill_historical_article_summaries_task",
    }
)


def _parse_queue_task_name(raw_message: str) -> str:
    import json

    body = json.loads(raw_message)
    return str((body.get("headers") or {}).get("task") or "")


def _parse_crawl_article_id(raw_message: str) -> int | None:
    import json
    import re

    body = json.loads(raw_message)
    task_name = str((body.get("headers") or {}).get("task") or "")
    if task_name != "tasks.ingestion_task.crawl_article_task":
        return None
    argsrepr = str((body.get("headers") or {}).get("argsrepr") or "")
    match = re.match(r"\((\d+),", argsrepr)
    return int(match.group(1)) if match else None


def _parse_upgrade_fast_synthesis_cluster_id(raw_message: str) -> str | None:
    import json
    import re

    body = json.loads(raw_message)
    argsrepr = str((body.get("headers") or {}).get("argsrepr") or "")
    match = re.match(r"\('([^']+)'", argsrepr)
    return match.group(1) if match else None


def _parse_synthesize_urgent_cluster_id(raw_message: str) -> str | None:
    import json

    body = json.loads(raw_message)
    task_name = str((body.get("headers") or {}).get("task") or "")
    if task_name != "tasks.intelligence.synthesize_urgent_task":
        return None
    return _parse_upgrade_fast_synthesis_cluster_id(raw_message)


def _parse_article_id_from_argsrepr(raw_message: str) -> int | None:
    import json
    import re

    body = json.loads(raw_message)
    argsrepr = str((body.get("headers") or {}).get("argsrepr") or "")
    match = re.match(r"\((\d+)", argsrepr)
    return int(match.group(1)) if match else None


def _parse_maintenance_dedupe_key(raw_message: str, task_name: str) -> str:
    if task_name != "tasks.intelligence.generate_cluster_metadata_task":
        if task_name == "tasks.ingestion_task.repair_single_source_task":
            import json
            import re

            body = json.loads(raw_message)
            argsrepr = str((body.get("headers") or {}).get("argsrepr") or "")
            match = re.match(r"\('([^']+)'", argsrepr)
            if match:
                return f"{task_name}:{match.group(1)}"
        return task_name

    import json
    import re

    body = json.loads(raw_message)
    kwargsrepr = str((body.get("headers") or {}).get("kwargsrepr") or "")
    cluster_match = re.search(r"'target_clusters':\s*\['([^']+)'\]", kwargsrepr)
    if cluster_match:
        return f"{task_name}:{cluster_match.group(1)}"
    return task_name


def get_total_queue_depth() -> int:
    from core.queue_status import get_total_queue_depth as _get_total_depth

    return int(_get_total_depth() or 0)


def get_reader_relevant_queue_depth() -> int:
    from core.queue_status import get_reader_relevant_queue_depth as _reader_depth

    return int(_reader_depth() or 0)


def fast_track_dispatches_deferred() -> bool:
    from core.limits import FAST_TRACK_QUEUE_DEFER_LIMIT

    return get_celery_queue_depth(FAST_TRACK_QUEUE_NAME) >= FAST_TRACK_QUEUE_DEFER_LIMIT


def maintenance_dispatches_deferred() -> bool:
    from core.limits import MAINTENANCE_QUEUE_DEFER_LIMIT

    return get_celery_queue_depth(MAINTENANCE_QUEUE_NAME) >= MAINTENANCE_QUEUE_DEFER_LIMIT


def pipeline_backpressure_active() -> bool:
    from core.limits import (
        CELERY_QUEUE_CRITICAL_DEPTH,
        FAST_TRACK_QUEUE_DEFER_LIMIT,
        INTEL_QUEUE_SECONDARY_DEFER_LIMIT,
        MAINTENANCE_QUEUE_DEFER_LIMIT,
        PIPELINE_TOTAL_DEFER_DEPTH,
    )

    if get_total_queue_depth() >= PIPELINE_TOTAL_DEFER_DEPTH:
        return True
    if get_celery_queue_depth(FAST_TRACK_QUEUE_NAME) >= FAST_TRACK_QUEUE_DEFER_LIMIT:
        return True
    if get_celery_queue_depth(INTEL_QUEUE_NAME) >= INTEL_QUEUE_SECONDARY_DEFER_LIMIT:
        return True
    if get_celery_queue_depth(MAINTENANCE_QUEUE_NAME) >= MAINTENANCE_QUEUE_DEFER_LIMIT:
        return True
    if get_celery_queue_depth() >= CELERY_QUEUE_CRITICAL_DEPTH:
        return True
    return False


def synthesis_dispatch_deferred() -> bool:
    from core.limits import INTEL_QUEUE_FULL_DEFER_LIMIT, SYNTHESIS_QUEUE_DEFER_LIMIT

    if get_celery_queue_depth("synthesis") >= SYNTHESIS_QUEUE_DEFER_LIMIT:
        return True
    if fast_track_dispatches_deferred():
        return True
    # Maintenance backlog inflates total depth but should not starve synthesis output.
    if get_celery_queue_depth(INTEL_QUEUE_NAME) >= INTEL_QUEUE_FULL_DEFER_LIMIT:
        return True
    return False


def crawl_dispatches_deferred() -> bool:
    from core.limits import CRAWL_QUEUE_DEFER_LIMIT

    return get_celery_queue_depth(INGESTION_CRAWL_QUEUE_NAME) >= CRAWL_QUEUE_DEFER_LIMIT


def crawl_dispatch_cap() -> int | None:
    """Return a per-cycle crawl cap when the crawl queue is elevated, else None."""
    from core.limits import CRAWL_DISPATCH_CAP, CRAWL_QUEUE_DEFER_LIMIT, CRAWL_QUEUE_SOFT_LIMIT

    depth = get_celery_queue_depth(INGESTION_CRAWL_QUEUE_NAME)
    if depth >= CRAWL_QUEUE_DEFER_LIMIT:
        return 0
    if depth >= CRAWL_QUEUE_SOFT_LIMIT:
        return CRAWL_DISPATCH_CAP
    return None


def reprioritize_intel_queue(*, defer_threshold: int = 150, groom_threshold: int = 80, dry_run: bool = False) -> dict:
    """Drop deferrable intel-heavy tasks and move summarize batches to the queue head."""
    depth_before = get_celery_queue_depth(INTEL_QUEUE_NAME)
    if depth_before < groom_threshold:
        return {
            "skipped": True,
            "reason": "below_groom_threshold",
            "depth_before": depth_before,
            "groom_threshold": groom_threshold,
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
        "groom_threshold": groom_threshold,
        "defer_threshold": defer_threshold,
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


def prune_ingestion_queue(*, max_pending: int = 1, dry_run: bool = False) -> dict:
    """Drop excess queued run_ingestion dispatches from the ingestion queue."""
    depth_before = get_celery_queue_depth(INGESTION_QUEUE_NAME)
    if depth_before <= max_pending:
        return {
            "skipped": True,
            "reason": "below_threshold",
            "depth_before": depth_before,
            "max_pending": max_pending,
        }

    raw_items = redis_client.lrange(INGESTION_QUEUE_NAME, 0, -1) or []
    kept = []
    removed = 0
    pending_ingestion = 0

    for raw in raw_items:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        task_name = _parse_queue_task_name(raw)
        if task_name == INGESTION_TASK_NAME:
            if pending_ingestion < max_pending:
                kept.append(raw)
                pending_ingestion += 1
            else:
                removed += 1
        elif task_name in INGESTION_CRAWL_TASKS:
            removed += 1
        else:
            kept.append(raw)

    result = {
        "skipped": False,
        "depth_before": depth_before,
        "depth_after": len(kept),
        "removed": removed,
        "kept_ingestion": pending_ingestion,
        "dry_run": dry_run,
        "max_pending": max_pending,
    }

    if dry_run:
        return result

    pipe = redis_client.pipeline()
    pipe.delete(INGESTION_QUEUE_NAME)
    if kept:
        pipe.rpush(INGESTION_QUEUE_NAME, *kept)
    pipe.execute()
    result["depth_after"] = get_celery_queue_depth(INGESTION_QUEUE_NAME)
    return result


def prune_crawl_queue(*, dry_run: bool = False) -> dict:
    """Drop duplicate crawl/image/invalidation dispatches, keeping the oldest per article."""
    from core.limits import CRAWL_QUEUE_SOFT_LIMIT

    depth_before = get_celery_queue_depth(INGESTION_CRAWL_QUEUE_NAME)
    if depth_before <= 1:
        return {
            "skipped": True,
            "reason": "below_threshold",
            "depth_before": depth_before,
        }

    raw_items = redis_client.lrange(INGESTION_CRAWL_QUEUE_NAME, 0, -1) or []
    kept = []
    seen_crawl_ids: set[int] = set()
    seen_image_ids: set[int] = set()
    seen_invalidation_ids: set[int] = set()
    removed = 0

    for raw in raw_items:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        task_name = _parse_queue_task_name(raw)
        if task_name == "tasks.ingestion_task.crawl_article_task":
            article_id = _parse_crawl_article_id(raw)
            if article_id is not None:
                if article_id in seen_crawl_ids:
                    removed += 1
                    continue
                seen_crawl_ids.add(article_id)
        elif task_name == "tasks.ingestion_task.process_article_image_task":
            article_id = _parse_article_id_from_argsrepr(raw)
            if article_id is not None:
                if article_id in seen_image_ids:
                    removed += 1
                    continue
                seen_image_ids.add(article_id)
        elif task_name == "tasks.ingestion_task.post_crawl_invalidation_task":
            article_id = _parse_article_id_from_argsrepr(raw)
            if article_id is not None:
                if article_id in seen_invalidation_ids:
                    removed += 1
                    continue
                seen_invalidation_ids.add(article_id)

        kept.append(raw)

    if len(kept) > CRAWL_QUEUE_SOFT_LIMIT:
        trimmed: list[str] = []
        invalidation_kept = 0
        invalidation_cap = max(5, CRAWL_QUEUE_SOFT_LIMIT // 10)
        for raw in kept:
            task_name = _parse_queue_task_name(raw)
            if task_name == "tasks.ingestion_task.post_crawl_invalidation_task":
                if invalidation_kept >= invalidation_cap:
                    removed += 1
                    continue
                invalidation_kept += 1
            trimmed.append(raw)
        kept = trimmed

    def _crawl_queue_sort_key(raw: str) -> int:
        task_name = _parse_queue_task_name(raw)
        if task_name == "tasks.ingestion_task.crawl_article_task":
            return 0
        if task_name == "tasks.ingestion_task.process_article_image_task":
            return 1
        return 2

    kept.sort(key=_crawl_queue_sort_key)

    result = {
        "skipped": False,
        "depth_before": depth_before,
        "depth_after": len(kept),
        "removed": removed,
        "dry_run": dry_run,
    }

    if dry_run:
        return result

    pipe = redis_client.pipeline()
    pipe.delete(INGESTION_CRAWL_QUEUE_NAME)
    if kept:
        pipe.rpush(INGESTION_CRAWL_QUEUE_NAME, *kept)
    pipe.execute()
    result["depth_after"] = get_celery_queue_depth(INGESTION_CRAWL_QUEUE_NAME)
    return result


def reprioritize_fast_track_queue(*, groom_threshold: int = 60, dry_run: bool = False) -> dict:
    """Drop misrouted synthesis work from fast-track while keeping urgent tasks."""
    from core.limits import FAST_TRACK_QUEUE_GROOM_DEPTH

    groom_threshold = int(groom_threshold or FAST_TRACK_QUEUE_GROOM_DEPTH)
    depth_before = get_celery_queue_depth(FAST_TRACK_QUEUE_NAME)
    if depth_before < groom_threshold:
        return {
            "skipped": True,
            "reason": "below_groom_threshold",
            "depth_before": depth_before,
            "groom_threshold": groom_threshold,
        }

    raw_items = redis_client.lrange(FAST_TRACK_QUEUE_NAME, 0, -1) or []
    urgent_by_cluster: dict[str, str] = {}
    breaking_alerts: list[str] = []
    kept_other: list[str] = []
    removed = 0
    seen_auto_summarize = False
    seen_breaking_alerts = False
    urgent_duplicates_removed = 0

    for raw in raw_items:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        task_name = _parse_queue_task_name(raw)
        if task_name == "tasks.intelligence.synthesize_urgent_task":
            cluster_id = _parse_synthesize_urgent_cluster_id(raw)
            if cluster_id:
                if cluster_id in urgent_by_cluster:
                    removed += 1
                    urgent_duplicates_removed += 1
                urgent_by_cluster[cluster_id] = raw
                continue
        if task_name == "tasks.delivery.briefing.send_profile_breaking_alerts_task":
            if seen_breaking_alerts:
                removed += 1
                continue
            seen_breaking_alerts = True
            breaking_alerts.append(raw)
            continue
        if task_name == "tasks.intelligence.auto_summarize_task":
            if seen_auto_summarize:
                removed += 1
                continue
            seen_auto_summarize = True
            kept_other.append(raw)
            continue
        if task_name in FAST_TRACK_MISROUTED_TASKS:
            removed += 1
            continue
        kept_other.append(raw)

    priority_items = list(urgent_by_cluster.values()) + breaking_alerts
    rebuilt = priority_items + kept_other
    result = {
        "skipped": False,
        "depth_before": depth_before,
        "depth_after": len(rebuilt),
        "removed": removed,
        "priority_count": len(priority_items),
        "kept_other_count": len(kept_other),
        "urgent_deduped": urgent_duplicates_removed,
        "dry_run": dry_run,
        "groom_threshold": groom_threshold,
    }
    if dry_run:
        return result

    pipe = redis_client.pipeline()
    pipe.delete(FAST_TRACK_QUEUE_NAME)
    if rebuilt:
        pipe.rpush(FAST_TRACK_QUEUE_NAME, *rebuilt)
    pipe.execute()
    result["depth_after"] = get_celery_queue_depth(FAST_TRACK_QUEUE_NAME)
    return result


def reprioritize_maintenance_queue(*, groom_threshold: int = 80, dry_run: bool = False) -> dict:
    """Drop duplicate maintenance housekeeping when the maintenance queue is congested."""
    from core.limits import MAINTENANCE_QUEUE_SOFT_LIMIT

    groom_threshold = int(groom_threshold or MAINTENANCE_QUEUE_SOFT_LIMIT)
    depth_before = get_celery_queue_depth(MAINTENANCE_QUEUE_NAME)
    if depth_before < groom_threshold:
        return {
            "skipped": True,
            "reason": "below_groom_threshold",
            "depth_before": depth_before,
            "groom_threshold": groom_threshold,
        }

    raw_items = redis_client.lrange(MAINTENANCE_QUEUE_NAME, 0, -1) or []
    kept = []
    removed = 0
    seen_singletons: set[str] = set()
    seen_heavy: set[str] = set()
    seen_metadata_clusters: set[str] = set()
    seen_upgrade_clusters: set[str] = set()

    for raw in raw_items:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        task_name = _parse_queue_task_name(raw)
        if task_name in MAINTENANCE_MISROUTED_TASKS:
            removed += 1
            continue
        dedupe_key = _parse_maintenance_dedupe_key(raw, task_name)

        if task_name in MAINTENANCE_HEAVY_TASKS:
            if task_name in seen_heavy:
                removed += 1
                continue
            seen_heavy.add(task_name)
        elif task_name in MAINTENANCE_SINGLETON_TASKS:
            if dedupe_key in seen_singletons:
                removed += 1
                continue
            seen_singletons.add(dedupe_key)
        elif task_name == "tasks.intelligence.upgrade_fast_synthesis_task":
            cluster_id = _parse_upgrade_fast_synthesis_cluster_id(raw)
            if cluster_id and cluster_id in seen_upgrade_clusters:
                removed += 1
                continue
            if cluster_id:
                seen_upgrade_clusters.add(cluster_id)

        kept.append(raw)

    from core.limits import MAINTENANCE_QUEUE_DEFER_LIMIT

    defer_cap = max(20, MAINTENANCE_QUEUE_DEFER_LIMIT // 3)
    if len(kept) > MAINTENANCE_QUEUE_DEFER_LIMIT:
        trimmed: list[str] = []
        defer_kept = 0
        for raw in kept:
            task_name = _parse_queue_task_name(raw)
            if task_name in MAINTENANCE_DEFERRABLE_TASKS:
                if defer_kept >= defer_cap:
                    removed += 1
                    continue
                defer_kept += 1
            trimmed.append(raw)
        kept = trimmed

    def _maintenance_queue_sort_key(raw: str) -> tuple[int, int]:
        task_name = _parse_queue_task_name(raw)
        if task_name in MAINTENANCE_QUEUE_GROOM_TASKS:
            return (0, 0)
        if task_name in MAINTENANCE_HEAVY_TASKS:
            return (2, 0)
        if task_name in MAINTENANCE_DEFERRABLE_TASKS:
            return (3, 0)
        return (1, 0)

    kept.sort(key=_maintenance_queue_sort_key)

    result = {
        "skipped": False,
        "depth_before": depth_before,
        "depth_after": len(kept),
        "removed": removed,
        "dry_run": dry_run,
        "groom_threshold": groom_threshold,
    }
    if dry_run:
        return result

    pipe = redis_client.pipeline()
    pipe.delete(MAINTENANCE_QUEUE_NAME)
    if kept:
        pipe.rpush(MAINTENANCE_QUEUE_NAME, *kept)
    pipe.execute()
    result["depth_after"] = get_celery_queue_depth(MAINTENANCE_QUEUE_NAME)
    return result


def schedule_task_once(
    lock_key: str,
    ttl_seconds: int,
    task,
    *,
    args=None,
    kwargs=None,
    countdown=0,
    queue: str | None = None,
) -> bool:
    """Schedule a Celery task only if no matching lock is already held."""
    if not acquire_task_lock(lock_key, ttl_seconds):
        return False
    options = {"countdown": max(0, int(countdown))}
    if queue:
        options["queue"] = queue
    task.apply_async(args=args or (), kwargs=kwargs or {}, **options)
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
