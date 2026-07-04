import datetime
import json

from core.prompts import (
    SYNTHESIS_SYSTEM_PROMPT_MK,
    SYNTHESIS_SYSTEM_PROMPT_SR,
)
from core.synthesis_quality import record_synthesis_runtime_event
from nlp import (
    generate_local_placeholder,
    synthesize_cluster_fallback,
)
from tasks.intelligence._constants import *  # noqa: F403
from tasks.intelligence._queue import (
    _dispatch_batched,
    _historical_summary_dispatch_limit,
    _queue_backlog_high,
    _skip_when_intel_backlog,
    intelligence_secondary_deferred,
)
from tasks.intelligence.synthesis_pipeline import _generate_synthesis_via_cascade
from tasks.intelligence.synthesis_prompt import (
    _build_source_comparison_prompt_block,
    _build_cluster_synthesis_prompt,
)
from tasks.utils import (
    acquire_task_lock,
    get_celery_queue_depth,
    log,
    redis_client,
    release_task_lock,
    schedule_task_once,
)


@celery_app.task(name="tasks.intelligence.auto_repair_sources_task")
def auto_repair_sources_task():
    """Bridge to ingestion module for repair task."""
    from tasks.ingestion_task import auto_repair_sources_task as _task

    return _task()


@celery_app.task(name="tasks.intelligence.backfill_cover_art_single_task", rate_limit="5/m")
def backfill_cover_art_single_task(cluster_id, title):
    """Generate cover art for a single cluster without blocking a worker."""
    if get_celery_queue_depth() >= _BACKFILL_QUEUE_DEPTH_LIMIT:
        log.info(
            "[tasks] Skipping cover art generation for %s while queue backlog is high.",
            cluster_id,
        )
        return
    try:
        svg_content = generate_local_placeholder(cluster_id, title or "vest")
        img_url = generate_cover_art(cluster_id, svg_content)
        if img_url:
            db.execute(
                "UPDATE articles SET image_url = %s WHERE cluster_id = %s AND image_url IS NULL",
                (img_url, cluster_id),
                fetch=False,
            )
    except Exception as e:
        log.warning(f"[tasks] Cover art generation failed for {cluster_id}: {e}")


@celery_app.task(name="tasks.intelligence.backfill_cover_art_task")
def backfill_cover_art_task():
    """Queue cover art generation for clusters that lack a strong visual."""
    if _skip_when_intel_backlog("cover art backfill"):
        return
    lock_key = "lock:backfill_cover_art"
    try:
        if not redis_client.set(lock_key, "1", nx=True, ex=1200):
            log.info("Cover art backfill already in progress, skipping duplicate dispatch.")
            return
    except Exception as e:
        log.warning(f"Redis lock check failed for backfill_cover_art: {e}")

    try:
        if get_celery_queue_depth("intel-heavy") >= _BACKFILL_QUEUE_DEPTH_LIMIT:
            log.info("[tasks] Backfill cover art skipping: queue depth limit exceeded.")
            return

        # Find clusters from last 24h that either:
        # 1. Have no representative image
        # 2. Have a representative image that would be considered 'weak' (placeholders, small thumbs)
        # But SKIP if we already generated AI art for them (to save credits)
        rows = db.execute(
            """
            SELECT DISTINCT a.cluster_id,
                   (SELECT summary FROM cluster_summaries WHERE cluster_id = a.cluster_id LIMIT 1) as summary,
                   (SELECT title FROM articles WHERE cluster_id = a.cluster_id ORDER BY created_at DESC LIMIT 1) as title
            FROM articles a
            LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id
            WHERE a.created_at >= NOW() - INTERVAL '24 hours'
              AND (
                  m.representative_image IS NULL
                  OR m.representative_image LIKE '%.svg'
                  OR m.representative_image LIKE '%placeholder%'
                  OR m.representative_image LIKE '%default%'
              )
              AND (m.representative_image IS NULL OR m.representative_image NOT LIKE '/static/generated/%.jpg')
            LIMIT 12
        """
        )
        for idx, r in enumerate(rows):
            prompt_text = r["summary"] or r["title"] or ""
            backfill_cover_art_single_task.apply_async(
                args=(r["cluster_id"], prompt_text),
                countdown=idx * 5,  # Faster dispatch
            )
    except Exception as e:
        log.warning(f"[tasks] Cover art backfill failed: {e}")


@celery_app.task(name="tasks.intelligence.generate_embeddings_task", soft_time_limit=600, time_limit=660)
def generate_embeddings_task():
    """Generate pgvector embeddings for articles that don't have one yet."""
    try:
        from core.embeddings import embed_recent_articles

        embed_recent_articles()
    except Exception as e:
        log.warning(f"[tasks] Embedding generation failed: {e}")


@celery_app.task(name="tasks.intelligence.discover_storylines_task")
def discover_storylines_task():
    """Discover evolving storylines from news clusters."""
    if _skip_when_intel_backlog("storyline discovery"):
        return
    try:
        from core.topic_discovery import discovery_engine

        discovery_engine.run_discovery(lookback_hours=48)
        discovery_engine.refresh_storyline_metadata()
    except Exception as e:
        log.warning(f"[tasks] Storyline discovery failed: {e}")

@celery_app.task(name="tasks.intelligence.schedule_backfill_historical_summaries_task")
def schedule_backfill_historical_summaries_task():
    """Beat entrypoint for Gemma-only historical article summary backfill."""
    from core.config import HOMEPAGE_SYNTHESIS_ONLY
    from core.llm_router import _local_model_available

    if HOMEPAGE_SYNTHESIS_ONLY:
        log.info("[tasks] Skipping historical summary backfill in homepage-only mode.")
        return {"skipped": True, "reason": "homepage_only"}

    if intelligence_secondary_deferred():
        log.info("[tasks] Skipping scheduled historical summary backfill while intel-heavy backlog is high.")
        return {"skipped": True, "reason": "backlog_high"}

    if not _local_model_available():
        log.info("[tasks] Skipping historical summary backfill because local Gemma model is unavailable.")
        return {"skipped": True, "reason": "local_model_missing"}

    if not acquire_task_lock(_HISTORICAL_SUMMARY_LOCK_KEY, 1200):
        log.info("[tasks] Skipping historical summary backfill because a run is already in progress.")
        return {"skipped": True, "reason": "already_running"}

    try:
        return backfill_historical_article_summaries_task()
    finally:
        release_task_lock(_HISTORICAL_SUMMARY_LOCK_KEY)


@celery_app.task(name="tasks.intelligence.backfill_historical_article_summaries_task")
def backfill_historical_article_summaries_task(limit=None):
    """Enqueue Gemma-only summary batches for the oldest unsummarized articles."""
    from core.llm_router import _local_model_available

    if intelligence_secondary_deferred():
        log.info("[tasks] Skipping historical summary backfill while intel-heavy backlog is high.")
        return {"skipped": True, "reason": "backlog_high"}

    if not _local_model_available():
        return {"skipped": True, "reason": "local_model_missing"}

    dispatch_limit = _historical_summary_dispatch_limit(limit)
    rows = db.execute(
        """
        SELECT id
        FROM articles
        WHERE summary IS NULL
        ORDER BY id ASC
        LIMIT %s
        """,
        (dispatch_limit,),
        read_only=True,
    ) or []
    article_ids = [int(row["id"]) for row in rows]
    if not article_ids:
        log.info("[tasks] Historical summary backfill complete.")
        return {"enqueued": 0, "complete": True}

    from tasks.intelligence.summarization import summarize_articles_local_batch_task

    _dispatch_batched(summarize_articles_local_batch_task, article_ids)
    high_water = max(article_ids)
    try:
        redis_client.set(_HISTORICAL_SUMMARY_CURSOR_KEY, str(high_water))
    except Exception as exc:
        log.warning("[tasks] Failed to persist historical summary high-water mark: %s", exc)

    log.info(
        "[tasks] Enqueued Gemma-only historical summary backfill for %s articles (high_water=%s).",
        len(article_ids),
        high_water,
    )
    return {"enqueued": len(article_ids), "high_water": high_water, "complete": False}


@celery_app.task(name="tasks.intelligence.schedule_backfill_cluster_summaries_task")
def schedule_backfill_cluster_summaries_task(lang="sr"):
    """Beat entrypoint that avoids enqueueing backfill while intel-heavy is congested."""
    if intelligence_secondary_deferred():
        log.info(
            "[tasks] Skipping scheduled summary backfill dispatch (lang=%s) while intel-heavy backlog is high.",
            lang,
        )
        return
    backfill_cluster_summaries_task.delay(lang=lang)


@celery_app.task(name="tasks.intelligence.backfill_cluster_summaries_task")
def backfill_cluster_summaries_task(days=30, lang="sr", offset=0):
    """Generate cluster summaries for all existing clusters that don't have them yet."""
    try:
        if _queue_backlog_high():
            log.info(f"[tasks] Skipping summary backfill (lang={lang}) while queue backlog is high.")
            return

        from core.config import AUTO_SUMMARIZE_MIN_SRC
        from core.database import db_manager as db

        target_country = "MK" if lang == "mk" else "RS"

        # Get all clusters with articles but no summaries
        rows = db.execute(
            """
            SELECT DISTINCT a.cluster_id
            FROM articles a
            WHERE a.cluster_id IS NOT NULL
            AND a.country = %s
            AND a.created_at >= NOW() - make_interval(days => %s)
            AND NOT EXISTS (
                SELECT 1 FROM cluster_summaries cs
                WHERE cs.cluster_id = a.cluster_id AND cs.lang = %s
            )
            ORDER BY a.cluster_id
            LIMIT %s OFFSET %s
            """,
            (target_country, days, lang, _BACKFILL_BATCH_SIZE + 1, offset),
        )

        if not rows:
            log.info(f"[tasks] No clusters found for backfill (lang={lang})")
            return

        has_more = len(rows) > _BACKFILL_BATCH_SIZE
        cluster_ids = [row["cluster_id"] for row in rows[:_BACKFILL_BATCH_SIZE]]
        log.info(f"[tasks] Backfilling summaries for {len(cluster_ids)} clusters (lang={lang}, offset={offset})")

        for cluster_id in cluster_ids:
            try:
                # Check if this cluster has enough sources
                src_rows = db.execute(
                    "SELECT DISTINCT source FROM articles WHERE cluster_id = %s AND country = %s",
                    (cluster_id, target_country),
                )

                if len(src_rows) < AUTO_SUMMARIZE_MIN_SRC:
                    log.debug(f"[tasks] Skipping cluster {cluster_id} - only {len(src_rows)} source(s)")
                    continue

                # Load articles for this cluster
                article_rows = db.execute(
                    "SELECT * FROM articles WHERE cluster_id = %s AND country = %s ORDER BY created_at ASC",
                    (cluster_id, target_country),
                )

                if not article_rows:
                    continue

                system_prompt = SYNTHESIS_SYSTEM_PROMPT_MK if lang == "mk" else SYNTHESIS_SYSTEM_PROMPT_SR
                full_prompt = _build_cluster_synthesis_prompt(
                    article_rows,
                    lang=lang,
                    history_context=_fetch_synthesis_history_context(cluster_id, lang=lang, article_rows=article_rows),
                    source_comparison=_build_source_comparison_prompt_block(article_rows, lang=lang),
                )
                cascade = _generate_synthesis_via_cascade(
                    article_rows,
                    full_prompt,
                    system_prompt,
                    lang=lang,
                    max_tokens=3000,
                    fast_mode=True,
                )
                generation_provider = cascade.get("provider")
                generation_model = cascade.get("model")
                fallback_reason = cascade.get("fallback_reason")

                if cascade["status"] == "success":
                    res_data = cascade["res_data"]
                    fallback_result = {
                        "summary": res_data.get("summary", ""),
                        "generated_article": res_data.get("article", "") or res_data.get("generated_article", ""),
                        "synthetic_headline": res_data.get("synthetic_headline", ""),
                        "synthetic_standfirst": res_data.get("synthetic_standfirst", ""),
                        "perspectives": res_data.get("perspectives", []),
                        "key_facts": res_data.get("key_facts", []),
                        "analyst_entities": res_data.get("analyst_entities", []),
                    }
                    if isinstance(fallback_result["summary"], list):
                        fallback_result["summary"] = "\n".join(str(s) for s in fallback_result["summary"])
                    fallback_reason = None
                else:
                    fallback_result = synthesize_cluster_fallback(article_rows, lang=lang)
                    generation_provider = "enhanced_fallback"
                    generation_model = "enhanced_fallback"
                    fallback_reason = "backfill_enhanced_fallback_after_cascade_exhausted"

                if fallback_result["summary"] or fallback_result["generated_article"]:
                    # Store the summary in database
                    db.execute(
                        """
                        INSERT INTO cluster_summaries
                        (cluster_id, lang, summary, generated_article, synthetic_headline,
                         synthetic_standfirst, created_at, perspectives, key_facts, analyst_entities,
                         generation_provider, generation_model, fallback_reason)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (cluster_id, lang) DO UPDATE SET
                        summary = EXCLUDED.summary,
                        generated_article = EXCLUDED.generated_article,
                        synthetic_headline = EXCLUDED.synthetic_headline,
                        synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                        created_at = NOW(),
                        perspectives = EXCLUDED.perspectives,
                        key_facts = EXCLUDED.key_facts,
                        analyst_entities = EXCLUDED.analyst_entities,
                        generation_provider = EXCLUDED.generation_provider,
                        generation_model = EXCLUDED.generation_model,
                        fallback_reason = EXCLUDED.fallback_reason
                        """,
                        (
                            cluster_id,
                            lang,
                            fallback_result["summary"][:4000] if fallback_result["summary"] else "",
                            fallback_result["generated_article"][:8000] if fallback_result["generated_article"] else "",
                            (
                                fallback_result["synthetic_headline"][:200]
                                if fallback_result["synthetic_headline"]
                                else ""
                            ),
                            (
                                fallback_result["synthetic_standfirst"][:500]
                                if fallback_result["synthetic_standfirst"]
                                else ""
                            ),
                            json.dumps(fallback_result["perspectives"][:2000] if fallback_result["perspectives"] else []),
                            json.dumps(fallback_result.get("key_facts")[:1000] if fallback_result.get("key_facts") else []),
                            json.dumps(fallback_result.get("analyst_entities")[:1000] if fallback_result.get("analyst_entities") else []),
                            generation_provider,
                            generation_model,
                            fallback_reason,
                        ),
                    )
                    record_synthesis_runtime_event(
                        provider=generation_provider or "unknown",
                        lang=lang,
                        fast_mode=False,
                        fallback_reason=fallback_reason,
                    )
                    log.info(f"[tasks] Generated summary for cluster {cluster_id} (lang={lang})")
                else:
                    log.debug(f"[tasks] No summary generated for cluster {cluster_id}")

            except Exception as e:
                log.warning(f"[tasks] Failed to generate summary for cluster {cluster_id}: {e}")

        log.info(f"[tasks] Completed backfill for {lang} language clusters")
        if has_more and not _queue_backlog_high():
            schedule_task_once(
                f"lock:backfill_summaries:{lang}",
                180,
                backfill_cluster_summaries_task,
                kwargs={"days": days, "lang": lang, "offset": offset + _BACKFILL_BATCH_SIZE},
                countdown=60,
            )
        elif has_more:
            log.info(
                "[tasks] Deferring next summary backfill page (lang=%s, offset=%s) while queue backlog is high.",
                lang,
                offset + _BACKFILL_BATCH_SIZE,
            )

    except Exception as e:
        log.error(f"[tasks] Backfill cluster summaries failed: {e}")
        raise


@celery_app.task(name="tasks.intelligence.refine_knowledge_graph_sentiment_task")
def refine_knowledge_graph_sentiment_task():
    """Asynchronously refine entities and relationships in the knowledge graph using deep LLM sentiment analysis."""
    if _skip_when_intel_backlog("knowledge graph sentiment refinement"):
        return
    try:
        # Fetch articles from the last 2 hours
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=2)
        rows = db.execute(
            """
            SELECT cluster_id, array_agg(DISTINCT title) as titles, MAX(description) as desc
            FROM articles
            WHERE created_at >= %s
            GROUP BY cluster_id
            HAVING COUNT(DISTINCT source) >= 2
            LIMIT 20
            """,
            (cutoff,),
        )
        
        if not rows:
            log.info("[sentiment-refinement] No active clusters to refine sentiment for.")
            return

        from core.entities import extract_entities
        from nlp import analyze_sentiment_locally

        refined_count = 0
        for r in rows:
            text = f"{' '.join(r['titles'])} {r['desc'] or ''}"
            
            # Extract the unique entities
            entities = extract_entities(text, max_entities=8)
            if not entities:
                continue
                
            # Run deep context-aware LLM sentiment analysis (bypass_llm=False)
            deep_sentiment = analyze_sentiment_locally(text, bypass_llm=False)
            
            for ent in entities:
                from core.entities import normalize_entity_name
                canonical_name = normalize_entity_name(ent["name"])
                
                # Blend the deep sentiment score into the existing database score
                db.execute(
                    """
                    UPDATE knowledge_entities
                    SET sentiment_score = (sentiment_score * 0.7) + (%s * 0.3),
                        last_seen = CURRENT_TIMESTAMP
                    WHERE name = %s
                    """,
                    (deep_sentiment, canonical_name),
                    fetch=False,
                )
                refined_count += 1
                
        log.info(f"[sentiment-refinement] Successfully refined deep sentiment for {refined_count} entities.")
        
    except Exception as e:
        log.error(f"[sentiment-refinement] Failed to refine knowledge graph sentiment: {e}")

_DELEGATED = frozenset({'CLUSTER_LOOKBACK', '_call_ai', '_sanitize_synthesis_outputs', 'acquire_task_lock', 'analyst', 'average_embeddings', 'celery_app', 'clean_extracted_article_text', 'clean_json_response', 'db', 'deShout', 'detect_category', 'detect_topic', 'extract_clean_summary_text', 'extract_cluster_tags_locally', 'extract_entities', 'filter_cluster_tags', 'generate_cover_art', 'generate_local_placeholder', 'get_celery_queue_depth', 'get_dominant_color', 'invalidate_cluster_caches', 'invalidate_public_data_caches', 'log', 'normalize_citation_sources', 'normalize_headline', 'normalize_perspectives', 'normalize_summary_text', 'parse_embedding_value', 'record_runtime_event', 'redis_client', 'release_task_lock', 'schedule_task_once', 'summarize_article_fallback', 'synthesize_cluster_fallback', 'validate_person_names'})

def __getattr__(name: str):
    if name in _DELEGATED:
        from tasks.intelligence import _constants
        return getattr(_constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

