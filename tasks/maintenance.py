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


@maintenance_task
def run_prune_db():
    """Standard maintenance."""
    try:
        prune_db()
    except Exception as e:
        log.error(f"[tasks] prune_db failed: {e}", exc_info=True)

    try:
        # Clean up orphaned local images and logs
        art_rows = db.execute("SELECT id FROM articles")
        active_art_ids = {int(r["id"]) for r in art_rows}
        asyncio.run(image_service.cleanup_storage(active_art_ids))
    except Exception as e:
        log.error(f"[tasks] cleanup_storage failed: {e}", exc_info=True)


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
    from core.health import _freshness_payload, load_last_refresh_time
    from core.ingestion_lock import break_stale_ingestion_lock, is_ingestion_in_flight
    from tasks.ingestion_task import run_ingestion

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
def validate_cluster_images_task():
    """
    Checks the representative_image for the 100 most recent active clusters.
    If the image is broken (non-200) or weak, promotes the next best available image from cluster articles.
    """
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

    stats = repair_cluster_representative_images(recent_clusters)
    if stats["replaced"] or stats["cleared"]:
        invalidate_public_data_caches()

    return f"Checked {stats['checked']} clusters, replaced {stats['replaced']}, cleared {stats['cleared']} images."


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
            [d for d in releases_dir.iterdir() if d.is_dir()], key=lambda x: x.stat().st_mtime, reverse=True
        )
        for old_rel in all_releases[5:]:
            log.info(f"[maintenance] Deleting old release: {old_rel}")
            import shutil

            shutil.rmtree(old_rel)


def repair_cluster_representative_images(
    clusters,
    *,
    check_reachability: bool = True,
    dry_run: bool = False,
) -> dict[str, int]:
    import httpx

    from nlp.image_quality import classify_image_url

    stats = {"checked": 0, "replaced": 0, "cleared": 0, "unchanged": 0, "skipped": 0}
    if not clusters:
        return stats

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PresekHealthCheck/1.0"}
    with httpx.Client(headers=headers, timeout=5.0, follow_redirects=True) as client:
        for cluster in clusters:
            stats["checked"] += 1
            img_url = cluster.get("representative_image")
            if not img_url:
                stats["skipped"] += 1
                continue

            if classify_image_url(img_url)[0] == "ok" and not check_reachability:
                stats["unchanged"] += 1
                continue

            outcome = repair_cluster_representative_image(
                client,
                cluster["cluster_id"],
                img_url,
                check_reachability=check_reachability,
                dry_run=dry_run,
            )
            stats[outcome] = stats.get(outcome, 0) + 1

    return stats


def repair_cluster_representative_image(
    client,
    cluster_id: str,
    img_url: str | None,
    *,
    check_reachability: bool = True,
    dry_run: bool = False,
) -> str:
    from nlp.image_quality import classify_image_url, pick_best_image_url

    if not img_url:
        return "skipped"

    quality, _reason = classify_image_url(img_url)
    needs_replacement = quality != "ok"
    if not needs_replacement and check_reachability and img_url.startswith("http"):
        try:
            needs_replacement = not image_url_reachable(client, img_url)
        except Exception as e:
            log.warning(f"[maintenance] Failed to check image {img_url}: {e}")
            needs_replacement = True

    if not needs_replacement:
        return "unchanged"

    if img_url.startswith("http"):
        log.info(f"[maintenance] Image needs replacement for cluster {cluster_id}: {img_url} ({quality})")

    articles = db.execute(
        """
        SELECT image_url, source FROM articles
        WHERE cluster_id = %s
          AND image_url IS NOT NULL
          AND image_url != %s
        ORDER BY created_at DESC
    """,
        (cluster_id, img_url),
    )

    new_img = pick_best_image_url([(art["image_url"], art.get("source")) for art in articles or []])
    if new_img and new_img.startswith("http"):
        if not check_reachability or image_url_reachable(client, new_img):
            if not dry_run:
                db.execute(
                    "UPDATE cluster_metadata SET representative_image = %s WHERE cluster_id = %s",
                    (new_img, cluster_id),
                    fetch=False,
                )
            log.info(f"[maintenance] Fixed cluster {cluster_id} with new image: {new_img}")
            return "replaced"

    if not dry_run:
        db.execute(
            "UPDATE cluster_metadata SET representative_image = NULL WHERE cluster_id = %s",
            (cluster_id,),
            fetch=False,
        )
    log.info(f"[maintenance] Cleared weak representative image for cluster {cluster_id}")
    return "cleared"


def image_url_reachable(client, url: str) -> bool:
    try:
        resp = client.head(url)
        if resp.status_code == 200:
            return True
        if resp.status_code not in (403, 404, 405, 501):
            return False
    except Exception:
        log.debug("Maintenance task fallback")
    try:
        resp = client.get(url, headers={"Range": "bytes=0-0"})
        return resp.status_code in (200, 206)
    except Exception:
        return False
