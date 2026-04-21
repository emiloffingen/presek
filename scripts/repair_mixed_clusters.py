import os
import sys
import logging
import json

# Ensure project root is in path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database import db_manager as db
import clustering

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("repair_clusters")

def run_repair():
    # 1. Fetch all pending articles
    log.info("Fetching articles marked as 'pending'...")
    pending_articles = db.execute("""
        SELECT id, title, source, category, topic, created_at, embedding 
        FROM articles 
        WHERE cluster_id = 'pending'
        ORDER BY created_at ASC
    """)
    
    if not pending_articles:
        log.info("No pending articles found.")
        return

    log.info(f"Found {len(pending_articles)} articles to re-cluster.")

    # 2. Fetch truly recent articles (last 48h) to use as cluster candidates
    # This prevents creating duplicate clusters for things that already exist
    log.info("Fetching recent context articles...")
    recent_articles = db.execute("""
        SELECT id, title, source, category, topic, created_at, cluster_id
        FROM articles 
        WHERE created_at >= NOW() - INTERVAL '48 hours'
          AND cluster_id != 'pending'
          AND cluster_id IS NOT NULL
    """)
    
    # Pre-parse embeddings for pending articles
    for a in pending_articles:
        if isinstance(a['embedding'], str):
            a['embedding'] = json.loads(a['embedding'])

    conn = db.get_conn()
    try:
        updated_count = 0
        for art in pending_articles:
            new_cid = clustering.find_or_create_cluster(
                conn, 
                art['title'], 
                recent_articles,
                embedding=art['embedding'],
                category=art['category'],
                source=art['source'],
                topic=art['topic']
            )
            
            # Update in DB
            db.execute("UPDATE articles SET cluster_id = %s WHERE id = %s", (new_cid, art['id']), fetch=False)
            
            # Add to local 'recent' context so subsequent pending articles can join these new clusters
            recent_articles.append({
                "id": art["id"],
                "title": art["title"],
                "source": art["source"],
                "category": art["category"],
                "topic": art["topic"],
                "created_at": art["created_at"],
                "cluster_id": new_cid
            })
            updated_count += 1
            if updated_count % 100 == 0:
                log.info(f"Progress: {updated_count}/{len(pending_articles)}...")

        log.info(f"Successfully re-clustered {updated_count} articles.")
    finally:
        db.put_conn(conn)

if __name__ == "__main__":
    run_repair()
