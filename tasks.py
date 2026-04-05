import logging
import datetime
import json
import re
from celery_app import celery_app
from ingestion import ingest_feeds, ingest_diaspora_feeds
from database import db_manager as db, prune_db
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, OPENCLAW_URL, OPENCLAW_TOKEN, NTFY_TOPIC, BREAKING_SCORE_THRESHOLD
from ai_engine import (
    translate_to_macedonian,
    sync_call_ai as _call_ai, clean_json_response, generate_cover_art
)
from prompts import (
    TAGGING_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT, 
    SYNTHESIS_SYSTEM_PROMPT, TOPIC_SYSTEM_PROMPT, 
    DAILY_BRIEF_SYSTEM_PROMPT, ENTITY_EXTRACTION_PROMPT
)
from categories import ALLOWED_CATEGORIES, detect_topic, detect_category, THEMATIC_TOPICS
from entities import extract_entities
from health import record_refresh, record_task_event
from utils import rank_articles_in_cluster, score_cluster, redis_client, delete_cache, delete_cache_prefix
from local_nlp import (
    summarize_article_fallback,
    synthesize_cluster_fallback,
    generate_daily_brief_fallback,
    extract_cluster_tags_locally,
    filter_cluster_tags,
)
from api_helpers import normalize_perspectives, normalize_summary_text

log = logging.getLogger("presek_celery")


def invalidate_public_data_caches():
    delete_cache_prefix("v4:news:")
    delete_cache("ssr:index:top_clusters")
    delete_cache("trending")
    delete_cache("stats:full")


def invalidate_cluster_caches(cluster_id=None):
    if cluster_id:
        delete_cache(f"cluster:detail:{cluster_id}")
    invalidate_public_data_caches()


def _load_cluster_articles_for_synthesis(cluster_id):
    return db.execute(
        "SELECT title, description, source, link, created_at, category FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
        (cluster_id,)
    )


def _normalize_cluster_synthesis(summary, perspectives, article_rows):
    clean_summary = normalize_summary_text(summary)
    clean_perspectives = normalize_perspectives(perspectives)

    if clean_summary and clean_perspectives:
        return clean_summary, clean_perspectives

    fallback = synthesize_cluster_fallback(article_rows)
    fallback_summary = normalize_summary_text(fallback.get("summary", ""))
    fallback_perspectives = normalize_perspectives(fallback.get("perspectives", []))

    if not clean_summary:
        clean_summary = fallback_summary
    if not clean_perspectives:
        clean_perspectives = fallback_perspectives

    return clean_summary, clean_perspectives

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def translate_article_task(article_id, title, description):
    """Translates non-Macedonian articles to Macedonian."""
    try:
        translated_title = translate_to_macedonian(title)
        translated_desc = translate_to_macedonian(description) if description else None

        title_changed = bool(translated_title and translated_title.strip() and translated_title != title)
        desc_changed = bool(description and translated_desc is not None and translated_desc != description)

        if translated_title:
            db.execute(
                "UPDATE articles SET title = %s, description = %s, is_translated = %s WHERE id = %s",
                (translated_title, translated_desc, 1 if (title_changed or desc_changed) else 0, article_id), fetch=False
            )
            invalidate_public_data_caches()
            log.info(f"Translated article {article_id}")
    except Exception as e:
        log.error(f"[tasks] Translation failed for {article_id}: {e}")

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def summarize_article_task(article_id, title, retry_attempt=0):
    """Generates an AI summary for a single article using Presek 4.0 DAL."""
    try:
        summary, _ = _call_ai(title, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
        if summary:
            clean = clean_json_response(summary)
            final = clean.get('summary', str(clean)) if isinstance(clean, dict) else clean
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (final, article_id), fetch=False)
            invalidate_public_data_caches()
            record_task_event("summarize_article", "ok", f"article:{article_id}")
            log.info(f"Successfully summarized article {article_id}")
        else:
            desc_row = db.execute_one("SELECT description FROM articles WHERE id = %s", (article_id,))
            fallback = summarize_article_fallback(title, (desc_row or {}).get("description"))
            if fallback:
                db.execute("UPDATE articles SET summary = %s WHERE id = %s", (fallback, article_id), fetch=False)
                invalidate_public_data_caches()
                record_task_event("summarize_article", "fallback", f"article:{article_id}")
                log.info(f"Stored local fallback summary for article {article_id}")
                if retry_attempt < 2:
                    summarize_article_task.apply_async(args=(article_id, title, retry_attempt + 1), countdown=1800)
            else:
                log.warning(f"No summary generated for article {article_id}")
    except Exception as e:
        desc_row = db.execute_one("SELECT description FROM articles WHERE id = %s", (article_id,))
        fallback = summarize_article_fallback(title, (desc_row or {}).get("description"))
        if fallback:
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (fallback, article_id), fetch=False)
            invalidate_public_data_caches()
            record_task_event("summarize_article", "fallback", f"article:{article_id}")
            log.warning(f"[tasks] Summarize failed for {article_id}; stored local fallback")
            if retry_attempt < 2:
                summarize_article_task.apply_async(args=(article_id, title, retry_attempt + 1), countdown=1800)
        else:
            record_task_event("summarize_article", "error", f"article:{article_id}")
            log.error(f"[tasks] Summarize failed for {article_id}: {e}")

@celery_app.task(rate_limit='5/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def synthesize_cluster_task(cluster_id, content, retry_attempt=0):
    """Generates a multi-perspective synthesis for a cluster."""
    article_rows = _load_cluster_articles_for_synthesis(cluster_id)
    try:
        raw, _ = _call_ai(f"Статии:\n{content}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True, task_type="synthesis")
        if raw:
            res = clean_json_response(raw)
            summary = res.get('summary', '') if isinstance(res, dict) else res
            perspectives = res.get('perspectives', []) if isinstance(res, dict) else []
            summary, perspectives = _normalize_cluster_synthesis(summary, perspectives, article_rows)
        else:
            fallback = synthesize_cluster_fallback(article_rows)
            summary, perspectives = _normalize_cluster_synthesis(
                fallback.get("summary", ""),
                fallback.get("perspectives", []),
                article_rows,
            )
            if (summary or perspectives) and retry_attempt < 2:
                synthesize_cluster_task.apply_async(args=(cluster_id, content, retry_attempt + 1), countdown=1800)

        if summary or perspectives:
            db.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, perspectives, created_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE
                   SET summary = EXCLUDED.summary, perspectives = EXCLUDED.perspectives, created_at = EXCLUDED.created_at""",
                (cluster_id, summary, json.dumps(perspectives), datetime.datetime.now()),
                fetch=False
            )

            any_img = db.execute_one("SELECT 1 FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL LIMIT 1", (cluster_id,))
            if not any_img:
                img_url = generate_cover_art(cluster_id, summary)
                if img_url:
                    db.execute("UPDATE articles SET image_url = %s WHERE id = (SELECT id FROM articles WHERE cluster_id = %s LIMIT 1)", (img_url, cluster_id), fetch=False)
            invalidate_cluster_caches(cluster_id)
            record_task_event("synthesize_cluster", "ok", f"cluster:{cluster_id}")
            log.info(f"Successfully synthesized cluster {cluster_id}")
        else:
            record_task_event("synthesize_cluster", "empty", f"cluster:{cluster_id}")
            log.warning(f"No synthesis generated for cluster {cluster_id}")
    except Exception as e:
        fallback = synthesize_cluster_fallback(article_rows)
        summary, perspectives = _normalize_cluster_synthesis(
            fallback.get("summary", ""),
            fallback.get("perspectives", []),
            article_rows,
        )
        if summary or perspectives:
            db.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, perspectives, created_at)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE
                   SET summary = EXCLUDED.summary, perspectives = EXCLUDED.perspectives, created_at = EXCLUDED.created_at""",
                (cluster_id, summary, json.dumps(perspectives), datetime.datetime.now()),
                fetch=False
            )
            invalidate_cluster_caches(cluster_id)
            record_task_event("synthesize_cluster", "fallback", f"cluster:{cluster_id}")
            log.warning(f"[tasks] Synthesis failed for {cluster_id}; stored local fallback")
            if retry_attempt < 2:
                synthesize_cluster_task.apply_async(args=(cluster_id, content, retry_attempt + 1), countdown=1800)
        else:
            record_task_event("synthesize_cluster", "error", f"cluster:{cluster_id}")
            log.error(f"[tasks] Synthesis failed for {cluster_id}: {e}")

@celery_app.task
def run_ingestion():
    """
    Main ingestion orchestrator. 
    Serialized for efficiency and to prevent DB/API bottlenecks.
    """
    log.info("Presek 4.0: Starting unified ingestion cycle...")
    new_count, errors = ingest_feeds()
    
    # Record health metrics
    record_refresh(new_count, errors)
    record_task_event("run_ingestion", "ok" if not errors else "warning", f"new_articles:{new_count}")
    if new_count > 0:
        invalidate_public_data_caches()
    
    if new_count > 0:
        # Chain dependent tasks to prevent resource spikes
        # 1. Embed new articles first (crucial for clustering/search)
        # 2. Extract metadata & entities
        # 3. Categorize & summarize
        (
            generate_embeddings_task.si() |
            generate_cluster_metadata_task.si() |
            classify_topics_task.si() |
            extract_entities_task.si() |
            recategorize_clusters_task.si() |
            auto_summarize_task.si()
        ).apply_async()
        
    log.info(f"Ingestion cycle orchestrated. Added {new_count} articles.")

@celery_app.task
def auto_summarize_task():
    """Dispatch summarization/synthesis tasks for top clusters."""
    from ai_engine import auto_summarize_top_clusters
    auto_summarize_top_clusters()


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
            
            if entities:
                from entities import update_knowledge_graph
                # Pass context text for local sentiment calculation
                update_knowledge_graph(entities, context_text=text)

            for ent in entities:
                db.execute(
                    "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (r['cluster_id'], ent.get('name'), ent.get('type')), fetch=False
                )
        invalidate_public_data_caches()
        record_task_event("extract_entities", "ok", "clusters:recent")
    except Exception as e:
        record_task_event("extract_entities", "error", "clusters:recent")
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
        record_task_event("classify_topics", "error", "clusters:recent")
        log.error(f"[tasks] Topic classification failed: {e}")
    else:
        invalidate_public_data_caches()
        record_task_event("classify_topics", "ok", "clusters:recent")

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
        record_task_event("recategorize_clusters", "error", "clusters:recent")
        log.error(f"[tasks] Recategorization failed: {e}")
    else:
        invalidate_public_data_caches()
        record_task_event("recategorize_clusters", "ok", "clusters:recent")

@celery_app.task
def generate_daily_brief_task(retry_attempt=0):
    """Generate the flagship morning briefing."""
    try:
        rows = db.execute(
            "SELECT cluster_id, title, description, source, category, topic, created_at FROM articles "
            "WHERE created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC LIMIT 10"
        )
        context = "\n".join([f"- {r['title']}" for r in rows])
        brief, _ = _call_ai(context, DAILY_BRIEF_SYSTEM_PROMPT, task_type="daily_brief")
        final_brief = brief or generate_daily_brief_fallback(rows)
        if final_brief:
            db.execute("INSERT INTO daily_briefings (date, content) VALUES (CURRENT_DATE, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content", (final_brief,), fetch=False)
            delete_cache("daily_brief:latest")
            record_task_event("daily_brief", "ok" if brief else "fallback", "date:current")
            if not brief and retry_attempt < 2:
                generate_daily_brief_task.apply_async(args=(retry_attempt + 1,), countdown=1800)
    except Exception as e:
        rows = db.execute(
            "SELECT cluster_id, title, description, source, category, topic, created_at FROM articles "
            "WHERE created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC LIMIT 10"
        )
        fallback = generate_daily_brief_fallback(rows)
        if fallback:
            db.execute("INSERT INTO daily_briefings (date, content) VALUES (CURRENT_DATE, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content", (fallback,), fetch=False)
            delete_cache("daily_brief:latest")
            record_task_event("daily_brief", "fallback", "date:current")
            log.warning("[tasks] Daily brief failed; stored local fallback briefing")
            if retry_attempt < 2:
                generate_daily_brief_task.apply_async(args=(retry_attempt + 1,), countdown=1800)
        else:
            record_task_event("daily_brief", "error", "date:current")
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
            SELECT cluster_id, array_agg(DISTINCT source) as sources, array_agg(DISTINCT title) as titles
            FROM articles WHERE created_at >= %s
            GROUP BY cluster_id HAVING COUNT(*) >= 2
        """, (cutoff,))
        for r in rows:
            entities = db.execute(
                "SELECT entity_name, entity_type FROM cluster_entities WHERE cluster_id = %s",
                (r['cluster_id'],)
            )
            entity_candidates = [dict(e) for e in entities]
            final_tags = extract_cluster_tags_locally(
                titles=r['titles'],
                entity_names=entity_candidates,
                sources=r['sources'],
                top_n=8,
            )
            if not final_tags:
                final_tags = filter_cluster_tags(r['sources'], limit=4)
            
            # 3. Representative Image Selection
            # We ONLY use images that belong to this specific cluster.
            # Using fallbacks from "similar clusters" causes massive duplication.
            img_row = db.execute_one(
                "SELECT image_url FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL ORDER BY created_at DESC LIMIT 1",
                (r['cluster_id'],)
            )
            rep_image = img_row['image_url'] if img_row else None

            db.execute(
                """INSERT INTO cluster_metadata (cluster_id, tags, representative_image, updated_at)
                   VALUES (%s, %s, %s, NOW())
                   ON CONFLICT (cluster_id) DO UPDATE SET 
                   tags = EXCLUDED.tags, 
                   representative_image = EXCLUDED.representative_image,
                   updated_at = NOW()""",
                (r['cluster_id'], final_tags, rep_image), fetch=False
            )
        invalidate_public_data_caches()
        record_task_event("cluster_metadata", "ok", "clusters:recent")
    except Exception as e:
        record_task_event("cluster_metadata", "error", "clusters:recent")
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


@celery_app.task(rate_limit='10/m')
def backfill_cover_art_single_task(cluster_id, title):
    """Generate cover art for a single cluster without blocking a worker."""
    try:
        img_url = generate_cover_art(cluster_id, title or '')
        if img_url:
            db.execute(
                "UPDATE articles SET image_url = %s WHERE cluster_id = %s AND image_url IS NULL",
                (img_url, cluster_id), fetch=False
            )
    except Exception as e:
        log.warning(f"[tasks] Cover art generation failed for {cluster_id}: {e}")


@celery_app.task
def backfill_cover_art_task():
    """Queue cover art generation without blocking a worker between items."""
    try:
        rows = db.execute("""
            SELECT DISTINCT a.cluster_id, 
                   (SELECT title FROM articles WHERE cluster_id = a.cluster_id ORDER BY created_at DESC LIMIT 1) as title
            FROM articles a
            WHERE a.image_url IS NULL
              AND a.created_at >= NOW() - INTERVAL '24 hours'
            LIMIT 5
        """)
        for idx, r in enumerate(rows):
            backfill_cover_art_single_task.apply_async(
                args=(r['cluster_id'], r['title'] or ''),
                countdown=idx * 4,
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
