"""
recluster_all.py - Global Clustering Reset for Presek 5.0
This script re-groups recent articles using the new strict similarity logic.
"""

import logging
import datetime
import uuid
from database import db_manager as db
from clustering import find_or_create_cluster
from ingestion import CLUSTER_LOOKBACK

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.recluster")

def recluster():
    log.info("Starting global re-clustering...")
    
    # 1. Fetch articles from the last 3 days
    cutoff = datetime.datetime.now() - datetime.timedelta(days=3)
    articles = db.execute(
        "SELECT id, title, category, embedding FROM articles WHERE created_at >= %s ORDER BY created_at ASC",
        (cutoff,)
    )
    
    log.info(f"Processing {len(articles)} articles...")
    
    processed_count = 0
    recent_articles = [] 

    for art in articles:
        # Generate new cluster ID using the strict logic
        new_cid = find_or_create_cluster(
            title=art['title'],
            recent_articles=recent_articles,
            embedding=art['embedding'],
            category=art['category']
        )
        
        # Update DB
        db.execute("UPDATE articles SET cluster_id = %s WHERE id = %s", (new_cid, art['id']), fetch=False)
        
        # Update local buffer for subsequent matches
        recent_articles.insert(0, {
            "title": art['title'], 
            "cluster_id": new_cid, 
            "category": art['category']
        })
        if len(recent_articles) > CLUSTER_LOOKBACK:
            recent_articles.pop()
            
        processed_count += 1
        if processed_count % 100 == 0:
            log.info(f"Processed {processed_count} articles...")

    log.info("Re-clustering complete. Pruning old summaries...")
    db.execute("DELETE FROM cluster_summaries", fetch=False)
    
    log.info("Done. The system will now regenerate summaries and cover art automatically.")

if __name__ == "__main__":
    recluster()
