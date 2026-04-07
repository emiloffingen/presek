import os
import logging
from database import db_manager as db
from embeddings import generate_embedding
from tasks import synthesize_cluster_task

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("backfill")

def backfill_embeddings():
    log.info("Starting embedding backfill for recent articles (last 72h)...")
    articles = db.execute("""
        SELECT id, title, description 
        FROM articles 
        WHERE created_at >= NOW() - INTERVAL '72 hours' 
          AND embedding IS NULL
    """)
    
    log.info(f"Found {len(articles)} articles missing embeddings.")
    
    updated = 0
    for i, art in enumerate(articles):
        text = f"{art['title']} {art['description']}".strip()
        emb = generate_embedding(text)
        if emb:
            db.execute("UPDATE articles SET embedding = %s WHERE id = %s", (str(emb), art['id']), fetch=False)
            updated += 1
            if updated % 100 == 0:
                log.info(f"Updated {updated} embeddings so far...")
            
    log.info(f"Successfully updated embeddings for {updated} articles.")

def backfill_cluster_summaries():
    log.info("Starting cluster synthesis backfill for top 50 recent active clusters...")
    clusters = db.execute("""
        SELECT cluster_id 
        FROM articles 
        WHERE created_at >= NOW() - INTERVAL '48 hours'
        GROUP BY cluster_id 
        HAVING COUNT(*) >= 3
        ORDER BY MAX(created_at) DESC 
        LIMIT 50
    """)
    
    log.info(f"Queueing {len(clusters)} clusters for re-synthesis...")
    
    for c in clusters:
        synthesize_cluster_task.delay(c['cluster_id'])
        
    log.info("Finished queueing cluster synthesis tasks.")

if __name__ == "__main__":
    backfill_embeddings()
    backfill_cluster_summaries()
