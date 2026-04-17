import logging
import asyncio
from celery_app import celery_app
from database import db_manager as db, prune_db
from image_service import image_service
from tasks.utils import log

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
        from ai_engine import cleanup_cover_art
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
def refresh_global_headlines_task():
    """Fetches top global headlines (English) and caches their embeddings for comparison."""
    import feedparser
    import httpx
    import json
    from embeddings import generate_query_embedding
    from utils import redis_client
    
    FEEDS = [
        "https://www.reutersagency.com/feed/?best-topics=world-news&post_type=best",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "http://feeds.bbci.co.uk/news/world/rss.xml"
    ]
    
    log.info("[maintenance] Refreshing global headlines cache...")
    all_heads = []
    
    try:
        with httpx.Client(timeout=15.0) as client:
            for url in FEEDS:
                try:
                    resp = client.get(url)
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:15]:
                        title = entry.title
                        vec = generate_query_embedding(title)
                        if vec:
                            all_heads.append({"title": title, "vec": vec})
                except Exception as e:
                    log.warning(f"[maintenance] Failed to fetch global feed {url}: {e}")
        
        if all_heads:
            redis_client.setex("presek:global_headlines:v1", 7200, json.dumps(all_heads))
            log.info(f"[maintenance] Cached {len(all_heads)} global headlines.")
            
    except Exception as e:
        log.error(f"[maintenance] refresh_global_headlines failed: {e}")
