import logging
from celery_app import celery_app
from ingestion import ingest_feeds, ingest_diaspora_feeds
from database import prune_db
from ai_engine import translate_to_macedonian, auto_summarize_top_clusters
from database import get_db

log = logging.getLogger("presek_celery")

@celery_app.task
def run_ingestion():
    """Periodic task to ingest regular and diaspora feeds."""
    log.info("Starting regular feed ingestion...")
    ingest_feeds()
    log.info("Finished regular feed ingestion.")
    
    log.info("Starting diaspora feed ingestion...")
    ingest_diaspora_feeds()
    log.info("Finished diaspora feed ingestion.")
    
    log.info("Starting auto-summarization...")
    auto_summarize_top_clusters()
    log.info("Finished auto-summarization.")

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
