import datetime
import json
import os
import re
import sys
import threading

_analyst_semaphore = threading.Semaphore(2)

# Ensure project root is in path for Celery workers
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from celery_app import celery_app
from database import db_manager as db
from config import CLUSTER_LOOKBACK
from ai_engine import (
    sync_call_ai as _call_ai, clean_json_response, generate_cover_art
)
from embeddings import average_embeddings, parse_embedding_value
from prompts import (
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT
)
from nlp.categories import detect_topic, detect_category
from entities import extract_entities, validate_person_names
from nlp import (
    summarize_article_fallback, synthesize_cluster_fallback,
    extract_cluster_tags_locally, filter_cluster_tags, deShout
)
from api_helpers import normalize_summary_text, normalize_perspectives, normalize_citation_sources
from utils import get_dominant_color
from tasks.utils import invalidate_public_data_caches, invalidate_cluster_caches, record_runtime_event, log, redis_client

@celery_app.task(rate_limit='50/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def summarize_article_task(article_id, final_title=None):
    """Refines article content using AI summarization."""
    row = db.execute_one("SELECT title, description, full_content, topic, category FROM articles WHERE id = %s", (article_id,))
    if not row: return
    
    title = final_title or row.get("title")
    description = row.get("description", "")
    full_content = row.get("full_content", "")
    topic = row.get("topic")
    
    context_text = full_content if len(full_content) > len(description) else description
    
    # AI summarization logic
    prompt_parts = [f"Наслов: {str(title or '').strip()}"]
    if context_text:
        prompt_parts.append(f"Текст за резимирање:\n[START_ARTICLE_TEXT]\n{str(context_text).strip()[:10000]}\n[END_ARTICLE_TEXT]")
    prompt = "\n".join(part for part in prompt_parts if part)
    
    raw_output, provider = _call_ai(prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize", topic=topic, json_mode=False)
    
    final_text = None
    if raw_output:
        parsed = clean_json_response(raw_output)
        if isinstance(parsed, dict) and 'summary' in parsed:
            final_text = parsed['summary']
        else:
            final_text = re.sub(r'^```(json)?\s*', '', raw_output.strip())
            final_text = re.sub(r'\s*```$', '', final_text)

    if final_text:
        final_text = validate_person_names(final_text)
        db.execute("UPDATE articles SET summary = %s WHERE id = %s", (final_text, article_id), fetch=False)
        invalidate_public_data_caches()
        log.info(f"Successfully summarized article {article_id}")
    else:
        fallback = summarize_article_fallback(title, context_text, topic=topic)
        if fallback:
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (fallback, article_id), fetch=False)
            invalidate_public_data_caches()

def _load_cluster_articles_for_synthesis(cluster_id):
    return db.execute(
        "SELECT title, description, summary, full_content, source, link, created_at, category, topic, embedding FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
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


def _ensure_dict(value):
    return value if isinstance(value, dict) else {}


def _fallback_key_facts(article_rows, summary="", limit=4):
    facts = []
    seen = set()
    for line in str(summary or "").splitlines():
        clean = line.strip(" •-* \t")
        if clean and len(clean) >= 20:
            key = clean.casefold()
            if key not in seen:
                seen.add(key)
                facts.append(clean[:220])
        if len(facts) >= limit:
            return facts

    for article in article_rows or []:
        source = str(article.get("source") or "Извор").strip()
        title = deShout(str(article.get("title") or "").strip())
        if not title:
            continue
        fact = f"{source}: {title}"
        key = fact.casefold()
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact[:220])
        if len(facts) >= limit:
            break
    return facts


def _build_citation_sources(article_rows):
    ordered = []
    for item in article_rows or []:
        ordered.append({
            "source": str(item.get("source") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "link": str(item.get("link") or "").strip(),
            "created_at": str(item.get("created_at") or "").strip(),
            "category": str(item.get("category") or "").strip(),
        })
    return normalize_citation_sources(ordered)


def _build_synthesis_source_context(article_rows):
    blocks = []
    for idx, row in enumerate(article_rows or [], start=1):
        title = str(row.get("title") or "").strip()
        source = str(row.get("source") or "Извор").strip()
        category = str(row.get("category") or "").strip()
        topic = str(row.get("topic") or "").strip()
        description = str(row.get("description") or "").strip()
        summary = str(row.get("summary") or "").strip()
        full_content = str(row.get("full_content") or "").strip()

        evidence = full_content if len(full_content) > len(description) else description
        evidence = evidence[:2200].strip()
        parts = [f"[{idx}] {source}"]
        if category:
            parts.append(f"Категорија: {category}")
        if topic:
            parts.append(f"Тема: {topic}")
        if title:
            parts.append(f"Наслов: {title}")
        if summary:
            parts.append(f"Постоечко резиме: {summary[:500]}")
        if evidence:
            parts.append(f"Контекст:\n{evidence}")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _compute_centroid_from_values(values):
    return average_embeddings(values)


def _cosine_dist(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return 1 - (dot / (norm_a * norm_b)) if norm_a and norm_b else 1.0

from local_analyst import analyst

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def standardize_article_style_task(article_id):
    """Refines article linguistic style using Gemma 2 2B (Literary Normalization)."""
    from config import ENABLE_EXPENSIVE_STYLE_TASKS
    if not ENABLE_EXPENSIVE_STYLE_TASKS:
        return

    row = db.execute_one("SELECT title, description, topic, category FROM articles WHERE id = %s", (article_id,))
    if not row: return

    title = row.get("title", "")
    topic = row.get("topic") or ""
    category = row.get("category") or ""
    
    if not title or len(title) < 25: return # Skip very short headlines

    try:
        # Topic-Aware Bypass: Don't over-polish sports or entertainment as it kills the "vibe"
        if topic == "Спорт" or category == "Спорт":
            return

        # Use Gemma 2 2B for Literary Normalization
        final_title = analyst.normalize_headline(title)
        
        if final_title and final_title.strip().lower() != title.strip().lower():
            # Check semantic similarity to ensure we didn't lose the plot
            from nlp.text_processing import _jaccard_similarity
            if _jaccard_similarity(title, final_title) < 0.35:
                log.warning(f"[style] Rejected over-aggressive polish for {article_id}")
                return

            # Preserve original for transparency/debugging
            db.execute(
                "UPDATE articles SET title = %s, original_title = %s, is_translated = 1 WHERE id = %s",
                (final_title, title, article_id), fetch=False
            )
            log.info(f"[style] Standardized title for article {article_id} using Gemma 2 2B")
            # Re-trigger summary if title changed significantly
            summarize_article_task.delay(article_id, final_title)
        
    except Exception as e:
        log.error(f"[style] Normalization failed for {article_id}: {e}")

@celery_app.task(rate_limit='15/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def detect_global_story_task(article_id):
    """Detects if a Macedonian article is a translation of a foreign global report."""
    from config import LOCAL_TRANSLATION_ENABLED
    if not LOCAL_TRANSLATION_ENABLED:
        return

    row = db.execute_one("SELECT title FROM articles WHERE id = %s", (article_id,))
    if not row or not row.get("title"): return

    try:
        from embeddings import generate_query_embedding
        from utils import redis_client
        import numpy as np

        # Use the multilingual embedding model (MiniLM-L12) to compare Macedonian directly with global English headlines
        mk_vec = generate_query_embedding(row["title"])
        if not mk_vec: return

        # 3. Compare with Global Cache from Redis
        global_data = redis_client.get("presek:global_headlines:v1")
        if not global_data: return
        
        global_heads = json.loads(global_data) # List of {"title": str, "vec": list}
        
        best_similarity = 0
        for head in global_heads:
            g_vec = np.array(head["vec"])
            sim = np.dot(mk_vec, g_vec) / (np.linalg.norm(mk_vec) * np.linalg.norm(g_vec))
            if sim > best_similarity:
                best_similarity = sim
        
        # 4. Verdict (0.82 is a strong semantic match for cross-lingual pairs)
        if best_similarity > 0.82:
            db.execute("UPDATE articles SET is_global = TRUE WHERE id = %s", (article_id,), fetch=False)
            log.info(f"[originality] Flagged article {article_id} as GLOBAL (Sim: {best_similarity:.4f})")
            
    except Exception as e:
        log.warning(f"[originality] Detection failed for {article_id}: {e}")

        if cluster_position and cluster_position.get("pos", 0) >= 2:
            log.info(f"Skipping AI summary for supporting article {article_id} in cluster {cluster_id}")
            fallback = summarize_article_fallback(title, full_content or description, topic=topic)
            if fallback:
                db.execute("UPDATE articles SET summary = %s WHERE id = %s", (fallback, article_id), fetch=False)
                invalidate_public_data_caches()
                record_runtime_event("summary_path", mode="local_throttle_skip", topic=topic or "unknown")
            return

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
        # Limit very long content to keep provider cost and token usage bounded
        prompt_parts.append(f"Текст за резимирање:\n[START_ARTICLE_TEXT]\n{str(context_text).strip()[:10000]}\n[END_ARTICLE_TEXT]")
    prompt = "\n".join(part for part in prompt_parts if part)

    try:
        from tasks.utils import record_task_event
        raw_output, provider = _call_ai(prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize", topic=topic, json_mode=False)
        
        final_text = None
        if raw_output:
            # First try parsing as JSON (backwards compatibility)
            parsed = clean_json_response(raw_output)
            if isinstance(parsed, dict) and 'summary' in parsed:
                final_text = parsed['summary']
            else:
                # If not JSON, use the raw output but strip markdown fences if any
                final_text = re.sub(r'^```(json)?\s*', '', raw_output.strip())
                final_text = re.sub(r'\s*```$', '', final_text)
                # If it still looks like JSON {"summary": "..."}, extract text
                if final_text.startswith('{') and '"summary"' in final_text:
                    try:
                        data = json.loads(final_text)
                        final_text = data.get('summary', final_text)
                    except: pass

        # Safety Check: Never allow prompt markers to leak into DB
        if final_text and ("[START_ARTICLE_TEXT]" in final_text or "Наслов:" in final_text):
            log.warning(f"AI response for {article_id} contained prompt markers, rejecting.")
            final_text = None

        if final_text:
            final_text = validate_person_names(final_text)
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (final_text, article_id), fetch=False)
            invalidate_public_data_caches()
            record_runtime_event("summary_path", mode=provider or "unknown", topic=topic or "unknown")
            record_task_event("summarize_article", "ok", f"article:{article_id}")
            log.info(f"Successfully summarized article {article_id} (provider: {provider})")
            
            # Post-summarize triggers
            extract_entities_task.delay()
            classify_topics_task.delay()
        else:
            # Fallback to local if AI failed or leaked prompt
            log.info(f"AI summary failed for {article_id}, using local fallback.")
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

@celery_app.task(rate_limit='15/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def synthesize_cluster_task(cluster_id, content, retry_attempt=0, fast_mode=False):
    """Generates a multi-perspective synthesis for a cluster with historical continuity."""
    article_rows = _load_cluster_articles_for_synthesis(cluster_id)
    citation_sources = _build_citation_sources(article_rows)
    source_context = _build_synthesis_source_context(article_rows)

    # In fast mode, we use a much shorter token limit to get a response in seconds
    max_tokens = 600 if fast_mode else 2800
    
    # 1. Fetch Historical Context (Cross-Story Memory)
    history_context = ""
    try:
        from embeddings import get_cluster_embedding
        current_vec = get_cluster_embedding(cluster_id)
        if current_vec:
            current_vec_str = "[" + ",".join(map(str, current_vec)) + "]"
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
            """, (cluster_id, cluster_id, cluster_id, current_vec_str))
            
            if related:
                r = related[0]
                prev_text = r['generated_article'] or r['summary']
                if prev_text:
                    history_context = f"\nПРЕТХОДЕН КОНТЕКСТ (за овој настан или поврзана тема од изминатите денови):\n[START_HISTORICAL_CONTEXT]\n{prev_text[:1000]}\n[END_HISTORICAL_CONTEXT]"
    except Exception as e:
        log.warning(f"[tasks/memory] Failed to fetch history for {cluster_id}: {e}")

    try:
        from tasks.utils import record_task_event
        legacy_summary = str(content or "").strip()
        prompt_parts = []
        if fast_mode:
            prompt_parts.append("PROVIDE A BRIEF 1-PARAGRAPH SUMMARY ONLY. FOCUS ON THE CORE EVENT. IGNORE PERSPECTIVES.")
        elif history_context:
            prompt_parts.append(history_context)
            
        prompt_parts.append("НОВИ СТАТИИ ОД ДЕНЕС:\n[START_NEW_ARTICLES]")
        if source_context:
            prompt_parts.append(source_context)
        elif legacy_summary:
            prompt_parts.append(legacy_summary)
        prompt_parts.append("[END_NEW_ARTICLES]")
        full_prompt = "\n\n".join(part for part in prompt_parts if part)
        raw, provider = _call_ai(full_prompt, SYNTHESIS_SYSTEM_PROMPT, json_mode=True, task_type="synthesis", max_tokens=max_tokens)
        res_data = {}

        if raw:
            try:
                res = clean_json_response(raw)
            except Exception as e:
                log.error(f"[tasks/synthesis] JSON Parse Error for {cluster_id}: {e}. Raw: {raw[:200]}")
                raise

            res_data = res if isinstance(res, dict) else {}
            
            # If the AI returned a string instead of a dict, or if the dict is missing core fields,
            # we should treat it as a partial failure and merge with local fallback
            if not isinstance(res, dict) or not res.get('summary') or not res.get('article'):
                log.info(f"[tasks/synthesis] AI returned unstructured or partial response for {cluster_id}, merging with enhanced fallback.")
                fallback = synthesize_cluster_fallback(article_rows)
                
                # Merge: Prefer AI summary if it exists and is long enough, otherwise fallback
                summary = res_data.get('summary') or (res if isinstance(res, str) and len(res) > 30 else fallback['summary'])
                generated_article = res_data.get('article') or fallback['generated_article']
                synthetic_headline = res_data.get('synthetic_headline') or fallback['synthetic_headline']
                synthetic_standfirst = res_data.get('synthetic_standfirst') or fallback['synthetic_standfirst']
                perspectives = res_data.get('perspectives') or fallback['perspectives']
            else:
                summary = res_data.get('summary', '')
                generated_article = res_data.get('article', '')
                synthetic_headline = res_data.get('synthetic_headline', '')
                synthetic_standfirst = res_data.get('synthetic_standfirst', '')
                perspectives = res_data.get('perspectives', [])

            verification_report = res_data.get('verification_report')
            quote = validate_person_names(res_data.get('quote', ''))

            if not summary or (isinstance(summary, str) and len(summary) < 20):
                 log.warning(f"[tasks/synthesis] AI returned empty or too short summary for {cluster_id}")
                 raise ValueError("Empty AI summary")

            # Sanitize for name hallucinations
            summary = validate_person_names(summary)
            generated_article = validate_person_names(generated_article)
            synthetic_headline = validate_person_names(synthetic_headline)
            synthetic_standfirst = validate_person_names(synthetic_standfirst)
            
            # --- [NEW] 2026 Intelligence: Storyline & Impact ---
            story_so_far = validate_person_names(res_data.get('story_so_far', ''))
            impact_data = _ensure_dict(res_data.get('impact_analysis', {}))
            impact_score = float(impact_data.get('score', 0.0))
            impact_reasoning = impact_data.get('reasoning', '')
            log.debug(f"Impact score for {cluster_id}: {impact_score} (Reason: {impact_reasoning})")

            # AI Quality Gate: Hallucination Scanner (SKIP in fast_mode)
            comparison_text = (summary or "") + "\n" + (generated_article or "")
            if not fast_mode and not _is_grounded_synthesis(comparison_text, source_context or legacy_summary) and retry_attempt < 2:
                log.warning(f"Hallucination gate failed for cluster {cluster_id}, retrying...")
                synthesize_cluster_task.apply_async(args=(cluster_id, content, retry_attempt + 1), countdown=30)
                return

            sentiment_data = {
                "sentiment": res_data.get('sentiment', {}),
                "tone_analysis": res_data.get('tone_analysis', {})
            }

            summary, perspectives = _normalize_cluster_synthesis(summary, perspectives, article_rows)
            record_runtime_event("synthesis_path", mode=provider or "unknown", fast_mode=fast_mode)

            # Phase 3: Deep Local Analyst (SKIP in fast_mode)
            deep_metadata = {}
            pluralism_data = {}

            if not fast_mode:
                def _run_analyst_logic():
                    nonlocal deep_metadata, pluralism_data
                    try:
                        # Use semaphore to limit concurrent heavy CPU tasks
                        with _analyst_semaphore:
                            analyst_text = f"НАСЛОВ: {synthetic_headline}\n{summary}"
                            deep_metadata = analyst.extract_deep_metadata(analyst_text)

                            # Phase 3.1: Pluralism Assessment
                            titles_sources = [f"{a['source']}: {a['title']}" for a in article_rows[:10]]
                            pluralism_data = analyst.assess_pluralism(titles_sources)

                            # Phase 3.2: Knowledge Graph Update
                            entities = deep_metadata.get('entities', [])
                            for entity in entities:
                                db.execute("BEGIN")
                                try:
                                    db.execute("""
                                        INSERT INTO knowledge_entities (name, type, last_seen, total_mentions)
                                        VALUES (%s, 'PERSON', NOW(), 1)
                                        ON CONFLICT (name) DO UPDATE SET 
                                            last_seen = NOW()
                                    """, (entity,), fetch=False)
                                    db.execute("""
                                        INSERT INTO entity_mentions_daily (entity_name, cluster_id, day)
                                        VALUES (%s, %s, CURRENT_DATE)
                                        ON CONFLICT (entity_name, cluster_id, day) DO NOTHING
                                    """, (entity, cluster_id), fetch=False)
                                    db.execute("""
                                        UPDATE knowledge_entities 
                                        SET total_mentions = (
                                            SELECT COUNT(*) FROM entity_mentions_daily WHERE entity_name = %s
                                        )
                                        WHERE name = %s
                                    """, (entity, entity), fetch=False)
                                    db.execute("COMMIT")
                                except:
                                    db.execute("ROLLBACK")
                                    raise
                    except Exception as e:
                        log.error(f"[analyst] Internal logic error: {e}")

                analyst_thread = threading.Thread(target=_run_analyst_logic)
                analyst_thread.start()
                analyst_thread.join(timeout=240) # 4 minute limit for low-core CPUs

                if analyst_thread.is_alive():
                    log.warning(f"[analyst] Timeout reached for cluster {cluster_id}")
                elif deep_metadata or pluralism_data:
                    log.info(f"[analyst] Pluralism and KG updated for cluster {cluster_id}")

                deep_metadata = _ensure_dict(deep_metadata)
                pluralism_data = _ensure_dict(pluralism_data)

        else:
            log.warning(f"[tasks/synthesis] AI provider {provider} returned no content for {cluster_id}, using enhanced fallback")
            fallback = synthesize_cluster_fallback(article_rows)
            summary = fallback["summary"]
            perspectives = fallback["perspectives"]
            synthetic_headline = deShout(article_rows[0]["title"])
            synthetic_standfirst = ""
            generated_article = ""
            verification_report = None
            sentiment_data = {"sentiment": {"score": 0, "tone": "неутрален"}, "tone_analysis": {}}
            deep_metadata = {}
            pluralism_data = {}
            impact_score = 0.0
            impact_reasoning = ""
            quote = ""
            story_so_far = ""
            record_task_event(cluster_id, "synthesis_fallback", {"provider": provider})
            record_runtime_event("synthesis_path", mode="local_fallback_total")

        if summary or perspectives:
            deep_metadata = _ensure_dict(deep_metadata)
            pluralism_data = _ensure_dict(pluralism_data)
            key_facts = deep_metadata.get("facts") or _fallback_key_facts(article_rows, summary)
            analyst_entities = deep_metadata.get("entities") or []
            pulse_score = deep_metadata.get("pulse", 50)
            pluralism_score = pluralism_data.get("score", 50)
            if not pluralism_data:
                pluralism_data = {
                    "score": pluralism_score,
                    "verdict": "Локална проценка додека AI синтезата се освежува."
                }
            # Calculate Cluster Centroid (Semantic Center)
            centroid = _compute_centroid_from_values([a.get("embedding") for a in article_rows if a.get("embedding")])
            centroid_str = f"[{','.join(map(str, centroid))}]" if centroid and len(centroid) == 384 else None

            # Archive current summary before updating (Evolution Log)
            db.execute(
                """INSERT INTO cluster_summary_history (cluster_id, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, verification_report, citation_sources, tone_analysis, created_at, key_facts, analyst_entities)
                   SELECT cluster_id, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, verification_report, citation_sources, tone_analysis, created_at, key_facts, analyst_entities
                   FROM cluster_summaries WHERE cluster_id = %s""",
                (cluster_id,), fetch=False
            )

            if fast_mode:
                db.execute(
                    """INSERT INTO cluster_summaries (cluster_id, summary, generated_article, synthetic_headline, synthetic_standfirst, created_at, citation_sources, key_facts, analyst_entities, pulse_score, pluralism_score, narrative_diversity)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (cluster_id) DO UPDATE SET 
                           summary = EXCLUDED.summary, 
                           generated_article = EXCLUDED.generated_article, 
                           synthetic_headline = EXCLUDED.synthetic_headline,
                           synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                           created_at = EXCLUDED.created_at,
                           citation_sources = EXCLUDED.citation_sources,
                           key_facts = EXCLUDED.key_facts,
                           analyst_entities = EXCLUDED.analyst_entities,
                           pulse_score = EXCLUDED.pulse_score,
                           pluralism_score = EXCLUDED.pluralism_score,
                           narrative_diversity = EXCLUDED.narrative_diversity""",
                    (cluster_id, summary, generated_article, synthetic_headline, synthetic_standfirst, datetime.datetime.now(), json.dumps(citation_sources), json.dumps(key_facts), json.dumps(analyst_entities), pulse_score, pluralism_score, json.dumps(pluralism_data)),
                    fetch=False
                )
            else:
                db.execute(
                    """INSERT INTO cluster_summaries (cluster_id, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, created_at, sentiment, tone_analysis, verification_report, quote, centroid, citation_sources, key_facts, analyst_entities, pulse_score, pluralism_score, narrative_diversity, storyline_narrative)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (cluster_id) DO UPDATE SET 
                           summary = EXCLUDED.summary, 
                           perspectives = EXCLUDED.perspectives, 
                           generated_article = EXCLUDED.generated_article, 
                           synthetic_headline = EXCLUDED.synthetic_headline,
                           synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                           created_at = EXCLUDED.created_at, 
                           sentiment = EXCLUDED.sentiment, 
                           tone_analysis = EXCLUDED.tone_analysis,
                           verification_report = EXCLUDED.verification_report, 
                           quote = EXCLUDED.quote, 
                           centroid = EXCLUDED.centroid,
                           citation_sources = EXCLUDED.citation_sources,
                           key_facts = EXCLUDED.key_facts,
                           analyst_entities = EXCLUDED.analyst_entities,
                           pulse_score = EXCLUDED.pulse_score,
                           pluralism_score = EXCLUDED.pluralism_score,
                           narrative_diversity = EXCLUDED.narrative_diversity,
                           storyline_narrative = EXCLUDED.storyline_narrative""",
                    (cluster_id, summary, json.dumps(perspectives), generated_article, synthetic_headline, synthetic_standfirst, datetime.datetime.now(), json.dumps(sentiment_data), json.dumps(res_data.get('tone_analysis', {})), json.dumps(verification_report) if verification_report else None, quote, centroid_str, json.dumps(citation_sources), json.dumps(key_facts), json.dumps(analyst_entities), pulse_score, pluralism_score, json.dumps(pluralism_data), story_so_far),
                    fetch=False
                )

            # Update Metadata with Impact Score
            db.execute("""
                UPDATE cluster_metadata 
                SET impact_score = %s, impact_explanation = %s 
                WHERE cluster_id = %s
            """, (impact_score, impact_reasoning, cluster_id), fetch=False)
            # Publish SSE event for Real-Time UI updates
            try:
                from utils import publish_event
                # Determine if breaking
                is_breaking = False
                if article_rows:
                    from utils import score_cluster
                    cluster_score = score_cluster(article_rows)
                    from config import BREAKING_SCORE_THRESHOLD
                    is_breaking = cluster_score >= BREAKING_SCORE_THRESHOLD

                snippet = summary.split('\n')[0] if summary else ""
                snippet = snippet.replace('•', '').strip()[:150]
                publish_event("updates", {
                    "type": "cluster_synthesis_updated",
                    "cluster_id": cluster_id,
                    "is_breaking": is_breaking,
                    "impact_score": impact_score,
                    "headline": synthetic_headline or article_rows[0].get('title', ''),
                    "snippet": snippet,
                    "time": datetime.datetime.now().isoformat()
                })
            except Exception as pub_err:
                log.warning(f"[tasks] Failed to publish SSE event for {cluster_id}: {pub_err}")

            # Real-time Sports Score Alert
            try:
                from nlp.categories import detect_topic
                all_titles = " ".join([a.get("title") or "" for a in article_rows])
                if detect_topic(all_titles) == "Спорт":
                    from nlp.generation import _extract_sports_scores
                    from notifier import BreakingNewsNotifier
                    from config import NTFY_TOPIC
                    
                    # Use articles sorted by date
                    latest_scores = _extract_sports_scores(article_rows[0].get("title") or "") + _extract_sports_scores(article_rows[0].get("description") or "")
                    if latest_scores:
                        latest_score = latest_scores[0]
                        # BreakingNewsNotifier handles deduplication internally
                        notifier = BreakingNewsNotifier(NTFY_TOPIC)
                        notifier.notify_score_change(article_rows[0].get("title"), latest_score, cluster_id)
            except Exception as e:
                log.warning(f"[tasks/sports] Score alert failed: {e}")

            # Improved image logic: if no image or ONLY weak visuals exist, generate art
            strong_img = db.execute_one("""
                SELECT 1 FROM articles 
                WHERE cluster_id = %s 
                  AND image_url IS NOT NULL 
                  AND image_url NOT LIKE '%%placeholder%%'
                  AND image_url NOT LIKE '%%logo%%'
                  AND image_url NOT LIKE '%%default%%'
                  AND image_url NOT LIKE '%%.svg'
                LIMIT 1
            """, (cluster_id,))
            
            if not strong_img:
                # Trigger cover art generation
                img_url = generate_cover_art(cluster_id, summary)
                if img_url:
                    # Update all articles without images to use this generated one
                    db.execute("UPDATE articles SET image_url = %s WHERE cluster_id = %s AND (image_url IS NULL OR image_url LIKE '%%placeholder%%')", (img_url, cluster_id), fetch=False)
            try:
                invalidate_cluster_caches(cluster_id)
            except Exception as cache_err:
                log.warning(f"[tasks] Failed to invalidate caches for {cluster_id}: {cache_err}")
            try:
                generate_cluster_metadata_task.delay()
            except Exception as queue_err:
                log.warning(f"[tasks] Failed to queue metadata refresh for {cluster_id}: {queue_err}")
            try:
                record_task_event("synthesize_cluster", "ok", f"cluster:{cluster_id}")
            except Exception as event_err:
                log.warning(f"[tasks] Failed to record synthesis success for {cluster_id}: {event_err}")
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
            key_facts = _fallback_key_facts(article_rows, summary)
            pluralism_data = {
                "score": 50,
                "verdict": "Автоматска проценка од достапните извори."
            }
            db.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, created_at, sentiment, verification_report, citation_sources, key_facts, analyst_entities, pulse_score, pluralism_score, narrative_diversity)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE
                   SET summary = EXCLUDED.summary,
                       perspectives = EXCLUDED.perspectives,
                       generated_article = EXCLUDED.generated_article,
                       synthetic_headline = EXCLUDED.synthetic_headline,
                       synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                       created_at = EXCLUDED.created_at,
                       sentiment = EXCLUDED.sentiment,
                       citation_sources = EXCLUDED.citation_sources,
                       key_facts = EXCLUDED.key_facts,
                       analyst_entities = EXCLUDED.analyst_entities,
                       pulse_score = EXCLUDED.pulse_score,
                       pluralism_score = EXCLUDED.pluralism_score,
                       narrative_diversity = EXCLUDED.narrative_diversity""",
                (cluster_id, summary, json.dumps(perspectives), "", deShout(article_rows[0]["title"]) if article_rows else "", "", datetime.datetime.now(), json.dumps(sentiment_data), json.dumps(citation_sources), json.dumps(key_facts), json.dumps([]), 50, 50, json.dumps(pluralism_data)),
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
def extract_entities_task(hours=24):
    """Extract entities for top clusters using local hybrid logic (Lexicon + spaCy + Regex)."""
    try:
        from tasks.utils import record_task_event
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=int(hours or 24))
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
def generate_cluster_metadata_task(hours=24):
    """Tag recent clusters with metadata (entities, source count, centroid, and representative image)."""
    try:
        from tasks.utils import record_task_event

        cutoff = datetime.datetime.now() - datetime.timedelta(hours=int(hours or 24))
        rows = db.execute("""
            SELECT cluster_id, array_agg(DISTINCT source) as sources, array_agg(DISTINCT title) as titles,
                   array_agg(DISTINCT topic) as topics,
                   mode() WITHIN GROUP (ORDER BY category) as dominant_category,
                   array_agg(embedding) FILTER (WHERE embedding IS NOT NULL) as embeddings
            FROM articles WHERE created_at >= %s
            GROUP BY cluster_id
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
            
            # Calculate Centroid (Semantic Center)
            centroid = _compute_centroid_from_values(r.get("embeddings") or [])
            centroid_str = f"[{','.join(map(str, centroid))}]" if centroid and len(centroid) == 384 else None

            # Smart image selection: prefer high-quality sources and non-placeholder URLs
            img_row = db.execute_one("""
                SELECT image_url, source
                FROM articles 
                WHERE cluster_id = %s 
                  AND image_url IS NOT NULL 
                  AND image_url NOT LIKE '%%placeholder%%'
                  AND image_url NOT LIKE '%%default%%'
                  AND image_url NOT LIKE '%%.svg'
                  AND image_url NOT LIKE '%%logo%%'
                ORDER BY 
                    (
                        CASE WHEN image_url ~* '(thumb|thumbnail|sprite|logo|icon|avatar|favicon|pixel|small|social)' THEN -15 ELSE 0 END +
                        CASE WHEN image_url ~* '(hero|lead|main|large|full|original)' THEN 5 ELSE 0 END +
                        CASE WHEN image_url ~* '\\.(avif|webp)(\\?|$)' THEN 4 ELSE 0 END +
                        CASE WHEN image_url ~* '\\.(jpe?g)(\\?|$)' THEN 3 ELSE 0 END +
                        CASE WHEN image_url ~* '\\.png(\\?|$)' THEN -2 ELSE 0 END +
                        CASE WHEN image_url ~* '(^|[^0-9])(1[2-9][0-9]{2}|[2-9][0-9]{3})x(1[2-9][0-9]{2}|[2-9][0-9]{3})([^0-9]|$)' THEN 6 ELSE 0 END +
                        CASE 
                            WHEN source ILIKE '%%sdk%%' THEN 4
                            WHEN source ILIKE '%%360stepeni%%' THEN 4
                            WHEN source ILIKE '%%prizma%%' THEN 4
                            WHEN source ILIKE '%%sitel%%' THEN 2
                            WHEN source ILIKE '%%kanal5%%' THEN 2
                            WHEN source ILIKE '%%telma%%' THEN 3
                            WHEN source ILIKE '%%dw%%' THEN 4
                            ELSE 0
                        END
                    ) DESC,
                    created_at DESC 
                LIMIT 1
            """, (r['cluster_id'],))
            
            rep_image = img_row['image_url'] if img_row else None

            if not rep_image:
                # If we still have no image, try to generate one (AI cover art)
                rep_image = generate_cover_art(r['cluster_id'], r['titles'][0] if r['titles'] else 'Вест')

            curr_meta = db.execute_one("SELECT representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = %s", (r['cluster_id'],))
            dominant_color = curr_meta['dominant_color'] if curr_meta else None
            
            if rep_image and (not curr_meta or curr_meta['representative_image'] != rep_image or not dominant_color):
                dominant_color = get_dominant_color(rep_image)

            db.execute(
                """INSERT INTO cluster_metadata (cluster_id, tags, topics, representative_image, dominant_color, updated_at, centroid, category)
                   VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE SET 
                   tags = EXCLUDED.tags, 
                   topics = EXCLUDED.topics,
                   representative_image = EXCLUDED.representative_image,
                   dominant_color = EXCLUDED.dominant_color,
                   updated_at = NOW(),
                   centroid = EXCLUDED.centroid,
                   category = EXCLUDED.category""",
                (r['cluster_id'], final_tags, r['topics'], rep_image, dominant_color, centroid_str, r['dominant_category']), fetch=False
            )
        invalidate_public_data_caches()
        record_task_event("cluster_metadata", "ok", "clusters:recent")
    except Exception as e:
        from tasks.utils import record_task_event
        record_task_event("cluster_metadata", "error", "clusters:recent")
        log.error(f"[tasks] Cluster metadata generation failed: {e}")


@celery_app.task(rate_limit='1/h')
def recluster_recent_articles_task(hours=24, limit=800):
    """Re-assign cluster IDs for recent articles using the current clustering logic."""
    try:
        from tasks.utils import record_task_event
        import clustering

        hours = max(1, int(hours or 24))
        limit = max(1, int(limit or 800))
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
        rows = db.execute(
            """
            SELECT id, cluster_id, title, source, category, topic, created_at, embedding
            FROM articles
            WHERE created_at >= %s
            ORDER BY created_at ASC, id ASC
            LIMIT %s
            """,
            (cutoff, limit),
        ) or []

        if not rows:
            record_task_event("recluster_recent", "empty", f"hours:{hours}")
            return {"reclustered": 0, "touched_clusters": 0, "hours": hours, "limit": limit}

        recent_articles = []
        batch_clusters = []
        updates = []
        touched_clusters = set()

        for row in rows:
            title = str(row.get("title") or "").strip()
            category = row.get("category")
            topic = str(row.get("topic") or "Вести").strip() or "Вести"
            source = row.get("source")
            created_at = row.get("created_at")
            parsed_embedding = parse_embedding_value(row.get("embedding"))

            new_cluster_id = None
            if parsed_embedding:
                for candidate in batch_clusters:
                    if candidate["category"] != category or candidate["topic"] != topic:
                        continue
                    dist = _cosine_dist(parsed_embedding, candidate["embedding"])
                    if dist >= (clustering.VECTOR_THRESHOLD * 0.78):
                        continue
                    if topic == "Вести" or not topic:
                        incoming_entities = clustering._extract_title_entities(title)
                        candidate_entities = candidate.get("entities", set())
                        shared_entities = incoming_entities.intersection(candidate_entities) if incoming_entities and candidate_entities else set()
                        phrase_overlap = clustering._cluster_title_overlap(title, candidate["title"])
                        if not shared_entities and phrase_overlap < 0.34:
                            continue
                    new_cluster_id = candidate["cid"]
                    break

            if not new_cluster_id:
                new_cluster_id = clustering.find_or_create_cluster(
                    None,
                    title,
                    recent_articles,
                    embedding=None,
                    category=category,
                    source=source,
                    topic=topic,
                )

            old_cluster_id = str(row.get("cluster_id") or "")
            if new_cluster_id != old_cluster_id:
                updates.append((new_cluster_id, row["id"]))
                if old_cluster_id:
                    touched_clusters.add(old_cluster_id)
                touched_clusters.add(new_cluster_id)

            if parsed_embedding:
                batch_clusters.append({
                    "cid": new_cluster_id,
                    "embedding": parsed_embedding,
                    "category": category,
                    "topic": topic,
                    "title": title,
                    "entities": clustering._extract_title_entities(title),
                })

            recent_articles.insert(0, {
                "title": title,
                "cluster_id": new_cluster_id,
                "created_at": created_at,
                "category": category,
                "topic": topic,
                "source": source,
            })
            if len(recent_articles) > CLUSTER_LOOKBACK:
                recent_articles.pop()

        for cluster_id, article_id in updates:
            db.execute(
                "UPDATE articles SET cluster_id = %s WHERE id = %s",
                (cluster_id, article_id),
                fetch=False,
            )

        if touched_clusters:
            touched = sorted(touched_clusters)
            for table in ("cluster_summaries", "cluster_metadata", "cluster_entities", "reactions"):
                db.execute(f"DELETE FROM {table} WHERE cluster_id = ANY(%s)", (touched,), fetch=False)

            extract_entities_task.delay(hours=hours)
            generate_cluster_metadata_task.delay(hours=hours)
            auto_summarize_task.delay()
            invalidate_public_data_caches()

        record_task_event("recluster_recent", "ok", f"articles:{len(updates)}")
        return {
            "reclustered": len(updates),
            "touched_clusters": len(touched_clusters),
            "hours": hours,
            "limit": limit,
        }
    except Exception as e:
        from tasks.utils import record_task_event
        record_task_event("recluster_recent", "error", "clusters:recent")
        log.error(f"[tasks] Recent recluster failed: {e}")
        raise

@celery_app.task
def auto_repair_sources_task():
    """Bridge to ingestion module for repair task."""
    from tasks.ingestion_task import auto_repair_sources_task as _task
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
    """Queue cover art generation for clusters that lack a strong visual."""
    lock_key = "lock:backfill_cover_art"
    cooldown_key = "ai:cover_art:pollinations:cooldown"
    try:
        if not redis_client.set(lock_key, "1", nx=True, ex=1200):
            log.info("Cover art backfill already in progress, skipping duplicate dispatch.")
            return
    except Exception as e:
        log.warning(f"Redis lock check failed for backfill_cover_art: {e}")

    try:
        try:
            if redis_client.get(cooldown_key):
                log.info("Cover art backfill paused due to Pollinations cooldown.")
                return
        except Exception:
            pass

        # Find clusters from last 24h that either:
        # 1. Have no representative image
        # 2. Have a representative image that would be considered 'weak' (placeholders, small thumbs)
        # But SKIP if we already generated AI art for them (to save credits)
        rows = db.execute("""
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
            LIMIT 50
        """)
        for idx, r in enumerate(rows):
            prompt_text = r['summary'] or r['title'] or ''
            backfill_cover_art_single_task.apply_async(
                args=(r['cluster_id'], prompt_text),
                countdown=idx * 5, # Faster dispatch
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

def _is_grounded_synthesis(synthesis_text: str, source_context: str) -> bool:
    if not synthesis_text or not source_context:
        return True
    
    from tasks.delivery import _extract_capitalized_phrases
    source_lower = source_context.casefold()
    context_entities = {
        phrase.casefold()
        for phrase in _extract_capitalized_phrases(source_context)
        if len(str(phrase or "").strip()) >= 4
    }
    
    allowed_singletons = {
        "македонија", "скопје", "албанија", "еу", "вмро-дпмне",
        "иран", "ормускиот теснец", "дојран", "сад", "тексас", "нато",
        "обединетите нации", "он", "украина", "русија", "сдсм", "вашингтон", "техеран",
        "блискиот исток", "персискиот залив", "западниот балкан", "европската унија",
        "брисел", "москва", "киев", "израел", "газа", "либан", "црна гора", "србија", "грција", "бугарија",
        "ахмети", "мицкоски", "сиљановска", "пендаровски", "ковaчевски", "филипче", "груевски", "заев",
        "пресек", "битола", "охрид", "тетово", "куманово", "гостивар", "шри ланка", "кирибати",
        "си џинпинг", "бајден", "трамп", "путин", "зеленски", "макрон", "ердоган", "вучиќ", "рама",
        "мицкоски", "османи", "маричиќ", "костадиновска-стојчевска", "бисерка", "бочварски",
        "лига на шампиони", "премиер лига", "реал мадрид", "барселона", "манчестер јунајтед", "баерн минхен",
        "стеф кари", "леброн џејмс", "јокиќ", "дончиќ", "ѓоковиќ", "алкараз", "синер", "јаник синер",
        "винисиус", "винисиус жуниор", "мбапе", "халанд", "елмас", "елиф елмас", "пандев"
    }
    
    hallucinated_count = 0
    for phrase in _extract_capitalized_phrases(synthesis_text):
        clean = str(phrase or "").strip()
        if len(clean) < 4: continue
        if clean.split()[0].lower() in {"од", "во", "на", "со", "за", "низ"}:
            clean_parts = clean.split()[1:]
            if not clean_parts: continue
            clean = " ".join(clean_parts)
            if len(clean) < 3: continue
            
        words = [part for part in clean.replace("-", " ").split() if part]
        is_acronym = clean.isupper()
        
        # Stricter check for multi-word entities (proper names)
        # Single words are often common nouns or noise, so we are more lenient
        if len(words) < 2 and not is_acronym: continue
        
        folded = clean.casefold()
        if folded in context_entities or folded in allowed_singletons:
            continue
        if folded in source_lower:
            continue
        meaningful_words = [
            word.casefold()
            for word in re.findall(r"[A-Za-zА-Яа-яЀ-ӿ0-9-]{4,}", clean)
            if word.casefold() not in {"министерката", "министерот", "претседателот", "владата"}
        ]
        if meaningful_words and all(word in source_lower for word in meaningful_words):
            continue
            
        log.warning(f"[ai/hallucination] Hallucinated entity detected in synthesis: {clean}")
        hallucinated_count += 1
        
    # Allow 1 minor hallucination for very long syntheses to prevent infinite retry loops
    if hallucinated_count > 1:
        return False
    if hallucinated_count == 1 and len(synthesis_text) < 1500:
        return False
        
    return True
