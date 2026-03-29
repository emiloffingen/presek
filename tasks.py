import logging
import datetime
from celery_app import celery_app
from ingestion import ingest_feeds, ingest_diaspora_feeds
from database import prune_db
from ai_engine import translate_to_macedonian, auto_summarize_top_clusters, _call_ai, clean_json_response
from database import get_db
from prompts import CATEGORIZATION_SYSTEM_PROMPT
from categories import ALLOWED_CATEGORIES
from health import record_refresh

log = logging.getLogger("presek_celery")

@celery_app.task
def run_ingestion():
    """Periodic task to ingest regular and diaspora feeds."""
    log.info("Starting regular feed ingestion...")
    new_count, errors = ingest_feeds()
    
    log.info("Starting diaspora feed ingestion...")
    d_count, d_errors = ingest_diaspora_feeds()
    
    # Update health monitoring
    record_refresh(new_count + d_count, errors + d_errors)
    
    log.info("Starting recategorization for suspect clusters...")
    recategorize_clusters_task.delay()
    
    log.info("Starting auto-summarization...")
    from utils import rank_articles_in_cluster, score_cluster
    auto_summarize_top_clusters(rank_articles_in_cluster, score_cluster)
    
    log.info("Checking for breaking news to notify...")
    try:
        from notifier import BreakingNewsNotifier
        from config import NTFY_TOPIC, BREAKING_SCORE_THRESHOLD
        from collections import defaultdict
        
        notifier = BreakingNewsNotifier(topic=NTFY_TOPIC, threshold=3)
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=1)
        rows = conn.execute("SELECT * FROM articles WHERE created_at >= %s", (cutoff,)).fetchall()
        conn.close()
        
        if rows:
            clusters_map = defaultdict(list)
            for r in rows:
                clusters_map[r["cluster_id"]].append(dict(r))
            
            for cid, arts in clusters_map.items():
                sorted_arts = rank_articles_in_cluster(arts)
                score = score_cluster(sorted_arts)
                unique_sources = len({a["source"] for a in sorted_arts})
                
                if score >= BREAKING_SCORE_THRESHOLD or unique_sources >= 3:
                    notifier.notify(sorted_arts[0]["title"], unique_sources, cid)
    except Exception as e:
        log.error(f"Notification check failed: {e}")
    
    log.info("Finished ingestion cycle.")

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
def send_daily_digest_task():
    """
    Periodic task to send a daily digest of the top stories to ntfy and email subscribers.
    """
    from digest import fetch_top_stories, send_ntfy_digest, render_html, send_email, mk_date
    from config import NTFY_TOPIC, DB_PATH
    import os
    
    log.info("Generating and sending daily digest...")
    try:
        # Fetch top stories for the last 24 hours
        stories_by_cat = fetch_top_stories(DB_PATH, days=1, per_category=3)
        if not stories_by_cat:
            log.warning("No stories found for the daily digest.")
            return

        # 1. Send via ntfy
        send_ntfy_digest(stories_by_cat, NTFY_TOPIC, period_days=1)
        
        # 2. Send via Email if SMTP is configured
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASS")
        
        if smtp_user and smtp_pass:
            now = datetime.datetime.now()
            start = now - datetime.timedelta(days=1)
            html = render_html(stories_by_cat, start, now)
            subject = f"Пресек — Дневен преглед {mk_date(start)} — {mk_date(now)}"
            
            conn = get_db()
            subs = conn.execute("SELECT email FROM subscribers").fetchall()
            conn.close()
            
            for sub in subs:
                send_email(html, subject, smtp_user, smtp_pass, sub["email"])
                
    except Exception as e:
        log.error(f"Daily digest task failed: {e}")

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
