import logging
import datetime
import time
import json
from celery_app import celery_app
from ingestion import ingest_feeds, ingest_diaspora_feeds
from database import db_manager as db, prune_db
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, OPENCLAW_URL, OPENCLAW_TOKEN, NTFY_TOPIC, BREAKING_SCORE_THRESHOLD
from ai_engine import (
    translate_to_macedonian, auto_summarize_top_clusters, 
    _call_ai, clean_json_response, generate_cover_art
)
from prompts import (
    TAGGING_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT, 
    SYNTHESIS_SYSTEM_PROMPT, TOPIC_SYSTEM_PROMPT, 
    DAILY_BRIEF_SYSTEM_PROMPT, ENTITY_EXTRACTION_PROMPT
)
from categories import ALLOWED_CATEGORIES, detect_topic, detect_category, THEMATIC_TOPICS
from entities import extract_entities
from health import record_refresh
from utils import rank_articles_in_cluster, score_cluster, redis_client

log = logging.getLogger("presek_celery")

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def summarize_article_task(article_id, title):
    """Generates an AI summary for a single article using Presek 4.0 DAL."""
    try:
        summary, _ = _call_ai(title, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
        if summary:
            clean = clean_json_response(summary)
            final = clean.get('summary', str(clean)) if isinstance(clean, dict) else clean
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (final, article_id), fetch=False)
            log.info(f"Successfully summarized article {article_id}")
        else:
            log.warning(f"No summary generated for article {article_id}")
    except Exception as e:
        log.error(f"[tasks] Summarize failed for {article_id}: {e}")

@celery_app.task(rate_limit='5/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def synthesize_cluster_task(cluster_id, content):
    """Generates a multi-perspective synthesis for a cluster."""
    try:
        raw, _ = _call_ai(f"Статии:\n{content}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True, task_type="synthesis")
        if raw:
            res = clean_json_response(raw)
            summary = res.get('summary', '') if isinstance(res, dict) else res
            perspectives = res.get('perspectives', []) if isinstance(res, dict) else []
            
            db.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, perspectives, created_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE
                   SET summary = EXCLUDED.summary, perspectives = EXCLUDED.perspectives, created_at = EXCLUDED.created_at""",
                (cluster_id, summary, json.dumps(perspectives), datetime.datetime.now()),
                fetch=False
            )

            # Cover art generation
            any_img = db.execute_one("SELECT 1 FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL LIMIT 1", (cluster_id,))
            if not any_img:
                img_url = generate_cover_art(cluster_id, summary)
                if img_url:
                    db.execute("UPDATE articles SET image_url = %s WHERE id = (SELECT id FROM articles WHERE cluster_id = %s LIMIT 1)", (img_url, cluster_id), fetch=False)
            log.info(f"Successfully synthesized cluster {cluster_id}")
        else:
            log.warning(f"No synthesis generated for cluster {cluster_id}")
    except Exception as e:
        log.error(f"[tasks] Synthesis failed for {cluster_id}: {e}")

@celery_app.task
def run_ingestion():
    """Main ingestion orchestrator."""
    log.info("Presek 4.0: Starting ingestion cycle...")
    new_count, errors = ingest_feeds()
    
    # Diaspora is paused per user request
    d_count, d_errors = 0, []
    
    record_refresh(new_count + d_count, errors + d_errors)
    
    # Chain downstream tasks
    recategorize_clusters_task.delay()
    generate_cluster_metadata_task.delay()
    classify_topics_task.delay()
    extract_entities_task.delay()
    
    auto_summarize_top_clusters()
    log.info(f"Ingestion cycle complete. Added {new_count} articles.")

@celery_app.task
def extract_entities_task():
    """Extract entities for top clusters using free rule-based logic first."""
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        rows = db.execute("""
            SELECT cluster_id, array_agg(DISTINCT title) as titles, MAX(description) as desc
            FROM articles WHERE created_at >= %s GROUP BY cluster_id
            HAVING COUNT(DISTINCT source) >= 2 LIMIT 20
        """, (cutoff,))

        for r in rows:
            text = f"{' '.join(r['titles'])} {r['desc'] or ''}"
            
            # Rule-based (Free)
            entities = extract_entities(text)
            
            # AI Fallback (Commented out to save money)
            """
            if not entities:
                res, _ = _call_ai(text, ENTITY_EXTRACTION_PROMPT, json_mode=True, task_type="entity")
                if res:
                    data = clean_json_response(res)
                    entities = data.get('entities', []) if isinstance(data, dict) else []
            """

            for ent in entities:
                db.execute(
                    "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (r['cluster_id'], ent.get('name'), ent.get('type')), fetch=False
                )
    except Exception as e:
        log.error(f"[tasks] Entity extraction failed: {e}")

@celery_app.task
def classify_topics_task():
    """Classify default 'Вести' clusters into specific topics using rule-based detection first."""
    try:
        rows = db.execute("SELECT cluster_id, title FROM articles WHERE topic = 'Вести' LIMIT 50")
        for r in rows:
            # Rule-based first (Free)
            topic = detect_topic(r['title'])
            if topic != 'Вести':
                db.execute("UPDATE articles SET topic = %s WHERE cluster_id = %s", (topic, r['cluster_id']), fetch=False)
                continue
            
            # AI Fallback (Optional, commented out to save money as requested)
            """
            res, _ = _call_ai(r['title'], TOPIC_SYSTEM_PROMPT, task_type="topic", max_tokens=20)
            if res:
                topic = res.strip().strip('"').strip('.')
                if topic in THEMATIC_TOPICS:
                    db.execute("UPDATE articles SET topic = %s WHERE cluster_id = %s", (topic, r['cluster_id']), fetch=False)
            """
    except Exception as e:
        log.error(f"[tasks] Topic classification failed: {e}")

@celery_app.task
def recategorize_clusters_task():
    """Verify if 'Македонија' articles belong in specialized categories using rule-based detection."""
    try:
        rows = db.execute("SELECT cluster_id, title, description FROM articles WHERE category = 'Македонија' LIMIT 20")
        for r in rows:
            # Rule-based first (Free)
            res = detect_category(r['title'], description=r.get('description', ''))
            if res != 'Македонија':
                db.execute("UPDATE articles SET category = %s WHERE cluster_id = %s", (res, r['cluster_id']), fetch=False)
                continue

            # AI Fallback (Commented out to save money)
            """
            res, _ = _call_ai(r['title'], "Категоризирај ја веста: " + r['title'], task_type="categorize", max_tokens=20)
            if res and res in ALLOWED_CATEGORIES and res != 'Македонија':
                db.execute("UPDATE articles SET category = %s WHERE cluster_id = %s", (res, r['cluster_id']), fetch=False)
            """
    except Exception as e:
        log.error(f"[tasks] Recategorization failed: {e}")

@celery_app.task
def generate_daily_brief_task():
    """Generate the flagship morning briefing."""
    try:
        # Simplified for refactor: Fetch top 5 scored clusters
        rows = db.execute("SELECT cluster_id, title FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' LIMIT 10")
        context = "\n".join([f"- {r['title']}" for r in rows])
        brief, _ = _call_ai(context, DAILY_BRIEF_SYSTEM_PROMPT, task_type="daily_brief")
        if brief:
            db.execute("INSERT INTO daily_briefings (date, content) VALUES (CURRENT_DATE, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content", (brief,), fetch=False)
    except Exception as e:
        log.error(f"[tasks] Daily brief failed: {e}")

@celery_app.task
def run_prune_db():
    """Standard maintenance."""
    prune_db()
    from ai_engine import cleanup_cover_art
    cleanup_cover_art()


@celery_app.task
def generate_cluster_metadata_task():
    """Tag recent clusters with metadata (entities, source count, and representative image)."""
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        rows = db.execute("""
            SELECT cluster_id, array_agg(DISTINCT source) as sources
            FROM articles WHERE created_at >= %s
            GROUP BY cluster_id HAVING COUNT(*) >= 2
        """, (cutoff,))
        for r in rows:
            # 1. Fetch entities for this cluster to use as high-quality tags
            entities = db.execute("SELECT entity_name FROM cluster_entities WHERE cluster_id = %s", (r['cluster_id'],))
            tags = [e['entity_name'] for e in entities]
            if not tags:
                tags = r['sources']
            
            # 2. Representative Image Selection
            # First, try to get an image from the current cluster
            img_row = db.execute_one(
                "SELECT image_url FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL ORDER BY created_at DESC LIMIT 1",
                (r['cluster_id'],)
            )
            rep_image = img_row['image_url'] if img_row else None
            
            # Fallback: if no image in current cluster, try similar clusters (sharing tags)
            if not rep_image and tags:
                similar_img_row = db.execute_one("""
                    SELECT a.image_url 
                    FROM cluster_metadata m
                    JOIN articles a ON m.cluster_id = a.cluster_id
                    WHERE m.cluster_id != %s 
                      AND m.tags && %s
                      AND a.image_url IS NOT NULL
                      AND a.created_at >= NOW() - INTERVAL '48 hours'
                    ORDER BY a.created_at DESC
                    LIMIT 1
                """, (r['cluster_id'], tags))
                if similar_img_row:
                    rep_image = similar_img_row['image_url']

            db.execute(
                """INSERT INTO cluster_metadata (cluster_id, tags, representative_image, updated_at)
                   VALUES (%s, %s, %s, NOW())
                   ON CONFLICT (cluster_id) DO UPDATE SET 
                   tags = EXCLUDED.tags, 
                   representative_image = EXCLUDED.representative_image,
                   updated_at = NOW()""",
                (r['cluster_id'], tags, rep_image), fetch=False
            )
    except Exception as e:
        log.error(f"[tasks] Cluster metadata generation failed: {e}")


@celery_app.task
def send_daily_digest_task():
    """Send daily email digest. Placeholder — implement with digest module."""
    try:
        import digest as digest_module
        digest_module.send_digest()
    except Exception as e:
        log.warning(f"[tasks] Daily digest skipped: {e}")


@celery_app.task
def send_telegram_briefing_task():
    """Send daily briefing to Telegram channel."""
    try:
        row = db.execute_one(
            "SELECT content FROM daily_briefings WHERE date = CURRENT_DATE"
        )
        if not row or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            return
        import urllib.request
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": row["content"][:4096]}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        log.info("[tasks] Telegram briefing sent.")
    except Exception as e:
        log.warning(f"[tasks] Telegram briefing failed: {e}")


@celery_app.task
def backfill_cover_art_task():
    """Generate AI cover art for clusters that have no image."""
    try:
        rows = db.execute("""
            SELECT DISTINCT a.cluster_id, cs.summary
            FROM articles a
            JOIN cluster_summaries cs ON a.cluster_id = cs.cluster_id
            WHERE a.image_url IS NULL
              AND a.created_at >= NOW() - INTERVAL '24 hours'
            LIMIT 5
        """)
        for r in rows:
            img_url = generate_cover_art(r['cluster_id'], r['summary'] or '')
            if img_url:
                db.execute(
                    "UPDATE articles SET image_url = %s WHERE cluster_id = %s AND image_url IS NULL",
                    (img_url, r['cluster_id']), fetch=False
                )
    except Exception as e:
        log.warning(f"[tasks] Cover art backfill failed: {e}")


@celery_app.task
def generate_embeddings_task():
    """Generate pgvector embeddings for articles that don't have one yet."""
    try:
        from embeddings import embed_recent_articles
        embed_recent_articles()
    except Exception as e:
        log.warning(f"[tasks] Embedding generation failed: {e}")
