import logging
import datetime
from celery_app import celery_app
from ingestion import ingest_feeds, ingest_diaspora_feeds
from database import prune_db
from ai_engine import translate_to_macedonian, auto_summarize_top_clusters, _call_ai, clean_json_response, generate_cover_art
from database import get_db
from prompts import CATEGORIZATION_SYSTEM_PROMPT, TAGGING_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, TOPIC_SYSTEM_PROMPT, DAILY_BRIEF_SYSTEM_PROMPT, ENTITY_EXTRACTION_PROMPT
from categories import ALLOWED_CATEGORIES
from health import record_refresh

log = logging.getLogger("presek_celery")

@celery_app.task(rate_limit='10/m')
def summarize_article_task(article_id, title):
    """Asynchronously generates a summary for a single article."""
    try:
        summary, tier = _call_ai(title, SUMMARY_SYSTEM_PROMPT)
        if summary:
            summary_res = clean_json_response(summary)
            # clean_json_response might return dict for synthesis but here it should be string
            final_summary = summary_res.get('summary', str(summary_res)) if isinstance(summary_res, dict) else summary_res
            conn = get_db()
            conn.execute("UPDATE articles SET summary = %s WHERE id = %s", (final_summary, article_id))
            conn.commit()
            conn.close()
    except Exception as e:
        log.warning(f"[auto-summarize] DB write failed for article {article_id}: {e}")

@celery_app.task(rate_limit='10/m')
def synthesize_cluster_task(cluster_id, content):
    """Asynchronously generates a synthesis for a cluster with multiple perspectives."""
    try:
        raw_res, tier = _call_ai(f"Статии:\n{content}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True)
        if raw_res:
            res = clean_json_response(raw_res)
            summary = ""
            perspectives = []

            if isinstance(res, dict):
                summary = res.get('summary', '')
                perspectives = res.get('perspectives', [])
            else:
                summary = res

            now = datetime.datetime.now()
            import json as _json
            conn = get_db()
            conn.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, perspectives, created_at) 
                   VALUES (%s, %s, %s, %s) 
                   ON CONFLICT (cluster_id) DO UPDATE 
                   SET summary = EXCLUDED.summary, perspectives = EXCLUDED.perspectives, created_at = EXCLUDED.created_at""",
                (cluster_id, summary, _json.dumps(perspectives), now)
            )
            conn.commit()

            # Check if lead image is missing
            lead_row = conn.execute("SELECT id, image_url FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 1", (cluster_id,)).fetchone()
            if lead_row and not lead_row["image_url"]:
                img_url = generate_cover_art(cluster_id, summary)
                if img_url:
                    conn.execute("UPDATE articles SET image_url = %s WHERE cluster_id = %s", (img_url, cluster_id))
                    conn.commit()
            
            conn.close()
    except Exception as e:
        log.warning(f"[auto-summarize] Cluster synthesis failed for {cluster_id}: {e}")

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

    log.info("Starting metadata generation (tagging)...")
    generate_cluster_metadata_task.delay()

    log.info("Starting topical classification...")
    classify_topics_task.delay()

    log.info("Starting entity extraction...")
    extract_entities_task.delay()
    
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
def generate_daily_brief_task():
    """
    Generate a cohesive narrative summary of the top stories.
    Runs once a day (usually in the morning).
    """
    try:
        from utils import rank_articles_in_cluster, score_cluster
        from collections import defaultdict
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        
        # Get top clusters from the last 24h
        rows = conn.execute("SELECT * FROM articles WHERE created_at >= %s", (cutoff,)).fetchall()
        
        if not rows:
            conn.close()
            return

        clusters_map = defaultdict(list)
        for r in rows:
            clusters_map[r["cluster_id"]].append(dict(r))
            
        ranked = []
        for cid, arts in clusters_map.items():
            sorted_arts = rank_articles_in_cluster(arts)
            s = score_cluster(sorted_arts)
            ranked.append((cid, sorted_arts, s))
        
        ranked.sort(key=lambda x: x[2], reverse=True)
        top_5 = ranked[:5]
        
        # Collect summaries/titles for context
        brief_context = []
        for cid, arts, s in top_5:
            # Check for synthesis first
            syn = conn.execute("SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cid,)).fetchone()
            content = syn['summary'] if syn else arts[0]['title']
            brief_context.append(f"Тема {len(brief_context)+1}: {content}")
            
        context_text = "\n\n".join(brief_context)
        
        brief_text, tier = _call_ai(context_text, DAILY_BRIEF_SYSTEM_PROMPT, max_tokens=1000)
        
        if brief_text:
            today = datetime.date.today()
            conn.execute(
                "INSERT INTO daily_briefings (date, content) VALUES (%s, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content",
                (today, brief_text)
            )
            conn.commit()
            log.info(f"[daily-brief] Generated brief for {today} via {tier}")
            
        conn.close()
    except Exception as e:
        log.error(f"Daily brief generation failed: {e}")

@celery_app.task
def generate_cluster_metadata_task():
    """
    Background task to generate tags for top clusters from the last 24h.
    """
    try:
        import json
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        
        # Get clusters from last 24h that don't have metadata yet
        rows = conn.execute("""
            SELECT cluster_id, title, description 
            FROM articles 
            WHERE created_at >= %s 
              AND cluster_id NOT IN (SELECT cluster_id FROM cluster_metadata)
            GROUP BY cluster_id, title, description
            LIMIT 20
        """, (cutoff,)).fetchall()
        
        if not rows:
            conn.close()
            return

        for r in rows:
            cid = r['cluster_id']
            text = f"Title: {r['title']}\nDescription: {r['description']}"
            
            res, tier = _call_ai(text, TAGGING_SYSTEM_PROMPT, max_tokens=100)
            if res:
                try:
                    # Clean the response to ensure it's a valid JSON list
                    clean_res = res.strip().replace('```json', '').replace('```', '').strip()
                    tags = json.loads(clean_res)
                    if isinstance(tags, list):
                        conn.execute(
                            "INSERT INTO cluster_metadata (cluster_id, tags) VALUES (%s, %s) ON CONFLICT (cluster_id) DO UPDATE SET tags = EXCLUDED.tags",
                            (cid, tags)
                        )
                        conn.commit()
                except Exception as e:
                    log.warning(f"[tagging] Failed to parse tags for {cid}: {e}")
        
        conn.close()
    except Exception as e:
        log.error(f"Metadata generation task failed: {e}")

@celery_app.task
def extract_entities_task():
    """
    Background task to extract key personalities and organizations from top clusters.
    """
    try:
        import json
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        
        # Get clusters from last 24h that don't have entities yet
        rows = conn.execute("""
            SELECT cluster_id, title, description 
            FROM articles 
            WHERE created_at >= %s 
              AND cluster_id NOT IN (SELECT cluster_id FROM cluster_entities)
            GROUP BY cluster_id, title, description
            LIMIT 30
        """, (cutoff,)).fetchall()
        
        if not rows:
            conn.close()
            return

        for r in rows:
            cid = r['cluster_id']
            text = f"Title: {r['title']}\nDescription: {r['description']}"
            
            res, tier = _call_ai(text, ENTITY_EXTRACTION_PROMPT, max_tokens=500, json_mode=True)
            if res:
                try:
                    data = clean_json_response(res)
                    entities = data.get('entities', []) if isinstance(data, dict) else []
                    for ent in entities:
                        name = ent.get('name', '').strip()
                        etype = ent.get('type', 'PERSON').strip()
                        if name:
                            conn.execute(
                                "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                                (cid, name, etype)
                            )
                    conn.commit()
                except Exception as e:
                    log.warning(f"[entities] Failed to parse for {cid}: {e}")
        
        conn.close()
    except Exception as e:
        log.error(f"Entity extraction task failed: {e}")

@celery_app.task
def classify_topics_task():
    """
    Background task to classify untagged clusters into topical categories (Politics, Sport, etc.)
    """
    try:
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        
        # Find clusters created in last 24h where the topic is still 'Вести' (default)
        rows = conn.execute("""
            SELECT cluster_id, title, description 
            FROM articles 
            WHERE created_at >= %s AND topic = 'Вести'
            GROUP BY cluster_id, title, description
            LIMIT 30
        """, (cutoff,)).fetchall()
        
        if not rows:
            conn.close()
            return

        for r in rows:
            cid = r['cluster_id']
            text = f"Title: {r['title']}\nDescription: {r['description']}"
            
            res, tier = _call_ai(text, TOPIC_SYSTEM_PROMPT, max_tokens=10)
            if res:
                topic = res.strip().strip('"').strip("'").strip('.')
                # Simple validation
                valid_topics = ['Политика', 'Економија', 'Технологија', 'Спорт', 'Забава', 'Здравје', 'Вести']
                if topic in valid_topics:
                    log.info(f"[topic] Cluster {cid} -> {topic}")
                    conn.execute("UPDATE articles SET topic = %s WHERE cluster_id = %s", (topic, cid))
                    conn.commit()
        
        conn.close()
    except Exception as e:
        log.error(f"Topic classification task failed: {e}")

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
    from config import NTFY_TOPIC
    import os
    
    log.info("Generating and sending daily digest...")
    try:
        # Fetch top stories for the last 24 hours
        stories_by_cat = fetch_top_stories(days=1, per_category=3)
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
def cleanup_cover_art_task():
    """Background task to remove orphaned cover art images."""
    from ai_engine import cleanup_cover_art
    cleanup_cover_art()

@celery_app.task
def run_prune_db():
    """Periodic task to prune old articles and clean up files."""
    log.info("Pruning old database entries...")
    prune_db()
    log.info("Cleaning up orphaned cover art...")
    cleanup_cover_art_task.delay()

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
