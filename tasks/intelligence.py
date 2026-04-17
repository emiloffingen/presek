import datetime
import json
import logging
from celery_app import celery_app
from database import db_manager as db
from ai_engine import (
    translate_to_macedonian,
    sync_call_ai as _call_ai, clean_json_response, generate_cover_art
)
from prompts import (
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, 
    TOPIC_SYSTEM_PROMPT, FACTCHECK_SYSTEM_PROMPT
)
from categories import ALLOWED_CATEGORIES, detect_topic, detect_category, THEMATIC_TOPICS
from entities import extract_entities
from nlp import (
    summarize_article_fallback, synthesize_cluster_fallback,
    extract_cluster_tags_locally, filter_cluster_tags
)
from api_helpers import normalize_summary_text, normalize_perspectives
from utils import get_dominant_color
from tasks.utils import invalidate_public_data_caches, invalidate_cluster_caches, record_runtime_event, log

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
            # Trigger summarization after translation
            summarize_article_task.delay(article_id, translated_title)
    except Exception as e:
        log.error(f"[tasks] Translation failed for {article_id}: {e}")
        raise

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def standardize_article_style_task(article_id):
    """Refines article linguistic style using NLLB round-trip (Style Normalization)."""
    row = db.execute_one("SELECT title, description FROM articles WHERE id = %s", (article_id,))
    if not row: return

    title = row.get("title", "")
    desc = row.get("description", "")
    
    if not title or len(title) < 25: return # Skip very short headlines

    try:
        from nllb_translate import translate as nllb_translate
        from ai_engine import rewrite_to_macedonian_locally
        
        # 1. Title Normalization: MK -> EN -> MK
        en_bridge = nllb_translate(title, src_lang="mk", target_lang="en")
        if en_bridge and en_bridge.strip().lower() != title.strip().lower():
            mk_standard = nllb_translate(en_bridge, src_lang="en", target_lang="mk")
            if mk_standard and len(mk_standard) > 15:
                # Local polish
                final_title = rewrite_to_macedonian_locally(mk_standard)
                if final_title and final_title.strip().lower() != title.strip().lower():
                    # Preserve original for transparency/debugging
                    db.execute(
                        "UPDATE articles SET title = %s, original_title = %s, is_translated = 1 WHERE id = %s",
                        (final_title, title, article_id), fetch=False
                    )
                    log.info(f"[style] Standardized title for article {article_id}")
                    # Re-trigger summary if title changed significantly
                    summarize_article_task.delay(article_id, final_title)
        
    except Exception as e:
        log.error(f"[style] Normalization failed for {article_id}: {e}")

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def summarize_article_task(article_id, title, retry_attempt=0):
    """Generates an AI summary for a single article using Presek 4.0 DAL."""
    row = db.execute_one("SELECT description, full_content, topic FROM articles WHERE id = %s", (article_id,))
    if not row:
        return
        
    description = row.get("description") or ""
    full_content = row.get("full_content") or ""
    topic = row.get("topic")
    
    # Prioritize full content for better quality, but limit context size for cheap providers
    context_text = full_content if len(full_content) > len(description) else description
    
    # Save tokens: Don't use AI for very short content, use local fallback
    if len(context_text) < 200:
        fallback = summarize_article_fallback(title, context_text, topic=topic)
        if fallback:
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (fallback, article_id), fetch=False)
            invalidate_public_data_caches()
            record_runtime_event("summary_path", mode="local_short", topic=topic or "unknown")
            return

    prompt_parts = [f"Наслов: {str(title or '').strip()}"]
    if context_text:
        # Limit very long content to avoid extreme costs/token limits even for Gemini
        prompt_parts.append(f"Текст за резимирање:\n[START_ARTICLE_TEXT]\n{str(context_text).strip()[:10000]}\n[END_ARTICLE_TEXT]")
    prompt = "\n".join(part for part in prompt_parts if part)

    try:
        from tasks.utils import record_task_event
        summary, provider = _call_ai(prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize", topic=topic)
        if summary:
            clean = clean_json_response(summary)
            final = clean.get('summary', str(clean)) if isinstance(clean, dict) else clean
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (final, article_id), fetch=False)
            invalidate_public_data_caches()
            record_runtime_event("summary_path", mode=provider or "unknown", topic=topic or "unknown")
            record_task_event("summarize_article", "ok", f"article:{article_id}")
            log.info(f"Successfully summarized article {article_id} (provider: {provider})")
            
            # Post-summarize triggers
            extract_entities_task.delay()
            classify_topics_task.delay()
        else:
            fallback = summarize_article_fallback(title, context_text, topic=topic)
            if fallback:
                db.execute("UPDATE articles SET summary = %s WHERE id = %s", (fallback, article_id), fetch=False)
                invalidate_public_data_caches()
                record_runtime_event("summary_path", mode="local_fallback", topic=topic or "unknown")
                record_task_event("summarize_article", "fallback", f"article:{article_id}")
                log.info(f"Stored local fallback summary for article {article_id}")
            else:
                log.warning(f"No summary generated for article {article_id}")
    except Exception as e:
        fallback = summarize_article_fallback(title, context_text, topic=topic)
        if fallback:
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (fallback, article_id), fetch=False)
            invalidate_public_data_caches()
            record_runtime_event("summary_path", mode="local_exception_fallback", topic=topic or "unknown")
            record_task_event("summarize_article", "fallback", f"article:{article_id}")
            log.warning(f"[tasks] Summarize failed for {article_id}; stored local fallback")
        else:
            record_task_event("summarize_article", "error", f"article:{article_id}")
            log.error(f"[tasks] Summarize failed for {article_id}: {e}")

@celery_app.task(rate_limit='5/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def synthesize_cluster_task(cluster_id, content, retry_attempt=0):
    """Generates a multi-perspective synthesis for a cluster with historical continuity."""
    article_rows = _load_cluster_articles_for_synthesis(cluster_id)
    
    # 1. Fetch Historical Context (Cross-Story Memory)
    history_context = ""
    try:
        from embeddings import get_cluster_embedding
        current_vec = get_cluster_embedding(cluster_id)
        if current_vec:
            # Find semantically similar clusters from the last 7 days
            related = db.execute("""
                SELECT s.summary, s.generated_article, a.title
                FROM cluster_summaries s
                JOIN articles a ON s.cluster_id = a.cluster_id
                JOIN articles current_a ON current_a.cluster_id = %s
                WHERE s.cluster_id != %s
                  AND s.created_at >= NOW() - INTERVAL '7 days'
                  AND s.created_at < (SELECT MIN(created_at) FROM articles WHERE cluster_id = %s)
                ORDER BY (
                    SELECT AVG(embedding) FROM articles WHERE cluster_id = s.cluster_id
                ) <=> %s::vector
                LIMIT 1
            """, (cluster_id, cluster_id, cluster_id, current_vec))
            
            if related:
                r = related[0]
                prev_text = r['generated_article'] or r['summary']
                if prev_text:
                    history_context = f"\nПРЕТХОДЕН КОНТЕКСТ (за овој настан или поврзана тема од изминатите денови):\n[START_HISTORICAL_CONTEXT]\n{prev_text[:1000]}\n[END_HISTORICAL_CONTEXT]"
    except Exception as e:
        log.warning(f"[tasks/memory] Failed to fetch history for {cluster_id}: {e}")

    try:
        from tasks.utils import record_task_event
        full_prompt = f"{history_context}\n\nНОВИ СТАТИИ ОД ДЕНЕС:\n[START_NEW_ARTICLES]\n{content}\n[END_NEW_ARTICLES]"
        raw, provider = _call_ai(full_prompt, SYNTHESIS_SYSTEM_PROMPT, json_mode=True, task_type="synthesis")
        
        verification_report = None
        # Save tokens: only fact-check larger clusters (5+ sources)
        if len(article_rows) >= 5:
            v_raw, _ = _call_ai(f"Статии за споредба:\n[START_COMPARISON_DATA]\n{content}\n[END_COMPARISON_DATA]", FACTCHECK_SYSTEM_PROMPT, json_mode=True, task_type="factcheck")
            if v_raw:
                verification_report = clean_json_response(v_raw)

        if raw:
            res = clean_json_response(raw)
            summary = res.get('summary', '') if isinstance(res, dict) else res
            generated_article = res.get('article', '') if isinstance(res, dict) else ''
            perspectives = res.get('perspectives', []) if isinstance(res, dict) else []
            quote = res.get('quote', '') if isinstance(res, dict) else ''

            sentiment_data = {
                "sentiment": res.get('sentiment', {}),
                "tone_analysis": res.get('tone_analysis', {})
            }

            summary, perspectives = _normalize_cluster_synthesis(summary, perspectives, article_rows)
            record_runtime_event("synthesis_path", mode=provider or "unknown")
        else:
            fallback = synthesize_cluster_fallback(article_rows)
            sentiment_data = {"sentiment": {"score": 0, "tone": "неутрален"}, "tone_analysis": {}}
            summary, perspectives = _normalize_cluster_synthesis(
                fallback.get("summary", ""),
                fallback.get("perspectives", []),
                article_rows,
            )
            generated_article = ""
            quote = ""
            record_runtime_event("synthesis_path", mode="local_fallback")
            if (summary or perspectives) and retry_attempt < 2:
                synthesize_cluster_task.apply_async(args=(cluster_id, content, retry_attempt + 1), countdown=1800)

        if summary or perspectives:
            db.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, perspectives, generated_article, created_at, sentiment, verification_report, quote)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE
                   SET summary = EXCLUDED.summary,
                       perspectives = EXCLUDED.perspectives,
                       generated_article = EXCLUDED.generated_article,
                       created_at = EXCLUDED.created_at,
                       sentiment = EXCLUDED.sentiment,
                       verification_report = EXCLUDED.verification_report,
                       quote = EXCLUDED.quote""",
                (cluster_id, summary, json.dumps(perspectives), generated_article, datetime.datetime.now(), json.dumps(sentiment_data), json.dumps(verification_report) if verification_report else None, quote),
                fetch=False
            )
            any_img = db.execute_one("SELECT 1 FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL LIMIT 1", (cluster_id,))
            if not any_img:
                img_url = generate_cover_art(cluster_id, summary)
                if img_url:
                    db.execute("UPDATE articles SET image_url = %s WHERE id = (SELECT id FROM articles WHERE cluster_id = %s LIMIT 1)", (img_url, cluster_id), fetch=False)
            invalidate_cluster_caches(cluster_id)
            generate_cluster_metadata_task.delay()
            record_task_event("synthesize_cluster", "ok", f"cluster:{cluster_id}")
            log.info(f"Successfully synthesized cluster {cluster_id}")
        else:
            record_task_event("synthesize_cluster", "empty", f"cluster:{cluster_id}")
            log.warning(f"No synthesis generated for cluster {cluster_id}")
    except Exception as e:
        record_runtime_event("synthesis_path", mode="local_exception_fallback")
        fallback = synthesize_cluster_fallback(article_rows)
        sentiment_data = {"sentiment": {"score": 0, "tone": "неутрален"}, "tone_analysis": {}}
        summary, perspectives = _normalize_cluster_synthesis(
            fallback.get("summary", ""),
            fallback.get("perspectives", []),
            article_rows,
        )
        if summary or perspectives:
            db.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, perspectives, generated_article, created_at, sentiment, verification_report)
                   VALUES (%s, %s, %s, %s, %s, %s, NULL)
                   ON CONFLICT (cluster_id) DO UPDATE
                   SET summary = EXCLUDED.summary,
                       perspectives = EXCLUDED.perspectives,
                       generated_article = EXCLUDED.generated_article,
                       created_at = EXCLUDED.created_at,
                       sentiment = EXCLUDED.sentiment""",
                (cluster_id, summary, json.dumps(perspectives), "", datetime.datetime.now(), json.dumps(sentiment_data)),
                fetch=False
            )
            invalidate_cluster_caches(cluster_id)
            record_task_event("synthesize_cluster", "fallback", f"cluster:{cluster_id}")
            log.warning(f"[tasks] Synthesis failed for {cluster_id}; stored local fallback")
            if retry_attempt < 2:
                synthesize_cluster_task.apply_async(args=(cluster_id, content, retry_attempt + 1), countdown=1800)
        log.error(f"[tasks] Synthesis failed for {cluster_id}: {e}")

@celery_app.task
def auto_summarize_task():
    """Dispatch summarization/synthesis tasks for top clusters."""
    from ai_engine import auto_summarize_top_clusters
    auto_summarize_top_clusters()

@celery_app.task
def extract_entities_task():
    """Extract entities for top clusters using local hybrid logic (Lexicon + spaCy + Regex)."""
    try:
        from tasks.utils import record_task_event
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        rows = db.execute("""
            SELECT cluster_id, array_agg(DISTINCT title) as titles, MAX(description) as desc
            FROM articles WHERE created_at >= %s GROUP BY cluster_id
            HAVING COUNT(DISTINCT source) >= 2 LIMIT 50
        """, (cutoff,))

        for r in rows:
            text = f"{' '.join(r['titles'])} {r['desc'] or ''}"

            # Use hybrid local extractor (curated lexicon + spaCy NER + regex)
            entities = extract_entities(text, max_entities=8)

            if entities:
                from entities import update_knowledge_graph
                # update_knowledge_graph calculates local sentiment automatically
                update_knowledge_graph(entities, context_text=text)

                for ent in entities:
                    db.execute(
                        "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (r['cluster_id'], ent.get('name'), ent.get('type')), fetch=False
                    )

        invalidate_public_data_caches()
        record_task_event("extract_entities", "ok", "clusters:recent:local")
    except Exception as e:
        log.error(f"[tasks] Local entity extraction failed: {e}")

@celery_app.task
def classify_topics_task():
    """Classify default 'Вести' clusters using local rule-based detection."""
    try:
        from tasks.utils import record_task_event
        # Increased limit as local classification is nearly free
        rows = db.execute("SELECT cluster_id, title FROM articles WHERE topic = 'Вести' LIMIT 200")
        for r in rows:
            topic = detect_topic(r['title'])
            if topic != 'Вести':
                db.execute("UPDATE articles SET topic = %s WHERE cluster_id = %s", (topic, r['cluster_id']), fetch=False)
    except Exception as e:
        log.error(f"[tasks] Topic classification failed: {e}")
    else:
        invalidate_public_data_caches()
        from tasks.utils import record_task_event
        record_task_event("classify_topics", "ok", "clusters:recent:local")
@celery_app.task
def recategorize_clusters_task():
    """Verify if 'Македонија' articles belong in specialized categories using rule-based detection."""
    try:
        from tasks.utils import record_task_event
        rows = db.execute("SELECT cluster_id, title, description FROM articles WHERE category = 'Македонија' LIMIT 20")
        for r in rows:
            # Rule-based first (Free)
            res = detect_category(r['title'], description=r.get('description', ''))
            if res != 'Македонија':
                db.execute("UPDATE articles SET category = %s WHERE cluster_id = %s", (res, r['cluster_id']), fetch=False)
                continue
    except Exception as e:
        from tasks.utils import record_task_event
        record_task_event("recategorize_clusters", "error", "clusters:recent")
        log.error(f"[tasks] Recategorization failed: {e}")
    else:
        from tasks.utils import record_task_event
        invalidate_public_data_caches()
        record_task_event("recategorize_clusters", "ok", "clusters:recent")

@celery_app.task
def generate_cluster_metadata_task():
    """Tag recent clusters with metadata (entities, source count, and representative image)."""
    try:
        from tasks.utils import record_task_event
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
            
            img_row = db.execute_one(
                "SELECT image_url FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL ORDER BY created_at DESC LIMIT 1",
                (r['cluster_id'],)
            )
            rep_image = img_row['image_url'] if img_row else None

            if not rep_image:
                rep_image = generate_cover_art(r['cluster_id'], r['titles'][0] if r['titles'] else 'Вест')

            curr_meta = db.execute_one("SELECT representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = %s", (r['cluster_id'],))
            dominant_color = curr_meta['dominant_color'] if curr_meta else None
            
            if rep_image and (not curr_meta or curr_meta['representative_image'] != rep_image or not dominant_color):
                dominant_color = get_dominant_color(rep_image)

            db.execute(
                """INSERT INTO cluster_metadata (cluster_id, tags, representative_image, dominant_color, updated_at)
                   VALUES (%s, %s, %s, %s, NOW())
                   ON CONFLICT (cluster_id) DO UPDATE SET 
                   tags = EXCLUDED.tags, 
                   representative_image = EXCLUDED.representative_image,
                   dominant_color = EXCLUDED.dominant_color,
                   updated_at = NOW()""",
                (r['cluster_id'], final_tags, rep_image, dominant_color), fetch=False
            )
        invalidate_public_data_caches()
        record_task_event("cluster_metadata", "ok", "clusters:recent")
    except Exception as e:
        from tasks.utils import record_task_event
        record_task_event("cluster_metadata", "error", "clusters:recent")
        log.error(f"[tasks] Cluster metadata generation failed: {e}")

@celery_app.task
def auto_repair_sources_task():
    """Bridge to ingestion module for repair task."""
    from tasks.ingestion import auto_repair_sources_task as _task
    return _task()

@celery_app.task(rate_limit='5/m')
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
    """Queue cover art generation only for clusters that have ZERO images from any source."""
    try:
        rows = db.execute("""
            SELECT DISTINCT a.cluster_id, 
                   (SELECT summary FROM cluster_summaries WHERE cluster_id = a.cluster_id LIMIT 1) as summary,
                   (SELECT title FROM articles WHERE cluster_id = a.cluster_id ORDER BY created_at DESC LIMIT 1) as title
            FROM articles a
            WHERE NOT EXISTS (
                SELECT 1 FROM articles sub 
                WHERE sub.cluster_id = a.cluster_id 
                  AND sub.image_url IS NOT NULL 
                  AND sub.image_url NOT LIKE '/static/generated/%'
            )
            AND a.created_at >= NOW() - INTERVAL '24 hours'
            LIMIT 30
        """)
        for idx, r in enumerate(rows):
            prompt_text = r['summary'] or r['title'] or ''
            backfill_cover_art_single_task.apply_async(
                args=(r['cluster_id'], prompt_text),
                countdown=idx * 12,
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

@celery_app.task
def discover_storylines_task():
    """Discover evolving storylines from news clusters."""
    try:
        from topic_discovery import discovery_engine
        discovery_engine.run_discovery(lookback_hours=48)
        discovery_engine.refresh_storyline_metadata()
    except Exception as e:
        log.warning(f"[tasks] Storyline discovery failed: {e}")
