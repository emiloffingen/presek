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
from tasks.utils import invalidate_public_data_caches, log, prune_ingestion_queue, reprioritize_intel_queue


@celery_app.task
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


@celery_app.task
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


@celery_app.task
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


@celery_app.task
def catch_up_recent_summaries_task(hours=72, limit=200):
    """Enqueue summarize batches for recent articles missing summaries when the queue has headroom."""
    from tasks.intelligence import (
        _dispatch_batched,
        intelligence_batches_deferred,
        intelligence_secondary_deferred,
        summarize_articles_local_batch_task,
    )

    if intelligence_batches_deferred() or intelligence_secondary_deferred():
        log.info("[maintenance] Skipping recent summary catch-up while intel-heavy backlog is high.")
        return {"skipped": True, "reason": "backlog_high"}

    try:
        rows = db.execute(
            """
            SELECT id
            FROM articles
            WHERE summary IS NULL
              AND created_at >= NOW() - make_interval(hours => %s)
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, int(hours)), max(1, int(limit))),
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


@celery_app.task
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


@celery_app.task
def ensure_ingestion_freshness_task(max_age_minutes=120):
    """Trigger ingestion when the public freshness badge has gone stale."""
    from core.health import load_last_refresh_time, _freshness_payload
    from tasks.ingestion_task import run_ingestion

    from core.ingestion_lock import is_ingestion_in_flight

    prune_ingestion_queue(max_pending=1)

    freshness = _freshness_payload(load_last_refresh_time())
    age_minutes = freshness.get("age_minutes")
    if age_minutes is not None and age_minutes <= int(max_age_minutes):
        return {"skipped": True, "age_minutes": age_minutes}
    if is_ingestion_in_flight():
        return {"skipped": True, "reason": "in_flight", "age_minutes": age_minutes}

    run_ingestion.apply_async(expires=540)
    log.warning(
        "[maintenance] Triggered ingestion recovery because freshness age is %s minutes",
        age_minutes,
    )
    return {"triggered": True, "age_minutes": age_minutes}


@celery_app.task
def catch_up_cluster_syntheses_task(hours=48, limit=30):
    """Enqueue full synthesis for recent multi-source clusters missing cluster summaries."""
    from tasks.intelligence import intelligence_soft_deferred, synthesize_cluster_task

    if intelligence_soft_deferred():
        log.info("[maintenance] Skipping cluster synthesis catch-up while intel-heavy backlog is high.")
        return {"skipped": True, "reason": "backlog_high"}

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
        )
        enqueued += 1

    if enqueued:
        log.info("[maintenance] Enqueued cluster synthesis catch-up for %s clusters", enqueued)
    return {"enqueued": enqueued}


@celery_app.task
def refresh_low_score_syntheses_task(min_score=0.75, limit=20):
    """Re-run full synthesis for recent low-scoring cluster summaries."""
    from tasks.intelligence import intelligence_soft_deferred, synthesize_cluster_task

    if intelligence_soft_deferred():
        log.info("[maintenance] Skipping low-score synthesis refresh while intel-heavy backlog is high.")
        return {"skipped": True, "reason": "backlog_high"}

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
        (float(min_score), max(1, int(limit))),
        read_only=True,
    ) or []

    enqueued = 0
    for idx, row in enumerate(rows):
        synthesize_cluster_task.apply_async(
            (row["cluster_id"], None),
            {"fast_mode": False},
            countdown=idx * 30,
        )
        enqueued += 1

    if enqueued:
        log.info("[maintenance] Enqueued low-score synthesis refresh for %s clusters", enqueued)
    return {"enqueued": enqueued}


@celery_app.task
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


@celery_app.task
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


@celery_app.task
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
