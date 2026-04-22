import logging
import asyncio
import httpx
import os
import sys

# Ensure project root is in path for Celery workers
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from celery_app import celery_app
from database import db_manager as db
from crawler import crawler
from image_service import image_service
from health import record_refresh, record_task_event
from tasks.utils import invalidate_public_data_caches, redis_client, log, safe_async_run

@celery_app.task(rate_limit='20/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def crawl_article_task(article_id, url):
    """
    Background crawler task.
    Fetches full content and high-res images for an article.
    """
    try:
        # Use our new resilient crawler
        res = safe_async_run(crawler.extract_all(url))
        
        if res.get("error"):
            log.warning(f"Crawl failed for article {article_id}: {res['error']}")
            return

        updates = []
        params = []
        
        if res.get("content"):
            updates.append("full_content = %s")
            params.append(res["content"])
            
        final_image_url = res.get("image_url")
        if final_image_url:
            # Prefer the high-res image discovered by the crawler
            updates.append("image_url = %s")
            params.append(final_image_url)

            # 2. Process and save a local version for the lightning-fast proxy
            local_path = safe_async_run(image_service.process_and_save(final_image_url, article_id))
            if local_path:
                updates.append("local_image_path = %s")
                params.append(local_path)
            
        if updates:
            params.append(article_id)
            sql = f"UPDATE articles SET {', '.join(updates)} WHERE id = %s"
            db.execute(sql, tuple(params), fetch=False)
            log.info(f"Updated article {article_id} with crawled data (method: {res.get('method')})")
            
            # Invalidate cache if we got new content
            invalidate_public_data_caches()
            
    except Exception as e:
        log.error(f"Error in crawl_article_task for {article_id}: {e}")
        raise

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
        return # Fail-closed: better to skip a minute than crash the DB
    if not acquired:
        log.info("Presek 4.0: ingestion cycle already in flight, skipping duplicate dispatch.")
        return
    try:
        from ingestion import ingest_feeds
        log.info("Presek 4.0: Starting unified ingestion cycle...")
        new_count, errors = ingest_feeds()

        # Record health metrics
        record_refresh(new_count, errors)
        record_task_event("run_ingestion", "ok" if not errors else "warning", f"new_articles:{new_count}")
        if new_count > 0:
            invalidate_public_data_caches()

        if new_count > 0:
            # Lazy import to avoid circular dependencies
            from tasks.intelligence import (
                generate_embeddings_task,
                generate_cluster_metadata_task,
                classify_topics_task,
                extract_entities_task,
                recategorize_clusters_task,
                auto_summarize_task
            )
            # Dispatch post-ingestion tasks individually so a failure in one
            # doesn't block the rest (unlike a chain where errors halt propagation).
            generate_embeddings_task.apply_async(countdown=2)
            generate_cluster_metadata_task.apply_async(countdown=30)
            classify_topics_task.apply_async(countdown=60)
            extract_entities_task.apply_async(countdown=90)
            recategorize_clusters_task.apply_async(countdown=120)
            auto_summarize_task.apply_async(countdown=150)

        log.info(f"Ingestion cycle orchestrated. Added {new_count} articles.")
    finally:
        # Release the mutex so the next beat can run immediately rather than
        # waiting for the 15-minute TTL.
        try:
            redis_client.delete(lock_key)
        except Exception:
            pass

@celery_app.task
def auto_repair_sources_task():
    """
    Looks for sources that have been auto-paused due to errors
    and attempts to find new RSS feeds on their homepages.
    """
    try:
        # Find sources that are inactive and were auto-paused
        paused_sources = db.execute(
            "SELECT name, url FROM sources WHERE is_active = FALSE AND pause_mode = 'auto'"
        )
        if not paused_sources:
            return

        for source in paused_sources:
            name = source['name']
            current_url = source['url']
            
            # Try to derive a homepage from the feed URL
            from urllib.parse import urlsplit, urlunsplit
            parts = urlsplit(current_url)
            homepage = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
            
            log.info(f"Attempting to repair source '{name}' via {homepage}")
            
            # 1. Find potential feeds
            potential_feeds = safe_async_run(crawler.find_feeds(homepage))
            
            found_valid = False
            for feed_url in potential_feeds:
                # 2. Validate feed
                try:
                    import feedparser
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.get(feed_url, follow_redirects=True)
                        if resp.status_code == 200:
                            f = feedparser.parse(resp.content)
                            if not f.bozo and len(f.entries) > 0:
                                # Found a working feed!
                                log.info(f"Source '{name}' repaired with new URL: {feed_url}")
                                db.execute(
                                    """UPDATE sources 
                                       SET url = %s, is_active = TRUE, pause_mode = NULL, pause_reason = NULL, paused_at = NULL
                                       WHERE name = %s""",
                                    (feed_url, name), fetch=False
                                )
                                from health import reset_source_policy
                                reset_source_policy(name)
                                found_valid = True
                                break
                except Exception as e:
                    log.debug(f"Validation failed for candidate {feed_url}: {e}")
                    
            if not found_valid:
                log.warning(f"Could not repair source '{name}' after checking {len(potential_feeds)} candidates.")
                
    except Exception as e:
        log.error(f"[tasks] Auto-repair failed: {e}")
