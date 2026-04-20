import logging
import asyncio
from celery_app import celery_app
from database import db_manager as db, prune_db
from image_service import image_service
from tasks.utils import log, invalidate_public_data_caches

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
def validate_cluster_images_task():
    """
    Checks the representative_image for the 100 most recent active clusters.
    If the image is broken (non-200), promotes the next best available image from cluster articles.
    """
    import httpx
    
    # 1. Get recent clusters
    recent_clusters = db.execute("""
        SELECT cluster_id, representative_image 
        FROM cluster_metadata 
        WHERE updated_at >= NOW() - INTERVAL '48 hours'
        ORDER BY updated_at DESC 
        LIMIT 100
    """)
    
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
                log.info(f"[maintenance] Image broken for cluster {cluster['cluster_id']}: {img_url} (Status: {resp.status_code})")
                
                # 2. Find a fallback from the same cluster
                articles = db.execute("""
                    SELECT image_url FROM articles 
                    WHERE cluster_id = %s 
                      AND image_url IS NOT NULL 
                      AND image_url != %s
                    ORDER BY created_at DESC
                """, (cluster['cluster_id'], img_url))
                
                new_img = None
                for art in articles:
                    cand_url = art['image_url']
                    if not cand_url or not cand_url.startswith("http"): continue
                    try:
                        c_resp = client.head(cand_url)
                        if c_resp.status_code == 200:
                            new_img = cand_url
                            break
                    except: continue
                
                if new_img:
                    db.execute("UPDATE cluster_metadata SET representative_image = %s WHERE cluster_id = %s", (new_img, cluster['cluster_id']), fetch=False)
                    log.info(f"[maintenance] Fixed cluster {cluster['cluster_id']} with new image: {new_img}")
                    fixed_count += 1
                else:
                    # No good images found, set to NULL so it uses brand fallback
                    db.execute("UPDATE cluster_metadata SET representative_image = NULL WHERE cluster_id = %s", (cluster['cluster_id'],), fetch=False)
                    
            except Exception as e:
                log.warning(f"[maintenance] Failed to check image {img_url}: {e}")
                
    if fixed_count > 0:
        invalidate_public_data_caches()
        
    return f"Checked {len(recent_clusters)} clusters, fixed {fixed_count} images."

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
