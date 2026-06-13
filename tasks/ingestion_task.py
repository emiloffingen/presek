import os
import sys

import httpx

# Ensure project root is in path for Celery workers
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from celery import chain, group

from core.celery_app import celery_app
from core.crawler import crawler
from core.database import db_manager as db
from core.health import record_refresh, record_task_event
from core.image_service import image_service
from core.services.notifier import SystemNotifier as Notifier
from core.version import APP_VERSION_LABEL
from tasks.utils import (
    invalidate_public_data_caches,
    invalidate_public_data_caches_debounced,
    log,
    redis_client,
    safe_async_run,
)

# Whitelist of allowed columns for dynamic UPDATE to prevent SQL injection
_ALLOWED_ARTICLE_COLUMNS = {"full_content", "image_url"}


@celery_app.task(rate_limit="100/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def crawl_article_task(article_id, url):
    """
    Main crawler orchestrator.
    Triggers content crawling and, if successful, queues image processing and cache invalidation.
    """
    try:
        res = safe_async_run(crawler.extract_all(url))
        if res.get("error"):
            log.warning(f"Crawl failed for article {article_id}: {res['error']}")
            return

        # Build UPDATE query using whitelist to prevent SQL injection
        updates = []
        params = []

        # Only allow whitelisted columns
        column_mappings = {
            "content": "full_content",
            "image_url": "image_url",
        }

        for crawler_key, db_column in column_mappings.items():
            if res.get(crawler_key) and db_column in _ALLOWED_ARTICLE_COLUMNS:
                updates.append(f"{db_column} = %s")
                params.append(res[crawler_key])

        image_url = res.get("image_url")

        if updates:
            params.append(article_id)
            sql = f"UPDATE articles SET {', '.join(updates)} WHERE id = %s"
            db.execute(sql, tuple(params), fetch=False)
            log.info(f"Updated article {article_id} with crawled content.")

            # Post-crawl pipeline
            post_crawl_tasks = []
            if image_url:
                post_crawl_tasks.append(process_article_image_task.signature(args=(article_id, image_url)))

            if res.get("content"):
                post_crawl_tasks.append(post_crawl_invalidation_task.signature(args=(article_id,)))

            if post_crawl_tasks:
                if len(post_crawl_tasks) > 1:
                    group(post_crawl_tasks).apply_async()
                else:
                    post_crawl_tasks[0].apply_async()
        else:
            log.warning(f"Crawler retrieved no content for {article_id}")

    except Exception as e:
        log.error(f"Error in crawl_article_task for {article_id}: {e}")
        Notifier.send_alert(
            "CRAWL_FAILURE",
            f"Article {article_id} failed: {e}",
            {"article_id": article_id},
        )
        raise


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_article_image_task(article_id, image_url):
    """Processes and locally caches an article image."""
    try:
        local_path = safe_async_run(image_service.process_and_save(image_url, article_id))
        if local_path:
            db.execute(
                "UPDATE articles SET local_image_path = %s WHERE id = %s",
                (local_path, article_id),
                fetch=False,
            )
            log.info(f"Processed local image for article {article_id}")
    except Exception as e:
        log.error(f"Failed to process image for {article_id}: {e}")
        raise


@celery_app.task
def post_crawl_invalidation_task(article_id):
    """Handles cache invalidation after a successful crawl."""
    if invalidate_public_data_caches_debounced():
        log.debug(f"Invalidated caches for article {article_id}")


@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def run_ingestion():
    """
    Main ingestion orchestrator.
    Serialized for efficiency and to prevent DB/API bottlenecks.
    A short Redis mutex prevents two workers from racing the same cycle
    when beat double-dispatches across a restart.
    """
    lock_key = "lock:run_ingestion"
    try:
        acquired = redis_client.set(lock_key, "1", nx=True, ex=900)
    except Exception as e:
        log.error(f"[ingestion] Redis lock check failed, skipping cycle for safety: {e}")
        Notifier.send_alert("INGESTION_LOCK_FAILURE", f"Redis lock check failed: {e}")
        return  # Fail-closed: better to skip a minute than crash the DB
    if not acquired:
        log.info(f"Presek {APP_VERSION_LABEL}: ingestion cycle already in flight, skipping duplicate dispatch.")
        return
    try:
        from core.ingestion import ingest_feeds

        log.info(f"Presek {APP_VERSION_LABEL}: Starting unified ingestion cycle...")
        new_count, inserted_ids, errors = ingest_feeds()

        # Record health metrics
        record_refresh(new_count, errors)
        record_task_event(
            "run_ingestion",
            "ok" if not errors else "warning",
            f"new_articles:{new_count}",
        )

        if new_count > 0 and inserted_ids:
            invalidate_public_data_caches()

            # Extract modified cluster IDs for targeted updates
            # We fetch from DB to get cluster_ids for all inserted articles
            inserted_data = db.execute("SELECT cluster_id FROM articles WHERE id = ANY(%s)", (inserted_ids,))
            modified_cluster_ids = list(set(art["cluster_id"] for art in inserted_data if art.get("cluster_id")))
            # Lazy import to avoid circular dependencies
            from tasks.intelligence import (
                auto_summarize_task,
                classify_topics_task,
                extract_entities_task,
                generate_cluster_metadata_task,
                generate_embeddings_task,
                recategorize_clusters_task,
            )

            # Create a chain of post-ingestion tasks
            # This ensures they run sequentially immediately after ingestion completes.
            # Use .si() for immutable signatures to prevent passing previous task results
            # into tasks that expect zero arguments.
            ingestion_chain = chain(
                generate_embeddings_task.si(),
                generate_cluster_metadata_task.si(),
                classify_topics_task.si(),
                extract_entities_task.si(),
                recategorize_clusters_task.si(),
                auto_summarize_task.si(cluster_ids=modified_cluster_ids),
            )
            ingestion_chain.apply_async()

        log.info(f"Ingestion cycle orchestrated. Added {new_count} articles.")
    finally:
        # Release the mutex so the next beat can run immediately rather than
        # waiting for the 15-minute TTL.
        try:
            redis_client.delete(lock_key)
        except Exception as e:
            log.debug(f"Failed to delete lock {lock_key}: {e}")


@celery_app.task
def auto_repair_sources_task():
    """
    Identifies paused sources and dispatches individual repair tasks.
    """
    try:
        paused_sources = db.execute("SELECT name FROM sources WHERE is_active = FALSE AND pause_mode = 'auto'")
        for source in paused_sources:
            repair_single_source_task.delay(source["name"])
    except Exception as e:
        log.error(f"[tasks] Auto-repair dispatch failed: {e}")
        Notifier.send_alert("AUTO_REPAIR_FAILURE", f"Failed to dispatch repairs: {e}")


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def repair_single_source_task(name):
    """Attempts to find a new feed for a single paused source."""
    try:
        source_data = db.execute_one("SELECT url FROM sources WHERE name = %s", (name,))
        if not source_data:
            return

        current_url = source_data["url"]
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(current_url)
        homepage = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))

        log.info(f"Attempting to repair source '{name}' via {homepage}")
        potential_feeds = safe_async_run(crawler.find_feeds(homepage))

        import feedparser

        for feed_url in potential_feeds:
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(feed_url, follow_redirects=True)
                    if resp.status_code == 200:
                        f = feedparser.parse(resp.content)
                        if not f.bozo and len(f.entries) > 0:
                            log.info(f"Source '{name}' repaired with new URL: {feed_url}")
                            db.execute(
                                """UPDATE sources
                                   SET url = %s, is_active = TRUE, pause_mode = NULL, pause_reason = NULL, paused_at = NULL
                                   WHERE name = %s""",
                                (feed_url, name),
                                fetch=False,
                            )
                            from core.health import reset_source_policy

                            reset_source_policy(name)
                            return
            except Exception as e:
                log.debug(f"Validation failed for candidate {feed_url}: {e}")

        log.warning(f"Could not repair source '{name}' after checking candidates.")
    except Exception as e:
        log.error(f"[tasks] Repair failed for {name}: {e}")
        raise
