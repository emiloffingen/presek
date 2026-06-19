import asyncio
import os
import sys

# Ensure project root is in path for Celery workers
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.celery_app import celery_app
from core.database import db_manager as db
from core.database import prune_db
from core.image_service import image_service
from tasks.utils import (
    invalidate_public_data_caches,
    log,
    prune_crawl_queue,
    prune_ingestion_queue,
    reprioritize_intel_queue,
    schedule_task_once,
)


def maintenance_task(*task_args, **task_kwargs):
    """Celery decorator with transient-failure retries for maintenance jobs."""
    opts = {
        "autoretry_for": (Exception,),
        "retry_backoff": True,
        "max_retries": 2,
    }
    opts.update(task_kwargs)
    if task_args:
        return celery_app.task(*task_args, **opts)
    return celery_app.task(**opts)


def _synthesis_queue_depth() -> int:
    from tasks.utils import get_celery_queue_depth

    return int(get_celery_queue_depth("synthesis") or 0)


def _synthesis_dispatch_deferred() -> bool:
    from tasks.utils import synthesis_dispatch_deferred

    return synthesis_dispatch_deferred()


def _effective_synthesis_refresh_hourly_cap() -> int:
    from core.limits import (
        SYNTHESIS_QUEUE_BURST_INTEL_MAX,
        SYNTHESIS_REFRESH_HOURLY_CAP,
        SYNTHESIS_REFRESH_HOURLY_CAP_BURST,
    )
    from tasks.utils import get_celery_queue_depth

    if (
        _synthesis_queue_depth() < 20
        and int(get_celery_queue_depth("intel-heavy") or 0) < SYNTHESIS_QUEUE_BURST_INTEL_MAX
    ):
        return max(SYNTHESIS_REFRESH_HOURLY_CAP, SYNTHESIS_REFRESH_HOURLY_CAP_BURST)
    return SYNTHESIS_REFRESH_HOURLY_CAP


_HOMEPAGE_CLUSTER_SECTIONS = (
    "lead",
    "supporting",
    "developing",
    "live_now",
    "synthesis_picks",
    "for_you_pool",
    "wire",
    "global",
)

_HOMEPAGE_HERO_SYNTHESIS_SECTIONS = (
    "lead",
    "supporting",
)


def _iter_homepage_payload_clusters(payload: dict):
    for section in _HOMEPAGE_CLUSTER_SECTIONS:
        value = payload.get(section)
        if not value:
            continue
        if isinstance(value, dict):
            if value.get("cluster_id"):
                yield value
            continue
        if isinstance(value, list):
            for cluster in value:
                if isinstance(cluster, dict) and cluster.get("cluster_id"):
                    yield cluster


def _iter_homepage_payload_clusters_for_sections(payload: dict, sections: tuple[str, ...]):
    for section in sections:
        value = payload.get(section)
        if not value:
            continue
        if isinstance(value, dict):
            if value.get("cluster_id"):
                yield value
            continue
        if isinstance(value, list):
            for cluster in value:
                if isinstance(cluster, dict) and cluster.get("cluster_id"):
                    yield cluster


def _fetch_homepage_payload(lang: str) -> dict:
    import json
    import urllib.request

    url = f"http://127.0.0.1:5001/api/home?lang={lang}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        log.warning("[maintenance] Failed to fetch homepage payload for %s: %s", lang, exc)
        return {}
    if payload.get("status") != "success":
        return {}
    return payload


def _fetch_homepage_visible_clusters(lang: str) -> list[dict]:
    payload = _fetch_homepage_payload(lang)
    if not payload:
        return []

    clusters: list[dict] = []
    seen: set[str] = set()
    for cluster in _iter_homepage_payload_clusters(payload):
        cluster_id = str(cluster.get("cluster_id") or "").strip()
        if not cluster_id or cluster_id in seen:
            continue
        seen.add(cluster_id)
        clusters.append(cluster)
    return clusters


def _collect_homepage_synthesis_targets() -> list[str]:
    """Return homepage cluster IDs needing synthesis, hero sections first."""
    targets: list[str] = []
    seen: set[str] = set()
    other_sections = tuple(
        section for section in _HOMEPAGE_CLUSTER_SECTIONS if section not in _HOMEPAGE_HERO_SYNTHESIS_SECTIONS
    )

    for sections in (_HOMEPAGE_HERO_SYNTHESIS_SECTIONS, other_sections):
        for lang in ("sr", "mk"):
            payload = _fetch_homepage_payload(lang)
            if not payload:
                continue
            for cluster in _iter_homepage_payload_clusters_for_sections(payload, sections):
                cluster_id = str(cluster.get("cluster_id") or "").strip()
                if not cluster_id or cluster_id in seen or not _cluster_needs_synthesis(cluster):
                    continue
                seen.add(cluster_id)
                targets.append(cluster_id)
    return targets


def _collect_homepage_hero_cluster_ids() -> set[str]:
    hero_ids: set[str] = set()
    for lang in ("sr", "mk"):
        payload = _fetch_homepage_payload(lang)
        if not payload:
            continue
        for cluster in _iter_homepage_payload_clusters_for_sections(payload, _HOMEPAGE_HERO_SYNTHESIS_SECTIONS):
            cluster_id = str(cluster.get("cluster_id") or "").strip()
            if cluster_id:
                hero_ids.add(cluster_id)
    return hero_ids


def _cluster_needs_synthesis(cluster: dict) -> bool:
    articles = cluster.get("articles") or []
    freshness = cluster.get("synthesis_freshness") or {}
    synthesis_meta = cluster.get("synthesis_meta") or {}
    reasons = freshness.get("reasons") or []
    needs_synthesis = (
        not cluster.get("has_synthesis")
        or bool(freshness.get("is_stale"))
        or bool(synthesis_meta.get("needs_upgrade"))
        or "missing_synthesis" in reasons
    )
    if not needs_synthesis:
        return False
    min_sources = 1 if ("missing_synthesis" in reasons or not cluster.get("has_synthesis")) else 2
    return len(articles) >= min_sources


def _homepage_synthesis_only() -> bool:
    from core.config import HOMEPAGE_SYNTHESIS_ONLY

    return HOMEPAGE_SYNTHESIS_ONLY


def _collect_homepage_layout_cluster_ids(limit: int = 48) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for lang in ("sr", "mk"):
        for cluster in _fetch_homepage_visible_clusters(lang):
            cluster_id = str(cluster.get("cluster_id") or "").strip()
            if not cluster_id or cluster_id in seen:
                continue
            seen.add(cluster_id)
            targets.append(cluster_id)
            if len(targets) >= limit:
                return targets
    return targets


def _collect_homepage_cluster_ids(limit: int = 48) -> list[str]:
    targets = _collect_homepage_layout_cluster_ids(limit)
    if len(targets) >= limit or _homepage_synthesis_only():
        return targets

    from routes.news import fetch_news_data
    from tasks.utils import safe_async_run

    seen = set(targets)
    for lang in ("sr", "mk"):
        payload = safe_async_run(lambda: fetch_news_data(sort="score", page_size=24, lang=lang)) or {}
        for cluster in payload.get("clusters") or []:
            cluster_id = str(cluster.get("cluster_id") or "").strip()
            if not cluster_id or cluster_id in seen:
                continue
            seen.add(cluster_id)
            targets.append(cluster_id)
            if len(targets) >= limit:
                return targets
    return targets


def filter_cluster_ids_for_synthesis(cluster_ids: list[str]) -> list[str]:
    """Return cluster IDs that should receive scheduled synthesis work."""
    normalized = [str(cluster_id).strip() for cluster_id in (cluster_ids or []) if str(cluster_id).strip()]
    if not normalized:
        return []
    if not _homepage_synthesis_only():
        return normalized
    homepage_ids = set(_collect_homepage_layout_cluster_ids())
    return [cluster_id for cluster_id in normalized if cluster_id in homepage_ids]


def _synthesis_refresh_budget_remaining() -> int:
    """Return remaining hourly budget for maintenance synthesis refresh tasks."""
    cap = _effective_synthesis_refresh_hourly_cap()
    if cap <= 0:
        return 10**9
    try:
        from utils import redis_client

        key = "presek:synthesis_refresh_hourly"
        used = int(redis_client.get(key) or 0)
        return max(0, cap - used)
    except Exception:
        return cap


def _consume_synthesis_refresh_budget(count: int = 1) -> bool:
    cap = _effective_synthesis_refresh_hourly_cap()
    if cap <= 0:
        return True
    try:
        from utils import redis_client

        key = "presek:synthesis_refresh_hourly"
        current = int(redis_client.incrby(key, max(0, int(count))))
        if current == max(0, int(count)):
            redis_client.expire(key, 3600)
        return current <= cap
    except Exception:
        return True


@maintenance_task
def run_prune_db():
    """Standard maintenance."""
    try:
        prune_db()
    except Exception as e:
        log.error(f"[tasks] prune_db failed: {e}", exc_info=True)
    try:
        valid_rows = db.execute("SELECT DISTINCT cluster_id FROM articles")
        valid_ids = {str(r["cluster_id"]) for r in valid_rows if r["cluster_id"]}
        from core.ai_engine import cleanup_cover_art

        cleanup_cover_art(valid_ids)
    except Exception as e:
        log.error(f"[tasks] cleanup_cover_art failed: {e}", exc_info=True)

    try:
        # 3. Clean up orphaned local images and logs
        art_rows = db.execute("SELECT id FROM articles")
        active_art_ids = {int(r["id"]) for r in art_rows}
        asyncio.run(image_service.cleanup_storage(active_art_ids))
    except Exception as e:
        log.error(f"[tasks] cleanup_storage failed: {e}", exc_info=True)


@maintenance_task
def prune_fast_track_queue_task(dry_run=False):
    """Drop misrouted synthesis work from the fast-track queue."""
    try:
        from tasks.utils import reprioritize_fast_track_queue

        result = reprioritize_fast_track_queue(dry_run=bool(dry_run))
        if result.get("removed"):
            log.info(
                "[maintenance] Pruned fast-track queue: removed=%s depth=%s->%s",
                result["removed"],
                result.get("depth_before"),
                result.get("depth_after"),
            )
        return result
    except Exception as e:
        log.error(f"[maintenance] prune_fast_track_queue failed: {e}", exc_info=True)
        raise


@maintenance_task
def prune_maintenance_queue_task(dry_run=False):
    """Drop duplicate heavy maintenance dispatches when the queue is congested."""
    try:
        from tasks.utils import reprioritize_maintenance_queue

        result = reprioritize_maintenance_queue(dry_run=bool(dry_run))
        if result.get("removed"):
            log.info(
                "[maintenance] Pruned maintenance queue: removed=%s depth=%s->%s",
                result["removed"],
                result.get("depth_before"),
                result.get("depth_after"),
            )
        return result
    except Exception as e:
        log.error(f"[maintenance] prune_maintenance_queue failed: {e}", exc_info=True)
        raise


@maintenance_task
def prune_intel_queue_task(defer_threshold=None, dry_run=False):
    """Drop deferrable intel-heavy tasks and prioritize summarize batches when congested."""
    threshold = int(defer_threshold or os.environ.get("INTEL_QUEUE_SECONDARY_DEFER_LIMIT", "150"))
    groom = int(os.environ.get("INTEL_QUEUE_GROOM_DEPTH", "80"))
    try:
        result = reprioritize_intel_queue(defer_threshold=threshold, groom_threshold=groom, dry_run=bool(dry_run))
        if result.get("removed"):
            log.info(
                "[maintenance] Pruned intel-heavy queue: removed=%s priority=%s depth=%s->%s",
                result["removed"],
                result["priority_count"],
                result["depth_before"],
                result["depth_after"],
            )
        return result
    except Exception as e:
        log.error(f"[maintenance] prune_intel_queue failed: {e}", exc_info=True)
        raise


@maintenance_task
def upgrade_stuck_fast_syntheses_task(limit=None):
    """Enqueue full-quality upgrades for fast-mode publishes that stayed provisional too long."""
    from core.limits import FAST_SYNTHESIS_STUCK_HOURS, FAST_SYNTHESIS_UPGRADE_QUEUE, FAST_SYNTHESIS_UPGRADE_SWEEP_LIMIT
    from core.synthesis_quality import list_stuck_fast_synthesis_cluster_ids, prune_stale_fast_synthesis_pending
    from tasks.intelligence.synthesis import upgrade_fast_synthesis_task
    from tasks.utils import maintenance_dispatches_deferred

    if maintenance_dispatches_deferred():
        log.info("[maintenance] Skipping stuck fast synthesis sweep while maintenance queue is congested.")
        return {"skipped": True, "reason": "maintenance_backlog"}

    cleared_pending = prune_stale_fast_synthesis_pending()
    batch_limit = max(1, int(limit or FAST_SYNTHESIS_UPGRADE_SWEEP_LIMIT))
    cluster_ids = list_stuck_fast_synthesis_cluster_ids(
        max_age_hours=FAST_SYNTHESIS_STUCK_HOURS,
        limit=batch_limit,
    )
    if not cluster_ids:
        return {"enqueued": 0, "stuck_total": 0, "cleared_pending": cleared_pending}

    enqueued = 0
    for cluster_id in cluster_ids:
        lock_key = f"lock:fast_synthesis_upgrade:{cluster_id}"
        if schedule_task_once(
            lock_key,
            int(os.environ.get("FAST_SYNTHESIS_UPGRADE_LOCK_TTL_SECONDS", "7200")),
            upgrade_fast_synthesis_task,
            args=(cluster_id,),
            kwargs={"content": None, "defer_attempt": 0},
            countdown=30,
            queue=os.environ.get("FAST_SYNTHESIS_UPGRADE_QUEUE", FAST_SYNTHESIS_UPGRADE_QUEUE),
        ):
            enqueued += 1

    log.info(
        "[maintenance] Enqueued %s stuck fast synthesis upgrades (found=%s, age>=%sh)",
        enqueued,
        len(cluster_ids),
        FAST_SYNTHESIS_STUCK_HOURS,
    )
    return {"enqueued": enqueued, "stuck_total": len(cluster_ids), "cleared_pending": cleared_pending}


@maintenance_task
def refresh_fallback_syntheses_task(limit=None):
    """Re-run full synthesis for provisional or deterministic fallback summaries."""
    from core.limits import FALLBACK_SYNTHESIS_REFRESH_LIMIT
    from tasks.intelligence import synthesize_cluster_task

    if _synthesis_dispatch_deferred():
        log.info("[maintenance] Skipping fallback synthesis refresh while synthesis queue backlog is high.")
        return {"skipped": True, "reason": "synthesis_backlog"}

    batch_limit = max(1, int(limit or FALLBACK_SYNTHESIS_REFRESH_LIMIT))
    budget = _synthesis_refresh_budget_remaining()
    if budget <= 0:
        return {"skipped": True, "reason": "hourly_cap"}
    batch_limit = min(batch_limit, budget)
    rows = db.execute(
        """
        SELECT cluster_id, MAX(created_at) AS latest_at
        FROM cluster_summaries
        WHERE created_at >= NOW() - INTERVAL '7 days'
          AND (
            fallback_reason = 'fast_mode_provisional'
            OR generation_provider = 'enhanced_fallback'
            OR COALESCE(fallback_reason, '') ILIKE '%%enhanced_fallback%%'
          )
        GROUP BY cluster_id
        ORDER BY latest_at ASC
        LIMIT %s
        """,
        (max(batch_limit * 4, batch_limit),),
        read_only=True,
    ) or []

    homepage_ids = set(_collect_homepage_cluster_ids())
    ordered_rows = sorted(
        rows,
        key=lambda row: (str(row["cluster_id"]) not in homepage_ids, row["latest_at"]),
    )

    enqueued = 0
    homepage_enqueued = 0
    for idx, row in enumerate(ordered_rows[:batch_limit]):
        if not _consume_synthesis_refresh_budget():
            break
        synthesize_cluster_task.apply_async(
            (row["cluster_id"], None),
            {"fast_mode": False},
            countdown=idx * 25,
            queue="synthesis",
        )
        enqueued += 1
        if str(row["cluster_id"]) in homepage_ids:
            homepage_enqueued += 1

    log.info(
        "[maintenance] Enqueued fallback/provisional synthesis refresh for %s clusters (%s homepage-priority)",
        enqueued,
        homepage_enqueued,
    )
    return {
        "enqueued": enqueued,
        "homepage_enqueued": homepage_enqueued,
        "candidates": len(rows),
        "hourly_cap": _effective_synthesis_refresh_hourly_cap(),
    }


@maintenance_task
def refresh_synthesis_quality_task():
    """Refresh the Redis synthesis quality snapshot used by /api/health."""
    try:
        from scripts.monitor_synthesis_quality import build_snapshot, _write_redis

        snapshot = build_snapshot()
        _write_redis(snapshot)
        log.info(
            "[maintenance] Refreshed synthesis quality snapshot: status=%s queue=%s",
            snapshot.get("status"),
            snapshot.get("celery_queue_depth"),
        )
        return snapshot
    except Exception as e:
        log.error(f"[maintenance] refresh_synthesis_quality failed: {e}", exc_info=True)
        raise


@maintenance_task
def catch_up_recent_summaries_task(hours=72, limit=400):
    """Enqueue summarize batches for recent articles missing summaries when the queue has headroom."""
    from tasks.intelligence import (
        _dispatch_batched,
        intelligence_batches_deferred,
        summarize_articles_local_batch_task,
    )
    from tasks.utils import get_celery_queue_depth, pipeline_backpressure_active

    if pipeline_backpressure_active() or intelligence_batches_deferred():
        log.info("[maintenance] Skipping recent summary catch-up while pipeline backlog is high.")
        return {"skipped": True, "reason": "backlog_full"}

    depth = get_celery_queue_depth("intel-heavy")
    headroom = max(0, int(os.environ.get("INTEL_QUEUE_FULL_DEFER_LIMIT", "800")) - depth - 40)
    scaled_limit = min(max(1, int(limit)), max(1, headroom * 8))

    homepage_ids = _collect_homepage_layout_cluster_ids() if _homepage_synthesis_only() else None
    if homepage_ids is not None and not homepage_ids:
        return {"skipped": True, "reason": "no_homepage_clusters"}

    try:
        if homepage_ids is not None:
            rows = db.execute(
                """
                SELECT id
                FROM articles
                WHERE summary IS NULL
                  AND created_at >= NOW() - make_interval(hours => %s)
                  AND cluster_id = ANY(%s)
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (max(1, int(hours)), homepage_ids, scaled_limit),
                read_only=True,
            ) or []
        else:
            rows = db.execute(
                """
                SELECT id
                FROM articles
                WHERE summary IS NULL
                  AND created_at >= NOW() - make_interval(hours => %s)
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (max(1, int(hours)), scaled_limit),
                read_only=True,
            ) or []
        article_ids = [int(row["id"]) for row in rows]
        if not article_ids:
            return {"enqueued": 0}

        _dispatch_batched(summarize_articles_local_batch_task, article_ids)
        log.info("[maintenance] Enqueued Gemma-only summary catch-up for %s recent articles", len(article_ids))
        return {"enqueued": len(article_ids)}
    except Exception as e:
        log.error(f"[maintenance] catch_up_recent_summaries failed: {e}", exc_info=True)
        raise


@maintenance_task
def prune_crawl_queue_task(dry_run=False):
    """Drop duplicate crawl_article_task dispatches from the ingestion-crawl queue."""
    try:
        result = prune_crawl_queue(dry_run=bool(dry_run))
        if result.get("removed"):
            log.info(
                "[maintenance] Pruned ingestion-crawl queue: removed=%s depth=%s->%s",
                result["removed"],
                result.get("depth_before"),
                result.get("depth_after"),
            )
        return result
    except Exception as e:
        log.error(f"[maintenance] prune_crawl_queue failed: {e}", exc_info=True)
        raise


@maintenance_task
def catch_up_deferred_crawls_task(limit=None):
    """Enqueue crawls for recent articles missing full_content when crawl queue has headroom."""
    from core.limits import CRAWL_CATCH_UP_LIMIT, CRAWL_QUEUE_SOFT_LIMIT
    from tasks.ingestion_task import crawl_article_task
    from tasks.utils import crawl_dispatches_deferred, get_celery_queue_depth

    if crawl_dispatches_deferred():
        log.info("[maintenance] Skipping deferred crawl catch-up while ingestion-crawl backlog is high.")
        return {"skipped": True, "reason": "crawl_backlog_high"}

    depth = get_celery_queue_depth("ingestion-crawl")
    headroom = max(0, CRAWL_QUEUE_SOFT_LIMIT - depth)
    dispatch_limit = min(max(1, int(limit or CRAWL_CATCH_UP_LIMIT)), headroom)
    if dispatch_limit <= 0:
        return {"skipped": True, "reason": "no_headroom", "depth": depth}

    rows = db.execute(
        """
        SELECT id, link
        FROM articles
        WHERE full_content IS NULL
          AND created_at >= NOW() - make_interval(hours => 72)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (dispatch_limit,),
        read_only=True,
    ) or []

    enqueued = 0
    for row in rows:
        crawl_article_task.delay(int(row["id"]), row["link"])
        enqueued += 1

    if enqueued:
        log.info("[maintenance] Enqueued deferred crawl catch-up for %s articles", enqueued)
    return {"enqueued": enqueued, "depth": depth}


@maintenance_task
def prune_ingestion_queue_task(max_pending=1, dry_run=False):
    """Drop duplicate queued run_ingestion dispatches."""
    try:
        result = prune_ingestion_queue(max_pending=int(max_pending), dry_run=bool(dry_run))
        if result.get("removed"):
            log.info(
                "[maintenance] Pruned ingestion queue: removed=%s depth=%s->%s",
                result["removed"],
                result["depth_before"],
                result["depth_after"],
            )
        return result
    except Exception as e:
        log.error(f"[maintenance] prune_ingestion_queue failed: {e}", exc_info=True)
        raise


@maintenance_task
def ensure_ingestion_freshness_task(max_age_minutes=120):
    """Trigger ingestion when the public freshness badge has gone stale."""
    from core.health import load_last_refresh_time, _freshness_payload
    from tasks.ingestion_task import run_ingestion

    from core.ingestion_lock import break_stale_ingestion_lock, is_ingestion_in_flight

    prune_ingestion_queue(max_pending=1)

    freshness = _freshness_payload(load_last_refresh_time())
    age_minutes = freshness.get("age_minutes")
    if age_minutes is not None and age_minutes <= int(max_age_minutes):
        return {"skipped": True, "age_minutes": age_minutes}
    if is_ingestion_in_flight() and not break_stale_ingestion_lock():
        return {"skipped": True, "reason": "in_flight", "age_minutes": age_minutes}

    run_ingestion.apply_async(expires=540)
    log.warning(
        "[maintenance] Triggered ingestion recovery because freshness age is %s minutes",
        age_minutes,
    )
    return {"triggered": True, "age_minutes": age_minutes}


@maintenance_task
def catch_up_cluster_syntheses_task(hours=48, limit=50):
    """Enqueue full synthesis for recent multi-source clusters missing cluster summaries."""
    from tasks.intelligence import synthesize_cluster_task

    if _homepage_synthesis_only():
        log.info("[maintenance] Skipping cluster synthesis catch-up in homepage-only mode.")
        return {"skipped": True, "reason": "homepage_only"}

    if _synthesis_dispatch_deferred():
        log.info("[maintenance] Skipping cluster synthesis catch-up while synthesis queue backlog is high.")
        return {"skipped": True, "reason": "synthesis_backlog"}

    rows = db.execute(
        """
        SELECT a.cluster_id, COUNT(a.id) AS source_count
        FROM articles a
        LEFT JOIN cluster_summaries cs ON cs.cluster_id = a.cluster_id
        WHERE a.created_at >= NOW() - make_interval(hours => %s)
          AND cs.cluster_id IS NULL
        GROUP BY a.cluster_id
        HAVING COUNT(a.id) >= 2
        ORDER BY MAX(a.created_at) DESC
        LIMIT %s
        """,
        (max(1, int(hours)), max(1, int(limit))),
        read_only=True,
    ) or []

    enqueued = 0
    for idx, row in enumerate(rows):
        synthesize_cluster_task.apply_async(
            (row["cluster_id"], None),
            {"fast_mode": False},
            countdown=idx * 20,
            queue="synthesis",
        )
        enqueued += 1

    if enqueued:
        log.info("[maintenance] Enqueued cluster synthesis catch-up for %s clusters", enqueued)
    return {"enqueued": enqueued}


@maintenance_task
def prioritize_homepage_syntheses_task(limit=None):
    """Enqueue synthesis for homepage-visible clusters missing or stale summaries."""
    from core.config import HOMEPAGE_SYNTHESIS_PRIORITIZE_LIMIT, HOMEPAGE_SYNTHESIS_QUEUE_HEADROOM
    from routes.news import fetch_news_data
    from tasks.intelligence.synthesis import synthesize_cluster_task, synthesize_urgent_task
    from tasks.utils import fast_track_dispatches_deferred, maintenance_dispatches_deferred, safe_async_run

    if maintenance_dispatches_deferred():
        log.info("[maintenance] Skipping homepage synthesis prioritization while maintenance queue is congested.")
        return {"skipped": True, "reason": "maintenance_backlog"}

    synthesis_depth = _synthesis_queue_depth()
    synthesis_deferred = _synthesis_dispatch_deferred()
    fast_track_congested = fast_track_dispatches_deferred()
    if synthesis_deferred and fast_track_congested:
        log.info("[maintenance] Skipping homepage synthesis prioritization while synthesis and fast-track are congested.")
        return {
            "skipped": True,
            "reason": "synthesis_and_fast_track_backlog",
            "synthesis_depth": synthesis_depth,
        }

    # Use fast-track only as a fallback when synthesis is backed up but fast-track still has headroom.
    use_fast_track = synthesis_deferred and not fast_track_congested
    batch_limit = HOMEPAGE_SYNTHESIS_PRIORITIZE_LIMIT if limit is None else int(limit)
    dispatch_limit = max(1, batch_limit)
    if not use_fast_track:
        queue_headroom = max(1, HOMEPAGE_SYNTHESIS_QUEUE_HEADROOM - synthesis_depth)
        dispatch_limit = min(dispatch_limit, queue_headroom)
        if dispatch_limit <= 0:
            return {"skipped": True, "reason": "no_headroom", "synthesis_depth": synthesis_depth}

    targets = _collect_homepage_synthesis_targets()
    hero_ids = _collect_homepage_hero_cluster_ids()
    seen = set(targets)
    if not _homepage_synthesis_only():
        for lang in ("sr", "mk"):
            payload = safe_async_run(lambda: fetch_news_data(sort="score", page_size=24, lang=lang)) or {}
            for cluster in payload.get("clusters") or []:
                cluster_id = str(cluster.get("cluster_id") or "").strip()
                if not cluster_id or cluster_id in seen or not _cluster_needs_synthesis(cluster):
                    continue
                seen.add(cluster_id)
                targets.append(cluster_id)

    enqueued = 0
    for idx, cluster_id in enumerate(targets[:dispatch_limit]):
        use_hero_fast_track = cluster_id in hero_ids and not fast_track_congested
        if use_hero_fast_track or use_fast_track:
            synthesize_urgent_task.apply_async(
                (cluster_id, None),
                countdown=idx * 5,
                queue="fast-track",
            )
        else:
            synthesize_cluster_task.apply_async(
                (cluster_id, None),
                {"fast_mode": False},
                countdown=idx * 15,
                queue="synthesis",
            )
        enqueued += 1

    if enqueued:
        log.info(
            "[maintenance] Enqueued homepage-priority synthesis for %s clusters (fast_track=%s)",
            enqueued,
            use_fast_track,
        )
    return {
        "enqueued": enqueued,
        "candidates": len(targets),
        "synthesis_depth": synthesis_depth,
        "fast_track": use_fast_track,
    }


@maintenance_task(soft_time_limit=120, time_limit=180)
def boost_homepage_cluster_supply_task(hours=36, recluster_limit=600, repair_limit=800):
    """Queue recluster/repair work for homepage supply without blocking maintenance workers."""
    from core.limits import INTEL_QUEUE_SECONDARY_DEFER_LIMIT
    from tasks.intelligence.cluster_ops import recluster_recent_articles_task, repair_split_clusters_task
    from tasks.intelligence import intelligence_batches_deferred
    from tasks.utils import acquire_task_lock, get_celery_queue_depth, pipeline_backpressure_active

    if pipeline_backpressure_active() or intelligence_batches_deferred():
        log.info("[maintenance] Skipping homepage cluster supply boost while pipeline backlog is high.")
        return {"skipped": True, "reason": "backlog_full"}

    intel_depth = int(get_celery_queue_depth("intel-heavy") or 0)
    if intel_depth >= INTEL_QUEUE_SECONDARY_DEFER_LIMIT:
        log.info(
            "[maintenance] Skipping homepage cluster supply boost while intel-heavy depth is %s",
            intel_depth,
        )
        return {"skipped": True, "reason": "intel_busy", "intel_depth": intel_depth}

    lock_key = "lock:boost_homepage_cluster_supply"
    if not acquire_task_lock(lock_key, 3600):
        return {"skipped": True, "reason": "already_running", "intel_depth": intel_depth}

    recluster_recent_articles_task.apply_async(
        kwargs={"hours": int(hours), "limit": int(recluster_limit)},
        queue="intel-heavy",
    )
    repair_split_clusters_task.apply_async(
        kwargs={"hours": int(hours), "limit": int(repair_limit), "dry_run": False},
        queue="intel-heavy",
    )
    log.info(
        "[maintenance] Dispatched homepage cluster supply boost (intel_depth=%s)",
        intel_depth,
    )
    return {"dispatched": True, "intel_depth": intel_depth}


@maintenance_task
def refresh_low_score_syntheses_task(min_score=None, limit=None):
    """Re-run full synthesis for recent low-scoring cluster summaries."""
    from core.limits import LOW_SCORE_SYNTHESIS_MIN, LOW_SCORE_SYNTHESIS_REFRESH_LIMIT
    from tasks.intelligence import synthesize_cluster_task

    if _synthesis_dispatch_deferred():
        log.info("[maintenance] Skipping low-score synthesis refresh while synthesis queue backlog is high.")
        return {"skipped": True, "reason": "synthesis_backlog"}

    score_floor = float(min_score if min_score is not None else LOW_SCORE_SYNTHESIS_MIN)
    batch_limit = max(1, int(limit or LOW_SCORE_SYNTHESIS_REFRESH_LIMIT))
    budget = _synthesis_refresh_budget_remaining()
    if budget <= 0:
        return {"skipped": True, "reason": "hourly_cap"}
    batch_limit = min(batch_limit, budget)
    rows = db.execute(
        """
        SELECT cs.cluster_id, cs.lang, cs.quality_score, COUNT(a.id) AS source_count
        FROM cluster_summaries cs
        JOIN articles a ON a.cluster_id = cs.cluster_id
        WHERE cs.quality_score IS NOT NULL
          AND cs.quality_score < %s
          AND cs.created_at >= NOW() - INTERVAL '7 days'
          AND COALESCE(cs.generation_provider, '') NOT IN ('enhanced_fallback', '')
        GROUP BY cs.cluster_id, cs.lang, cs.quality_score
        ORDER BY cs.quality_score ASC, source_count DESC, MAX(a.created_at) DESC
        LIMIT %s
        """,
        (float(score_floor), max(batch_limit * 4, batch_limit)),
        read_only=True,
    ) or []

    homepage_ids = set(_collect_homepage_layout_cluster_ids()) if _homepage_synthesis_only() else set()
    ordered_rows = rows
    if homepage_ids:
        ordered_rows = [row for row in rows if str(row["cluster_id"]) in homepage_ids]
    elif _homepage_synthesis_only():
        return {"skipped": True, "reason": "homepage_only", "candidates": 0}

    enqueued = 0
    for idx, row in enumerate(ordered_rows[:batch_limit]):
        if not _consume_synthesis_refresh_budget():
            break
        synthesize_cluster_task.apply_async(
            (row["cluster_id"], None),
            {"fast_mode": False},
            countdown=idx * 30,
            queue="synthesis",
        )
        enqueued += 1

    if enqueued:
        log.info("[maintenance] Enqueued low-score synthesis refresh for %s clusters", enqueued)
    return {"enqueued": enqueued}


@maintenance_task
def validate_cluster_images_task():
    """
    Checks the representative_image for the 100 most recent active clusters.
    If the image is broken (non-200), promotes the next best available image from cluster articles.
    """
    import httpx

    # 1. Get recent clusters
    recent_clusters = db.execute(
        """
        SELECT cluster_id, representative_image
        FROM cluster_metadata
        WHERE updated_at >= NOW() - INTERVAL '48 hours'
        ORDER BY updated_at DESC
        LIMIT 100
    """
    )

    if not recent_clusters:
        return

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PresekHealthCheck/1.0"}

    fixed_count = 0
    with httpx.Client(headers=headers, timeout=5.0, follow_redirects=True) as client:
        for cluster in recent_clusters:
            img_url = cluster.get("representative_image")
            if not img_url or not img_url.startswith("http"):
                continue

            try:
                resp = client.head(img_url)
                if resp.status_code == 200:
                    continue

                # If we get here, the image is likely broken (404, 403, etc.)
                log.info(
                    f"[maintenance] Image broken for cluster {cluster['cluster_id']}: {img_url} (Status: {resp.status_code})"
                )

                # 2. Find a fallback from the same cluster
                articles = db.execute(
                    """
                    SELECT image_url FROM articles
                    WHERE cluster_id = %s
                      AND image_url IS NOT NULL
                      AND image_url != %s
                    ORDER BY created_at DESC
                """,
                    (cluster["cluster_id"], img_url),
                )

                new_img = None
                for art in articles:
                    cand_url = art["image_url"]
                    if not cand_url or not cand_url.startswith("http"):
                        continue
                    try:
                        c_resp = client.head(cand_url)
                        if c_resp.status_code == 200:
                            new_img = cand_url
                            break
                    except Exception as e:
                        # Network error, try next candidate
                        log.debug(f"Failed to check image URL {cand_url}: {e}")
                        continue

                if new_img:
                    db.execute(
                        "UPDATE cluster_metadata SET representative_image = %s WHERE cluster_id = %s",
                        (new_img, cluster["cluster_id"]),
                        fetch=False,
                    )
                    log.info(f"[maintenance] Fixed cluster {cluster['cluster_id']} with new image: {new_img}")
                    fixed_count += 1
                else:
                    # No good images found, set to NULL so it uses brand fallback
                    db.execute(
                        "UPDATE cluster_metadata SET representative_image = NULL WHERE cluster_id = %s",
                        (cluster["cluster_id"],),
                        fetch=False,
                    )

            except Exception as e:
                log.warning(f"[maintenance] Failed to check image {img_url}: {e}")

    if fixed_count > 0:
        invalidate_public_data_caches()

    return f"Checked {len(recent_clusters)} clusters, fixed {fixed_count} images."


@maintenance_task
def repair_knowledge_graph_task():
    """Merges fragmented entities and cleans up noise in the knowledge graph."""
    from core.entities import normalize_entity_name

    try:
        log.info("[maintenance] Starting knowledge graph repair...")
        # 1. Fetch all entities
        rows = db.execute("SELECT name, total_mentions, sentiment_score, type FROM knowledge_entities")
        if not rows:
            return "No entities to repair."

        canonical_map = {}
        aliases_map = {}
        for r in rows:
            name = r["name"]
            total = r["total_mentions"]
            sentiment = r["sentiment_score"]
            etype = r["type"]
            canonical = normalize_entity_name(name)

            if canonical not in canonical_map:
                canonical_map[canonical] = {
                    "mentions": total,
                    "sentiment_sum": sentiment * total,
                    "type": etype,
                }
            else:
                canonical_map[canonical]["mentions"] += total
                canonical_map[canonical]["sentiment_sum"] += sentiment * total
                if etype in ("PERSON", "ORG", "LOC") and canonical_map[canonical]["type"] == "ENTITY":
                    canonical_map[canonical]["type"] = etype

            if name != canonical:
                if canonical not in aliases_map:
                    aliases_map[canonical] = []
                aliases_map[canonical].append(name)

        merged_total = 0
        for canonical, data in canonical_map.items():
            if data["mentions"] == 0:
                continue

            # Find all aliases that resolve to this canonical
            aliases = aliases_map.get(canonical, [])

            # Always update/insert canonical first to ensure it exists for FKs
            final_sentiment = data["sentiment_sum"] / data["mentions"]
            db.execute(
                """
                INSERT INTO knowledge_entities (name, type, total_mentions, last_seen, sentiment_score)
                VALUES (%s, %s, %s, NOW(), %s)
                ON CONFLICT (name) DO UPDATE SET
                    total_mentions = EXCLUDED.total_mentions,
                    sentiment_score = EXCLUDED.sentiment_score,
                    type = EXCLUDED.type
            """,
                (canonical, data["type"], data["mentions"], final_sentiment),
                fetch=False,
            )

            if not aliases:
                continue

            for alias in aliases:
                # Merge relationships safely
                rel_rows = db.execute(
                    "SELECT entity_a, entity_b, weight, last_seen FROM knowledge_relationships WHERE entity_a = %s OR entity_b = %s",
                    (alias, alias),
                )
                for rel in rel_rows:
                    a, b = rel["entity_a"], rel["entity_b"]
                    new_a = canonical if a == alias else a
                    new_b = canonical if b == alias else b
                    if new_a == new_b:
                        continue
                    new_a, new_b = sorted([new_a, new_b])

                    db.execute(
                        """
                        INSERT INTO knowledge_relationships (entity_a, entity_b, weight, last_seen)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (entity_a, entity_b) DO UPDATE SET
                            weight = knowledge_relationships.weight + EXCLUDED.weight,
                            last_seen = GREATEST(knowledge_relationships.last_seen, EXCLUDED.last_seen)
                    """,
                        (new_a, new_b, rel["weight"], rel["last_seen"]),
                        fetch=False,
                    )

                # Delete alias relationships before the entity to satisfy FKs
                db.execute(
                    "DELETE FROM knowledge_relationships WHERE entity_a = %s OR entity_b = %s",
                    (alias, alias),
                    fetch=False,
                )
                # Now safe to delete alias entity
                db.execute(
                    "DELETE FROM knowledge_entities WHERE name = %s",
                    (alias,),
                    fetch=False,
                )
                merged_total += 1

        # 3. Noise cleanup (Must delete relationships first)
        noise_entities = db.execute(
            "SELECT name FROM knowledge_entities WHERE name ~* ' (vece|kako|sami|samite|bile|ima|bese)$'"
        )
        if noise_entities:
            noise_names = [n["name"] for n in noise_entities]
            db.execute(
                "DELETE FROM knowledge_relationships WHERE entity_a = ANY(%s) OR entity_b = ANY(%s)",
                (noise_names, noise_names),
                fetch=False,
            )
            db.execute(
                "DELETE FROM knowledge_entities WHERE name = ANY(%s)",
                (noise_names,),
                fetch=False,
            )
            log.info(f"[maintenance] Cleaned up {len(noise_names)} noisy entities.")

        # Apply exponential decay to relationship weights based on days since last seen
        # w_t = w_{t-1} * EXP(-0.05 * days_passed)
        try:
            db.execute(
                """
                UPDATE knowledge_relationships
                SET weight = weight * EXP(-0.05 * EXTRACT(DAY FROM NOW() - last_seen))
                WHERE last_seen < NOW() - INTERVAL '1 day'
                """,
                fetch=False,
            )
            # Prune extremely weak relationships (e.g. weight < 0.20)
            db.execute(
                "DELETE FROM knowledge_relationships WHERE weight < 0.20",
                fetch=False,
            )
            log.info("[maintenance] Applied exponential weight decay and pruned weak relationships.")
        except Exception as decay_err:
            log.warning(f"[maintenance] Weight decay/pruning failed: {decay_err}")

        log.info(f"[maintenance] Merged {merged_total} fragmented entities.")
        return f"Repaired {merged_total} entities and cleaned up noise."
    except Exception as e:
        log.error(f"[maintenance] Knowledge graph repair failed: {e}", exc_info=True)
        return str(e)


@maintenance_task
def prune_system_logs_and_releases():
    """Prunes logs older than 30 days and removes old deployments."""
    import time
    from pathlib import Path

    # 1. Prune Logs
    log_dir = Path(_ROOT) / "logs"
    if log_dir.exists():
        now = time.time()
        for f in log_dir.glob("*.log*"):
            if f.stat().st_mtime < now - (30 * 86400):
                log.info(f"[maintenance] Deleting old log: {f}")
                f.unlink()

    # 2. Prune old releases (keep latest 5)
    app_root = Path(os.environ.get("APP_ROOT", "/home/emiloffingen/presek-runtime"))
    releases_dir = app_root / "releases"
    if releases_dir.exists():
        all_releases = sorted(
            [d for d in releases_dir.iterdir() if d.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        for old_rel in all_releases[5:]:
            log.info(f"[maintenance] Deleting old release: {old_rel}")
            import shutil
            shutil.rmtree(old_rel)
