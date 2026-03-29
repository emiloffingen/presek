import logging
import datetime
from celery_app import celery_app
from ingestion import ingest_feeds, ingest_diaspora_feeds
from database import prune_db
from ai_engine import translate_to_macedonian, auto_summarize_top_clusters, _call_ai, clean_json_response
from database import get_db
from prompts import CATEGORIZATION_SYSTEM_PROMPT
from categories import ALLOWED_CATEGORIES

log = logging.getLogger("presek_celery")

@celery_app.task
def run_ingestion():
    """Periodic task to ingest regular and diaspora feeds."""
    log.info("Starting regular feed ingestion...")
    ingest_feeds()
    
    log.info("Starting diaspora feed ingestion...")
    ingest_diaspora_feeds()
    
    log.info("Starting recategorization for suspect clusters...")
    recategorize_clusters_task.delay()
    
    log.info("Starting auto-summarization...")
    from utils import rank_articles_in_cluster, score_cluster
    auto_summarize_top_clusters(rank_articles_in_cluster, score_cluster)

@celery_app.task
def recategorize_clusters_task():
    """
    Background task to find 'Македонија' clusters with multiple sources 
    and ask AI if they should be in a different category.
    """
    try:
        conn = get_db()
        # Find clusters with 2+ sources currently in 'Македонија' created in last 12h
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=12)
        rows = conn.execute("""
            SELECT cluster_id, title, description 
            FROM articles 
            WHERE category = 'Македонија' 
              AND created_at >= %s
            GROUP BY cluster_id, title, description
            HAVING COUNT(cluster_id) >= 2
            LIMIT 20
        """, (cutoff,)).fetchall()
        
        if not rows:
            conn.close()
            return

        for r in rows:
            cid = r['cluster_id']
            text = f"Title: {r['title']}\nDescription: {r['description']}"
            
            new_cat, tier = _call_ai(text, CATEGORIZATION_SYSTEM_PROMPT, max_tokens=10)
            if new_cat:
                new_cat = new_cat.strip().strip('"').strip("'")
                if new_cat in ALLOWED_CATEGORIES and new_cat != 'Македонија':
                    log.info(f"[recategorize] Cluster {cid}: Македонија -> {new_cat} (via {tier})")
                    conn.execute("UPDATE articles SET category = %s WHERE cluster_id = %s", (new_cat, cid))
                    conn.commit()
        
        conn.close()
    except Exception as e:
        log.error(f"Recategorize task failed: {e}")

@celery_app.task
def run_prune_db():
    """Periodic task to prune old articles from database."""
    log.info("Pruning old database entries...")
    prune_db()

@celery_app.task
def translate_article_task(article_id: int, original_title: str, original_description: str):
    """Background task to translate diaspora articles."""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        translated_title = original_title
        if original_title:
            try:
                translated_title = translate_to_macedonian(original_title)
            except Exception as e:
                log.error(f"Translation error (title) for {article_id}: {e}")

        translated_desc = original_description
        if original_description:
            try:
                translated_desc = translate_to_macedonian(original_description)
            except Exception as e:
                log.error(f"Translation error (desc) for {article_id}: {e}")

        cur.execute(
            "UPDATE articles SET title = %s, description = %s, is_translated = 1 WHERE id = %s",
            (translated_title, translated_desc, article_id)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Task failed for article {article_id}: {e}")
