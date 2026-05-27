from core.api_helpers import normalize_citation_sources, normalize_perspectives, normalize_summary_text
from core.entities import extract_entities, validate_person_names
from core.prompts import (
    SUMMARY_SYSTEM_PROMPT_MK,
    SUMMARY_SYSTEM_PROMPT_SR,
    SYNTHESIS_SYSTEM_PROMPT_MK,
    SYNTHESIS_SYSTEM_PROMPT_SR,
)
from nlp import (
    deShout,
    extract_cluster_tags_locally,
    filter_cluster_tags,
    generate_local_placeholder,
    summarize_article_fallback,
    synthesize_cluster_fallback,
)
from nlp.categories import detect_category, detect_topic
from nlp.local_analyst import analyst
from tasks.utils import (
    get_celery_queue_depth,
    invalidate_cluster_caches,
    invalidate_public_data_caches,
    log,
    record_runtime_event,
    redis_client,
)
from utils import get_dominant_color

SUPPORTED_LANGS = ["sr", "mk"]
import datetime
import json
import os
import re
import sys
import threading

from core.ai_engine import clean_json_response, generate_cover_art
from core.ai_engine import sync_call_ai as _call_ai
from core.celery_app import celery_app
from core.config import CLUSTER_LOOKBACK
from core.database import db_manager as db
from core.embeddings import average_embeddings, parse_embedding_value

_analyst_semaphore = threading.Semaphore(2)
_BACKFILL_QUEUE_DEPTH_LIMIT = 100

# Ensure project root is in path for Celery workers
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@celery_app.task
def summarize_articles_batch_task(article_ids):
    """Batch processes AI summarization for articles."""
    for article_id in article_ids:
        summarize_article_task(article_id)


@celery_app.task
def detect_global_stories_batch_task(article_ids):
    """Batch processes global story detection for articles."""
    for article_id in article_ids:
        detect_global_story_task(article_id)


@celery_app.task
def standardize_article_styles_batch_task(article_ids):
    """Batch processes style standardization for articles."""
    for article_id in article_ids:
        standardize_article_style_task(article_id)


@celery_app.task(rate_limit="50/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def summarize_article_task(article_id, final_title=None):
    """Refines article content using AI summarization."""
    row = db.execute_one(
        "SELECT title, description, full_content, topic, category FROM articles WHERE id = %s",
        (article_id,),
    )
    if not row:
        return

    title = final_title or row.get("title")
    description = row.get("description", "")
    full_content = row.get("full_content", "")
    topic = row.get("topic")

    context_text = full_content if len(full_content or "") > len(description or "") else description

    # AI summarization logic
    prompt_parts = [f"Naslov: {str(title or '').strip()}"]
    if context_text:
        prompt_parts.append(
            f"Tekst za rezimiranje:\n<article_content>\n{
                str(context_text).strip()[
                    :10000]}\n</article_content>"
        )
    prompt = "\n".join(part for part in prompt_parts if part)

    # Determine which prompt to use based on existing category or topic if possible,
    # but default to Serbian as the primary processing language for now.
    # In a full multi-lang setup, we'd summarize in the language of the source.
    from core.language import detect_language

    lang = detect_language(title + " " + (description or ""))
    system_prompt = SUMMARY_SYSTEM_PROMPT_MK if lang == "mk" else SUMMARY_SYSTEM_PROMPT_SR

    raw_output, provider = _call_ai(
        prompt,
        system_prompt,
        task_type="summarize",
        topic=topic,
        json_mode=False,
        lang=lang,
    )

    final_text = None
    if raw_output:
        parsed = clean_json_response(raw_output)
        if isinstance(parsed, dict) and "summary" in parsed:
            final_text = parsed["summary"]
        else:
            final_text = re.sub(r"^```(json)?\s*", "", raw_output.strip())
            final_text = re.sub(r"\s*```$", "", final_text)

    if final_text:
        final_text = validate_person_names(final_text)
        db.execute(
            "UPDATE articles SET summary = %s WHERE id = %s",
            (final_text, article_id),
            fetch=False,
        )
        invalidate_public_data_caches()
        log.info(f"Successfully summarized article {article_id}")
    else:
        fallback = summarize_article_fallback(title, context_text, topic=topic, lang=lang)
        if fallback:
            db.execute(
                "UPDATE articles SET summary = %s WHERE id = %s",
                (fallback, article_id),
                fetch=False,
            )
            invalidate_public_data_caches()


def _load_cluster_articles_for_synthesis(cluster_id):
    return db.execute(
        "SELECT title, description, summary, full_content, source, link, created_at, category, topic, embedding FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
        (cluster_id,),
    )


def _build_cluster_synthesis_content(article_rows):
    rows = article_rows or []
    return "\n".join(
        f"- [{row.get('source') or 'izvor'}]: {row.get('title') or ''}" for row in rows[:10] if row.get("title")
    )


def _normalize_cluster_synthesis(summary, perspectives, article_rows, lang="mk"):
    clean_summary = normalize_summary_text(summary)
    clean_perspectives = normalize_perspectives(perspectives)

    if clean_summary and clean_perspectives:
        return clean_summary, clean_perspectives

    fallback = synthesize_cluster_fallback(article_rows, lang=lang)
    fallback_summary = normalize_summary_text(fallback.get("summary", ""))
    fallback_perspectives = normalize_perspectives(fallback.get("perspectives", []))

    if not clean_summary:
        clean_summary = fallback_summary
    if not clean_perspectives:
        clean_perspectives = fallback_perspectives

    return clean_summary, clean_perspectives


def _looks_like_leaked_json_fragment(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False
    lowered = clean.lower()
    json_markers = (
        '"synthetic_headline"',
        '"synthetic_standfirst"',
        '"summary"',
        '"generated_article"',
        '"key_facts"',
        '"perspectives"',
        "verification_report",
    )
    marker_count = sum(1 for marker in json_markers if marker in lowered)
    bullet_json_lines = sum(1 for line in clean.splitlines() if line.strip().startswith(("• {", "• \"", "{", "\"")))
    return marker_count >= 2 or bullet_json_lines >= 2


def _paragraph_fingerprint(text: str) -> str:
    return re.sub(r"\W+", " ", str(text or "").casefold()).strip()


def _dedupe_generated_article(text: str) -> str:
    parts = [part.strip() for part in re.split(r"\n{2,}", str(text or "")) if part.strip()]
    kept = []
    seen = set()
    for part in parts:
        key = _paragraph_fingerprint(part)
        if not key or key in seen:
            continue
        if any(key and (key in prev or prev in key) and min(len(key), len(prev)) > 120 for prev in seen):
            continue
        seen.add(key)
        kept.append(part)
    return "\n\n".join(kept).strip()


def _sanitize_synthesis_outputs(summary, generated_article, perspectives, article_rows, lang="mk"):
    fallback = None
    clean_summary = normalize_summary_text(summary)
    clean_article = _dedupe_generated_article(validate_person_names(generated_article or ""))

    if _looks_like_leaked_json_fragment(clean_summary):
        fallback = fallback or synthesize_cluster_fallback(article_rows, lang=lang)
        clean_summary = normalize_summary_text(fallback.get("summary", ""))

    if _looks_like_leaked_json_fragment(clean_article) or len(clean_article) < 80:
        fallback = fallback or synthesize_cluster_fallback(article_rows, lang=lang)
        clean_article = _dedupe_generated_article(fallback.get("generated_article", ""))

    clean_perspectives = normalize_perspectives(perspectives, lang=lang)
    if not clean_perspectives:
        fallback = fallback or synthesize_cluster_fallback(article_rows, lang=lang)
        clean_perspectives = normalize_perspectives(fallback.get("perspectives", []), lang=lang)

    return clean_summary, clean_article, clean_perspectives


def _ensure_dict(value):
    return value if isinstance(value, dict) else {}


def _fallback_key_facts(article_rows, summary="", limit=4):
    facts = []
    seen = set()

    for article in article_rows or []:
        source = str(article.get("source") or "izvor").strip()
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
        ordered.append(
            {
                "source": str(item.get("source") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "link": str(item.get("link") or "").strip(),
                "created_at": str(item.get("created_at") or "").strip(),
                "category": str(item.get("category") or "").strip(),
            }
        )
    return normalize_citation_sources(ordered)


def _build_synthesis_source_context(article_rows, lang: str = "sr"):
    blocks = []
    for idx, row in enumerate(article_rows or [], start=1):
        title = str(row.get("title") or "").strip()
        source = str(row.get("source") or "izvor").strip()
        category = str(row.get("category") or "").strip()
        topic = str(row.get("topic") or "").strip()
        description = str(row.get("description") or "").strip()
        summary = str(row.get("summary") or "").strip()
        full_content = str(row.get("full_content") or "").strip()

        evidence = full_content if len(full_content or "") > len(description or "") else description
        evidence = evidence[:2200].strip()
        parts = [f"[{idx}] {source}"]
        if category:
            parts.append(f"{'Kategorija' if lang == 'sr' else 'Категорија'}: {category}")
        if topic:
            parts.append(f"{'Tema' if lang == 'sr' else 'Тема'}: {topic}")
        if title:
            parts.append(f"{'Naslov' if lang == 'sr' else 'Наслов'}: {title}")
        if summary:
            parts.append(f"{'Postojeće rezime' if lang == 'sr' else 'Постоечко резиме'}: {summary[:500]}")
        if evidence:
            parts.append(f"{'kontekst' if lang == 'sr' else 'контекст'}:\n{evidence}")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _compute_centroid_from_values(values):
    return average_embeddings(values)


def _cosine_dist(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return 1 - (dot / (norm_a * norm_b)) if norm_a and norm_b else 1.0


_GENERIC_CLUSTER_TOPICS = {"vesti", "news", ""}


def _cluster_text_similarity(left_titles, right_titles, lang="mk"):
    import core.clustering as clustering

    left_text = " ".join(str(title or "") for title in (left_titles or [])[:3])
    right_text = " ".join(str(title or "") for title in (right_titles or [])[:3])
    lexical = clustering.get_cosine(
        clustering.text_to_vector(left_text, lang=lang),
        clustering.text_to_vector(right_text, lang=lang),
    )
    phrase = 0.0
    for left in (left_titles or [])[:3]:
        for right in (right_titles or [])[:3]:
            phrase = max(phrase, clustering._title_phrase_overlap(str(left or ""), str(right or ""), lang=lang))
    return lexical, phrase


def _cluster_tag_set(row):
    return {str(tag or "").strip().lower() for tag in (row.get("tags") or []) if str(tag or "").strip()}


def _split_cluster_merge_score(left, right, lang="mk"):
    """Return a merge confidence for two already-created clusters, or 0 if unsafe."""
    if left.get("cluster_id") == right.get("cluster_id"):
        return 0.0
    if left.get("country") != right.get("country"):
        return 0.0
    if left.get("category") and right.get("category") and left.get("category") != right.get("category"):
        return 0.0

    left_topic = str(left.get("topic") or "").strip()
    right_topic = str(right.get("topic") or "").strip()
    if left_topic != right_topic:
        return 0.0

    left_latest = left.get("latest_article")
    right_latest = right.get("latest_article")
    if left_latest and right_latest:
        try:
            if abs((left_latest - right_latest).total_seconds()) > 36 * 3600:
                return 0.0
        except Exception:
            pass

    lexical, phrase = _cluster_text_similarity(left.get("titles"), right.get("titles"), lang=lang)
    shared_tags = _cluster_tag_set(left) & _cluster_tag_set(right)
    meaningful_shared_tags = {tag for tag in shared_tags if tag not in _GENERIC_CLUSTER_TOPICS}

    left_centroid = parse_embedding_value(left.get("centroid"))
    right_centroid = parse_embedding_value(right.get("centroid"))
    centroid_similarity = 0.0
    if left_centroid and right_centroid:
        centroid_similarity = 1 - _cosine_dist(left_centroid, right_centroid)

    generic_topic = left_topic.lower() in _GENERIC_CLUSTER_TOPICS
    if generic_topic:
        if len(meaningful_shared_tags) >= 2 and lexical >= 0.34:
            return round(lexical + phrase + len(meaningful_shared_tags) * 0.08 + centroid_similarity * 0.2, 4)
        if len(meaningful_shared_tags) >= 1 and lexical >= 0.28 and centroid_similarity >= 0.82:
            return round(lexical + phrase + centroid_similarity * 0.35, 4)
        return 0.0

    if lexical >= 0.42 or (phrase >= 0.25 and meaningful_shared_tags):
        return round(lexical + phrase + len(meaningful_shared_tags) * 0.06 + centroid_similarity * 0.15, 4)
    return 0.0


@celery_app.task(rate_limit="10/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def standardize_article_style_task(article_id):
    """Refines article linguistic style using Gemma 2 2B (Literary Normalization)."""
    from core.config import ENABLE_EXPENSIVE_STYLE_TASKS

    if not ENABLE_EXPENSIVE_STYLE_TASKS:
        return

    row = db.execute_one(
        "SELECT title, description, topic, category, country FROM articles WHERE id = %s",
        (article_id,),
    )
    if not row:
        return

    title = row.get("title", "")
    topic = row.get("topic") or ""
    category = row.get("category") or ""
    country = row.get("country") or "MK"
    lang = "sr" if country == "SR" else "mk"

    if not title or len(title) < 25:
        return  # Skip very short headlines

    try:
        # Topic-Aware Bypass: Don't over-polish sports or entertainment as it kills the "vibe"
        if topic == "Sport" or category == "Sport":
            return

        # Use Gemma 2 2B for Literary Normalization
        final_title = analyst.normalize_headline(title, lang=lang)

        if final_title and final_title.strip().lower() != title.strip().lower():
            # Check semantic similarity to ensure we didn't lose the plot
            from nlp.text_processing import _jaccard_similarity

            if _jaccard_similarity(title, final_title) < 0.35:
                log.warning(f"[style] Rejected over-aggressive polish for {article_id}")
                return

            # Preserve original for transparency/debugging
            db.execute(
                "UPDATE articles SET title = %s, original_title = %s, is_translated = 1 WHERE id = %s",
                (final_title, title, article_id),
                fetch=False,
            )
            log.info(f"[style] Standardized title for article {article_id} using Gemma 2 2B")
            # Re-trigger summary if title changed significantly
            summarize_article_task.delay(article_id, final_title)

    except Exception as e:
        log.error(f"[style] Normalization failed for {article_id}: {e}")


@celery_app.task(rate_limit="15/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def detect_global_story_task(article_id):
    """Detects if a Macedonian article is a translation of a foreign global report."""
    from core.config import LOCAL_TRANSLATION_ENABLED

    if not LOCAL_TRANSLATION_ENABLED:
        return

    row = db.execute_one("SELECT title FROM articles WHERE id = %s", (article_id,))
    if not row or not row.get("title"):
        return

    try:
        import numpy as np

        from core.embeddings import generate_query_embedding
        from utils import redis_client

        # Use the multilingual embedding model (MiniLM-L12) to compare Macedonian
        # directly with global English headlines
        mk_vec = generate_query_embedding(row["title"])
        if not mk_vec:
            return

        # 3. Compare with Global Cache from Redis
        global_data = redis_client.get("presek:global_headlines:v1")
        if not global_data:
            return

        global_heads = json.loads(global_data)  # List of {"title": str, "vec": list}

        best_similarity = 0
        for head in global_heads:
            g_vec = np.array(head["vec"])
            sim = np.dot(mk_vec, g_vec) / (np.linalg.norm(mk_vec) * np.linalg.norm(g_vec))
            if sim > best_similarity:
                best_similarity = sim

        # 4. Verdict (0.82 is a strong semantic match for cross-lingual pairs)
        if best_similarity > 0.82:
            db.execute(
                "UPDATE articles SET is_global = TRUE WHERE id = %s",
                (article_id,),
                fetch=False,
            )
            log.info(
                f"[originality] Flagged article {
                     article_id} as GLOBAL (Sim: {best_similarity:.4f})"
            )

    except Exception as e:
        log.warning(f"[originality] Detection failed for {article_id}: {e}")


@celery_app.task(
    queue="fast-track",
    rate_limit="60/m",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def synthesize_urgent_task(cluster_id, content=None):
    """Priority synthesis for new clusters."""
    return synthesize_cluster_task(cluster_id, content, fast_mode=True)


@celery_app.task(rate_limit="60/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def synthesize_cluster_task(cluster_id, content, retry_attempt=0, fast_mode=False):
    """Generates a multi-perspective synthesis for a cluster with historical continuity."""
    article_rows = _load_cluster_articles_for_synthesis(cluster_id)
    citation_sources = _build_citation_sources(article_rows)
    # We pass the default 'sr' here, but it will be overridden inside the lang loop if needed
    # Actually, it's better to build it inside the loop for each language
    source_context_sr = _build_synthesis_source_context(article_rows, lang="sr")
    source_context_mk = _build_synthesis_source_context(article_rows, lang="mk")

    # In fast mode, we use a slightly shorter token limit but still enough for the full JSON schema
    max_tokens = 1600 if fast_mode else 3200

    # 1. Fetch Historical Context (Cross-Story Memory)
    # We'll fetch this once for the primary language (sr) to use as context for all syntheses
    history_context = ""
    try:
        from core.embeddings import get_cluster_embedding

        current_vec = get_cluster_embedding(cluster_id)
        if current_vec:
            current_vec_str = "[" + ",".join(map(str, current_vec)) + "]"
            # Find semantically similar clusters from the last 7 days (prefer Serbian for context)
            related = db.execute(
                """
                SELECT s.summary, s.generated_article, a.title
                FROM cluster_summaries s
                JOIN articles a ON s.cluster_id = a.cluster_id
                JOIN cluster_metadata m ON s.cluster_id = m.cluster_id
                WHERE s.cluster_id != %s
                  AND s.lang = 'sr'
                  AND s.created_at >= NOW() - INTERVAL '7 days'
                  AND s.created_at < (SELECT MIN(created_at) FROM articles WHERE cluster_id = %s)
                ORDER BY m.centroid <=> %s::vector
                LIMIT 1
            """,
                (cluster_id, cluster_id, current_vec_str),
            )

            if related:
                r = related[0]
                prev_text = r["generated_article"] or r["summary"]
                if prev_text:
                    history_context = f"\nPRETHODEN kontekst (za ovoj nastan ili povrzana tema od izminatite denovi):\n<historical_context>\n{
                        prev_text[:1000]}\n</historical_context>"
    except Exception as e:
        log.warning(f"[tasks/memory] Failed to fetch history for {cluster_id}: {e}")

    legacy_summary = str(content or "").strip()

    # Track shared metrics that only need to be computed once per cluster
    shared_metrics = {
        "impact_score": 0.0,
        "impact_reasoning": "",
        "story_so_far": "",
        "centroid_str": None,
        "deep_metadata": {},
        "pluralism_data": {},
        "sentiment_data": {"sentiment": {"score": 0, "tone": "neutralan"}, "tone_analysis": {}},
        "citation_sources": citation_sources,
        "pulse_score": 50,
        "pluralism_score": 50,
        "analyst_entities": [],
    }
    shared_computed = False

    for lang in SUPPORTED_LANGS:
        try:
            log.info(f"Generating synthesis for cluster {cluster_id} in {lang}")
            prompt_parts = []
            if fast_mode:
                prompt_parts.append(
                    "PROVIDE A BRIEF 1-PARAGRAPH SUMMARY ONLY. FOCUS ON THE CORE EVENT. IGNORE PERSPECTIVES."
                )
            elif history_context:
                prompt_parts.append(history_context)

            prompt_parts.append("novi clanci OD danas:\n<articles_context>")
            current_context = source_context_mk if lang == "mk" else source_context_sr
            if current_context:
                prompt_parts.append(current_context)
            elif legacy_summary:
                prompt_parts.append(legacy_summary)
            prompt_parts.append("</articles_context>")
            full_prompt = "\n\n".join(part for part in prompt_parts if part)

            system_prompt = SYNTHESIS_SYSTEM_PROMPT_MK if lang == "mk" else SYNTHESIS_SYSTEM_PROMPT_SR

            from core.llm_router import SmartModelRouter
            target_model = SmartModelRouter.route_cluster(article_rows, lang=lang)

            if target_model == "enhanced_fallback":
                log.info(f"Router selected local enhanced fallback for cluster {cluster_id} ({lang})")
                raw, provider = None, "enhanced_fallback"
            else:
                raw, provider = _call_ai(
                    full_prompt,
                    system_prompt,
                    json_mode=True,
                    task_type="synthesis",
                    max_tokens=max_tokens,
                    lang=lang,
                    provider_override=target_model,
                )
            res_data = {}

            if raw:
                try:
                    res = clean_json_response(raw)
                except Exception as e:
                    log.error(f"[tasks/synthesis] JSON Parse Error for {cluster_id} ({lang}): {e}. Raw: {raw[:200]}")
                    continue  # Try next language

                res_data = res if isinstance(res, dict) else {}

                # If the AI returned a string instead of a dict, or if the dict is missing core fields,
                # we should treat it as a partial failure and merge with local fallback
                if not isinstance(res, dict) or not res.get("summary") or not res.get("article"):
                    log.info(
                        f"[tasks/synthesis] AI returned unstructured or partial response for {
                             cluster_id} ({lang}), merging with enhanced fallback."
                    )
                    fallback = synthesize_cluster_fallback(article_rows, lang=lang)

                    # Merge: Prefer AI summary if it exists and is long enough and not a leaked JSON, otherwise fallback
                    summary = res_data.get("summary") or (
                        res if isinstance(res, str) and len(res) > 30 and not _looks_like_leaked_json_fragment(res) else fallback["summary"]
                    )
                    generated_article = res_data.get("article") or fallback["generated_article"]
                    synthetic_headline = res_data.get("synthetic_headline") or fallback["synthetic_headline"]
                    synthetic_standfirst = res_data.get("synthetic_standfirst") or fallback["synthetic_standfirst"]
                    perspectives = res_data.get("perspectives") or fallback["perspectives"]
                else:
                    summary = res_data.get("summary", "")
                    generated_article = res_data.get("article", "")
                    synthetic_headline = res_data.get("synthetic_headline", "")
                    synthetic_standfirst = res_data.get("synthetic_standfirst", "")
                    perspectives = res_data.get("perspectives", [])

                # Ensure summary is a string for validation and comparison
                if isinstance(summary, list):
                    summary = "\n".join(str(s) for s in summary)

                verification_report = res_data.get("verification_report")
                quote = validate_person_names(res_data.get("quote", ""))

                if not summary or (isinstance(summary, str) and len(summary) < 20):
                    log.warning(f"[tasks/synthesis] AI returned empty or too short summary for {cluster_id} ({lang})")
                    continue

                # Sanitize for name hallucinations
                summary = validate_person_names(summary)
                generated_article = validate_person_names(generated_article)
                synthetic_headline = validate_person_names(synthetic_headline)
                synthetic_standfirst = validate_person_names(synthetic_standfirst)

                # --- [NEW] 2026 Intelligence: Storyline & Impact ---
                current_story_so_far = validate_person_names(res_data.get("story_so_far", ""))
                impact_data = _ensure_dict(res_data.get("impact_analysis", {}))
                current_impact_score = float(impact_data.get("score", 0.0))
                current_impact_reasoning = impact_data.get("reasoning", "")

                # AI Quality Gate: Hallucination Scanner (SKIP in fast_mode)
                comparison_text = (summary or "") + "\n" + (generated_article or "")
                if (
                    not fast_mode
                    and not _is_grounded_synthesis(comparison_text, current_context or legacy_summary)
                    and retry_attempt < 2
                ):
                    log.warning(f"Hallucination gate failed for cluster {cluster_id} ({lang}), retrying later...")
                    # We don't return here because we might want to try other languages
                    continue

                current_sentiment_data = {
                    "sentiment": res_data.get("sentiment", {}),
                    "tone_analysis": res_data.get("tone_analysis", {}),
                }

                summary, generated_article, perspectives = _sanitize_synthesis_outputs(
                    summary,
                    generated_article,
                    perspectives,
                    article_rows,
                    lang=lang,
                )
                record_runtime_event("synthesis_path", mode=provider or "unknown", fast_mode=fast_mode, lang=lang)

                # Phase 3: Deep Local Analyst (SKIP in fast_mode)
                # Only run shared cluster-wide logic once (on first successful lang, usually sr)
                if not fast_mode and not shared_computed:

                    def _run_analyst_logic():
                        try:
                            # Use semaphore to limit concurrent heavy CPU tasks
                            with _analyst_semaphore:
                                # Run analyst on the current (first successful) summary
                                analyst_text = f"NASLOV: {synthetic_headline}\n{summary}"
                                shared_metrics["deep_metadata"] = analyst.extract_deep_metadata(analyst_text, lang=lang)

                                # Phase 3.1: Pluralism Assessment
                                titles_sources = [
                                    f"{a['source']}: {
                                    a['title']}"
                                    for a in article_rows[:10]
                                ]
                                shared_metrics["pluralism_data"] = analyst.assess_pluralism(titles_sources, lang=lang)

                                # Phase 3.2: Knowledge Graph Update
                                entities = shared_metrics["deep_metadata"].get("entities", [])
                                for entity in entities:
                                    with db.connection() as conn:
                                        with conn.cursor() as cur:
                                            try:
                                                cur.execute(
                                                    """
                                                    INSERT INTO knowledge_entities (name, type, last_seen, total_mentions)
                                                    VALUES (%s, 'PERSON', NOW(), 1)
                                                    ON CONFLICT (name) DO UPDATE SET
                                                        last_seen = NOW()
                                                """,
                                                    (entity,),
                                                )
                                                cur.execute(
                                                    """
                                                    INSERT INTO entity_mentions_daily (entity_name, cluster_id, day)
                                                    VALUES (%s, %s, CURRENT_DATE)
                                                    ON CONFLICT (entity_name, cluster_id, day) DO NOTHING
                                                """,
                                                    (entity, cluster_id),
                                                )
                                                cur.execute(
                                                    """
                                                    UPDATE knowledge_entities
                                                    SET total_mentions = (
                                                        SELECT COUNT(*) FROM entity_mentions_daily WHERE entity_name = %s
                                                    )
                                                    WHERE name = %s
                                                """,
                                                    (entity, entity),
                                                )
                                                conn.commit()
                                            except Exception as e:
                                                log.debug(f"Failed to update entity mentions: {e}")
                                                conn.rollback()
                                                raise
                        except Exception as e:
                            log.error(f"[analyst] Internal logic error: {e}")

                    analyst_thread = threading.Thread(target=_run_analyst_logic)
                    analyst_thread.start()
                    analyst_thread.join(timeout=600)  # 10 minute limit for low-core CPUs

                    if analyst_thread.is_alive():
                        log.warning(f"[analyst] Timeout reached for cluster {cluster_id}")

                    shared_metrics["deep_metadata"] = _ensure_dict(shared_metrics["deep_metadata"])
                    shared_metrics["pluralism_data"] = _ensure_dict(shared_metrics["pluralism_data"])

                    shared_metrics["impact_score"] = current_impact_score
                    shared_metrics["impact_reasoning"] = current_impact_reasoning
                    shared_metrics["story_so_far"] = current_story_so_far
                    shared_metrics["sentiment_data"] = current_sentiment_data

                    shared_metrics["pulse_score"] = shared_metrics["deep_metadata"].get("pulse", 50)
                    shared_metrics["pluralism_score"] = shared_metrics["pluralism_data"].get("score", 50)
                    shared_metrics["analyst_entities"] = shared_metrics["deep_metadata"].get("entities") or []

                    # Calculate Cluster Centroid (Semantic Center)
                    centroid = _compute_centroid_from_values(
                        [a.get("embedding") for a in article_rows if a.get("embedding")]
                    )
                    shared_metrics["centroid_str"] = (
                        f"[{','.join(map(str, centroid))}]" if centroid and len(centroid) == 384 else None
                    )

                    shared_computed = True

            else:
                if provider == "enhanced_fallback":
                    log.info(f"Using pre-computed enhanced fallback for {cluster_id} ({lang})")
                else:
                    log.warning(
                        f"[tasks/synthesis] AI provider {provider} returned no content for {cluster_id} ({lang}), using enhanced fallback"
                    )
                fallback = synthesize_cluster_fallback(article_rows, lang=lang)
                summary = fallback.get("summary", "")
                perspectives = fallback.get("perspectives", [])
                synthetic_headline = fallback.get("synthetic_headline", "")
                synthetic_standfirst = fallback.get("synthetic_standfirst", "")
                generated_article = fallback.get("generated_article", "")
                verification_report = None
                quote = ""
                current_sentiment_data = shared_metrics["sentiment_data"]

                if not shared_computed:
                    shared_metrics["impact_score"] = 0.0
                    shared_metrics["impact_reasoning"] = ""
                    shared_metrics["story_so_far"] = ""
                    shared_computed = True  # Mark as computed even if fallback

            summary, generated_article, perspectives = _sanitize_synthesis_outputs(
                summary,
                generated_article,
                perspectives,
                article_rows,
                lang=lang,
            )

            if summary or perspectives:
                # Use shared metrics for DB save
                pulse_score = shared_metrics["pulse_score"]
                pluralism_score = shared_metrics["pluralism_score"]
                pluralism_data = shared_metrics["pluralism_data"]
                if not pluralism_data:
                    pluralism_data = {
                        "score": pluralism_score,
                        "verdict": "Procenkata e vo tek." if lang == "mk" else "Procena je u toku.",
                    }

                key_facts = res_data.get("key_facts")
                if not key_facts or not isinstance(key_facts, list):
                    key_facts = shared_metrics["deep_metadata"].get("facts") or _fallback_key_facts(
                        article_rows, summary
                    )

                if lang == "mk" and key_facts:
                    # Translate Serbian Latin key facts to Macedonian Cyrillic
                    from core.ai_engine import _call_ai, clean_json_response
                    facts_text = "\n".join(f"- {f}" for f in key_facts)
                    translate_prompt = (
                        "Преведи ги следните клучни факти од српски (латиница) на чист македонски литературен јазик (кирилица).\n"
                        "Врати ги преведените факти како чист JSON од тип {\"facts\": [\"факт 1\", \"факт 2\", ...]} без никакви дополнителни објаснувања, markdown или воведи.\n\n"
                        f"{facts_text}"
                    )
                    try:
                        raw_trans, _ = _call_ai(
                            prompt=translate_prompt,
                            system="Ти си професионален преведувач за вести од српски на македонски јазик.",
                            task_type="translation",
                            max_tokens=500,
                            json_mode=True,
                            lang="mk"
                        )
                        if raw_trans:
                            trans_data = clean_json_response(raw_trans)
                            if isinstance(trans_data, dict) and trans_data.get("facts"):
                                translated_facts = trans_data["facts"]
                                if isinstance(translated_facts, list) and len(translated_facts) == len(key_facts):
                                    key_facts = translated_facts
                                    log.info("Successfully translated key_facts from Serbian to Macedonian")
                    except Exception as e:
                        log.warning(f"Failed to translate key_facts to Macedonian: {e}")

                # Archive current summary before updating (Evolution Log)
                db.execute(
                    """INSERT INTO cluster_summary_history (cluster_id, lang, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, verification_report, citation_sources, tone_analysis, created_at, key_facts, analyst_entities)
                       SELECT cluster_id, lang, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, verification_report, citation_sources, tone_analysis, created_at, key_facts, analyst_entities
                       FROM cluster_summaries WHERE cluster_id = %s AND lang = %s""",
                    (cluster_id, lang),
                    fetch=False,
                )

                if res_data.get("full_article_draft") and len(res_data["full_article_draft"]) > 100:
                    db.execute(
                        """INSERT INTO cluster_summaries (cluster_id, lang, summary, generated_article, synthetic_headline, synthetic_standfirst, created_at, citation_sources, key_facts, analyst_entities, pulse_score, pluralism_score, narrative_diversity)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (cluster_id, lang) DO UPDATE SET
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
                        (
                            cluster_id,
                            lang,
                            summary,
                            generated_article,
                            synthetic_headline,
                            synthetic_standfirst,
                            datetime.datetime.now(),
                            json.dumps(shared_metrics["citation_sources"]),
                            json.dumps(key_facts),
                            json.dumps(shared_metrics["analyst_entities"]),
                            float(pulse_score),
                            float(pluralism_score),
                            json.dumps(pluralism_data),
                        ),
                        fetch=False,
                    )
                else:
                    db.execute(
                        """INSERT INTO cluster_summaries (cluster_id, lang, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, created_at, sentiment, tone_analysis, verification_report, quote, centroid, citation_sources, key_facts, analyst_entities, pulse_score, pluralism_score, narrative_diversity, storyline_narrative)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (cluster_id, lang) DO UPDATE SET
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
                        (
                            cluster_id,
                            lang,
                            summary,
                            json.dumps(perspectives),
                            generated_article,
                            synthetic_headline,
                            synthetic_standfirst,
                            datetime.datetime.now(),
                            json.dumps(shared_metrics["sentiment_data"]),
                            json.dumps(res_data.get("tone_analysis", {})),
                            (json.dumps(verification_report) if verification_report else None),
                            quote,
                            shared_metrics["centroid_str"],
                            json.dumps(shared_metrics["citation_sources"]),
                            json.dumps(key_facts),
                            json.dumps(shared_metrics["analyst_entities"]),
                            float(pulse_score),
                            float(pluralism_score),
                            json.dumps(pluralism_data),
                            shared_metrics["story_so_far"],
                        ),
                        fetch=False,
                    )
                log.info(f"Successfully synthesized cluster {cluster_id} for {lang}")

        except Exception as e:
            log.error(f"Synthesis failed for cluster {cluster_id} in {lang}: {e}", exc_info=True)
            continue

    # --- [Final Steps] Cluster-wide updates and events ---
    if shared_computed:
        # Update Metadata with Impact Score
        db.execute(
            """
            UPDATE cluster_metadata
            SET impact_score = %s, impact_explanation = %s
            WHERE cluster_id = %s
        """,
            (shared_metrics["impact_score"], shared_metrics["impact_reasoning"], cluster_id),
            fetch=False,
        )

        # Publish SSE event
        try:
            from utils import publish_event

            is_breaking = False
            if article_rows:
                from core.config import BREAKING_SCORE_THRESHOLD
                from utils import score_cluster

                is_breaking = score_cluster(article_rows) >= BREAKING_SCORE_THRESHOLD

            publish_event(
                "updates",
                {
                    "type": "cluster_synthesis_updated",
                    "cluster_id": cluster_id,
                    "is_breaking": is_breaking,
                    "impact_score": shared_metrics["impact_score"],
                    "headline": article_rows[0].get("title", "") if article_rows else "",
                    "time": datetime.datetime.now().isoformat(),
                },
            )
        except Exception as pub_err:
            log.warning(f"[tasks] Failed to publish SSE event for {cluster_id}: {pub_err}")

        # Real-time Sports Score Alert (once)
        try:
            from nlp.categories import detect_topic

            all_titles = " ".join([a.get("title") or "" for a in article_rows])
            if detect_topic(all_titles) == "Sport":
                from notifier import BreakingNewsNotifier

                from core.config import NTFY_TOPIC
                from nlp.generation import _extract_sports_scores

                latest_scores = _extract_sports_scores(article_rows[0].get("title") or "") + _extract_sports_scores(
                    article_rows[0].get("description") or ""
                )
                if latest_scores:
                    latest_score = latest_scores[0]
                    notifier = BreakingNewsNotifier(NTFY_TOPIC)
                    notifier.notify_score_change(article_rows[0].get("title"), latest_score, cluster_id)
        except Exception as e:
            log.warning(f"[tasks/sports] Score alert failed: {e}")

        # Improved image logic: if no image or ONLY weak visuals exist, generate art
        strong_img = db.execute_one(
            "SELECT 1 FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL AND image_url NOT LIKE '%%placeholder%%' LIMIT 1",
            (cluster_id,),
        )
        if not strong_img:
            # We use first summary for placeholder generation (usually Serbian)
            summary_row = db.execute_one(
                "SELECT summary FROM cluster_summaries WHERE cluster_id = %s LIMIT 1", (cluster_id,)
            )
            if summary_row:
                svg_content = generate_local_placeholder(cluster_id, summary_row["summary"])
                img_url = generate_cover_art(cluster_id, svg_content)
                if img_url:
                    db.execute(
                        "UPDATE articles SET image_url = %s WHERE cluster_id = %s AND (image_url IS NULL OR image_url LIKE '%%placeholder%%')",
                        (img_url, cluster_id),
                        fetch=False,
                    )

        try:
            invalidate_cluster_caches(cluster_id)
            if os.environ.get("REDIS_URL"):
                generate_cluster_metadata_task.delay()
        except Exception as err:
            log.warning(f"[tasks] Finalization error for {cluster_id}: {err}")
    else:
        # Fallback if all languages failed
        log.error(f"All synthesis attempts failed for cluster {cluster_id}")


@celery_app.task
def auto_summarize_task(cluster_ids: list[str] = None):
    """Dispatch summarization/synthesis tasks for top clusters or targeted clusters."""
    from core.ai_engine import auto_summarize_top_clusters

    auto_summarize_top_clusters(target_cluster_ids=cluster_ids)


@celery_app.task
def refresh_cluster_centroid_task(cluster_id):
    """
    Recalculates and updates the semantic centroid for a cluster.
    """
    from core.database import db_manager as db
    from core.embeddings import get_cluster_embedding

    new_centroid = get_cluster_embedding(cluster_id)
    if new_centroid:
        vec_str = "[" + ",".join(map(str, new_centroid)) + "]"
        db.execute(
            "UPDATE cluster_metadata SET centroid = %s::vector WHERE cluster_id = %s",
            (vec_str, cluster_id),
            fetch=False,
        )
        log.info(f"[tasks] Centroid updated for cluster {cluster_id}")


@celery_app.task
def extract_entities_task(*args, hours=24, target_clusters=None, **kwargs):
    """Extract entities for top clusters using local hybrid logic (Lexicon + spaCy + Regex)."""
    try:
        if target_clusters:
            rows = db.execute(
                """
                SELECT cluster_id, array_agg(DISTINCT title) as titles, MAX(description) as desc
                FROM articles WHERE cluster_id = ANY(%s) GROUP BY cluster_id
            """,
                (target_clusters,),
            )
        else:
            cutoff = datetime.datetime.now() - datetime.timedelta(hours=int(hours or 24))
            rows = db.execute(
                """
                SELECT cluster_id, array_agg(DISTINCT title) as titles, MAX(description) as desc
                FROM articles WHERE created_at >= %s GROUP BY cluster_id
                HAVING COUNT(DISTINCT source) >= 2 LIMIT 50
            """,
                (cutoff,),
            )

        for r in rows:
            text = f"{' '.join(r['titles'])} {r['desc'] or ''}"

            # Use hybrid local extractor (curated lexicon + spaCy NER + regex)
            entities = extract_entities(text, max_entities=8)

            if entities:
                from core.entities import update_knowledge_graph

                # update_knowledge_graph calculates local sentiment automatically
                update_knowledge_graph(entities, context_text=text)

                for ent in entities:
                    db.execute(
                        "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (r["cluster_id"], ent.get("name"), ent.get("type")),
                        fetch=False,
                    )

        invalidate_public_data_caches()
        from tasks import utils

        utils.record_task_event("extract_entities", "ok", "clusters:recent:local")
    except Exception as e:
        log.error(f"[tasks] Local entity extraction failed: {e}")


@celery_app.task
def classify_topics_task(*args, **kwargs):
    """Classify default 'vesti' clusters using local rule-based detection."""
    try:
        # Increased limit as local classification is nearly free
        rows = db.execute("SELECT cluster_id, title FROM articles WHERE topic = 'vesti' LIMIT 200")
        for r in rows:
            topic = detect_topic(r["title"])
            if topic != "vesti":
                db.execute(
                    "UPDATE articles SET topic = %s WHERE cluster_id = %s",
                    (topic, r["cluster_id"]),
                    fetch=False,
                )
    except Exception as e:
        log.error(f"[tasks] Topic classification failed: {e}")
    else:
        invalidate_public_data_caches()
        from tasks import utils

        utils.record_task_event("classify_topics", "ok", "clusters:recent:local")


@celery_app.task
def recategorize_clusters_task(*args, **kwargs):
    """Verify if 'Srbija' articles belong in specialized categories using rule-based detection."""
    try:
        rows = db.execute("SELECT cluster_id, title, description FROM articles WHERE category = 'Srbija' LIMIT 20")
        for r in rows:
            # Rule-based first (Free)
            res = detect_category(r["title"], description=r.get("description", ""))
            if res != "Srbija":
                db.execute(
                    "UPDATE articles SET category = %s WHERE cluster_id = %s",
                    (res, r["cluster_id"]),
                    fetch=False,
                )
                continue
    except Exception as e:
        from tasks import utils

        utils.record_task_event("recategorize_clusters", "error", "clusters:recent")
        log.error(f"[tasks] Recategorization failed: {e}")
    else:
        invalidate_public_data_caches()
        from tasks import utils

        utils.record_task_event("recategorize_clusters", "ok", "clusters:recent")


@celery_app.task
def generate_cluster_metadata_task(hours=24, target_clusters=None):
    """Tag recent clusters with metadata (entities, source count, centroid, and representative image)."""
    try:
        if target_clusters:
            rows = db.execute(
                """
                SELECT cluster_id, array_agg(DISTINCT source) as sources, array_agg(DISTINCT title) as titles,
                       array_agg(DISTINCT topic) as topics,
                       mode() WITHIN GROUP (ORDER BY category) as dominant_category,
                       array_agg(embedding) FILTER (WHERE embedding IS NOT NULL) as embeddings
                FROM articles WHERE cluster_id = ANY(%s)
                GROUP BY cluster_id
            """,
                (target_clusters,),
            )
        else:
            cutoff = datetime.datetime.now() - datetime.timedelta(hours=int(hours or 24))
            rows = db.execute(
                """
                SELECT cluster_id, array_agg(DISTINCT source) as sources, array_agg(DISTINCT title) as titles,
                       array_agg(DISTINCT topic) as topics,
                       mode() WITHIN GROUP (ORDER BY category) as dominant_category,
                       array_agg(embedding) FILTER (WHERE embedding IS NOT NULL) as embeddings
                FROM articles WHERE created_at >= %s
                GROUP BY cluster_id
            """,
                (cutoff,),
            )
        for r in rows:
            entities = db.execute(
                "SELECT entity_name, entity_type FROM cluster_entities WHERE cluster_id = %s",
                (r["cluster_id"],),
            )
            entity_candidates = [dict(e) for e in entities]
            final_tags = extract_cluster_tags_locally(
                titles=r["titles"],
                entity_names=entity_candidates,
                sources=r["sources"],
                top_n=8,
            )
            if not final_tags:
                final_tags = filter_cluster_tags(r["sources"], limit=4)

            # Calculate Centroid (Semantic Center)
            centroid = _compute_centroid_from_values(r.get("embeddings") or [])
            centroid_str = f"[{','.join(map(str, centroid))}]" if centroid and len(centroid) == 384 else None

            # Smart image selection: prefer high-quality sources and non-placeholder URLs
            img_row = db.execute_one(
                """
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
            """,
                (r["cluster_id"],),
            )

            rep_image = img_row["image_url"] if img_row else None

            if not rep_image:
                # If we still have no image, try to generate one (AI cover art)
                svg_content = generate_local_placeholder(r["cluster_id"], r["titles"][0] if r["titles"] else "vest")
                rep_image = generate_cover_art(r["cluster_id"], svg_content)

            curr_meta = db.execute_one(
                "SELECT representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = %s",
                (r["cluster_id"],),
            )
            dominant_color = curr_meta["dominant_color"] if curr_meta else None

            if rep_image and (not curr_meta or curr_meta["representative_image"] != rep_image or not dominant_color):
                import asyncio

                dominant_color = asyncio.run(get_dominant_color(rep_image))

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
                (
                    r["cluster_id"],
                    final_tags,
                    r["topics"],
                    rep_image,
                    dominant_color,
                    centroid_str,
                    r["dominant_category"],
                ),
                fetch=False,
            )
        invalidate_public_data_caches()
        from tasks import utils

        utils.record_task_event("cluster_metadata", "ok", "clusters:recent")
    except Exception as e:
        from tasks import utils

        utils.record_task_event("cluster_metadata", "error", "clusters:recent")
        log.error(f"[tasks] Cluster metadata generation failed: {e}")


@celery_app.task(rate_limit="1/h")
def recluster_recent_articles_task(hours=24, limit=800):
    """Re-assign cluster IDs for recent articles using the current clustering logic."""
    try:
        import core.clustering as clustering

        hours = max(1, int(hours or 24))
        limit = max(1, int(limit or 800))
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
        rows = (
            db.execute(
                """
            SELECT id, cluster_id, title, source, category, topic, created_at, embedding
            FROM articles
            WHERE created_at >= %s
            ORDER BY created_at ASC, id ASC
            LIMIT %s
            """,
                (cutoff, limit),
            )
            or []
        )

        if not rows:
            from tasks import utils

            utils.record_task_event("recluster_recent", "empty", f"hours:{hours}")
            return {
                "reclustered": 0,
                "touched_clusters": 0,
                "hours": hours,
                "limit": limit,
            }

        recent_articles = []
        batch_clusters = []
        updates = []
        touched_clusters = set()

        for row in rows:
            title = str(row.get("title") or "").strip()
            category = row.get("category")
            topic = str(row.get("topic") or "vesti").strip() or "vesti"
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
                    if topic == "vesti" or not topic:
                        incoming_entities = clustering._extract_title_entities(title)
                        candidate_entities = candidate.get("entities", set())
                        shared_entities = (
                            incoming_entities.intersection(candidate_entities)
                            if incoming_entities and candidate_entities
                            else set()
                        )
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
                batch_clusters.append(
                    {
                        "cid": new_cluster_id,
                        "embedding": parsed_embedding,
                        "category": category,
                        "topic": topic,
                        "title": title,
                        "entities": clustering._extract_title_entities(title),
                    }
                )

            recent_articles.insert(
                0,
                {
                    "title": title,
                    "cluster_id": new_cluster_id,
                    "created_at": created_at,
                    "category": category,
                    "topic": topic,
                    "source": source,
                },
            )
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
            # Whitelist of tables that can be safely deleted from
            _ALLOWED_CLEANUP_TABLES = (
                "cluster_summaries",
                "cluster_metadata",
                "cluster_entities",
                "reactions",
            )
            for table in _ALLOWED_CLEANUP_TABLES:
                db.execute(
                    f"DELETE FROM {table} WHERE cluster_id = ANY(%s)",
                    (touched,),
                    fetch=False,
                )

            extract_entities_task.apply_async(kwargs={"hours": hours, "target_clusters": touched}, countdown=5)
            generate_cluster_metadata_task.apply_async(kwargs={"hours": hours, "target_clusters": touched}, countdown=5)
            auto_summarize_task.apply_async(args=(touched,), countdown=2)
            invalidate_public_data_caches()

        from tasks import utils

        utils.record_task_event("recluster_recent", "ok", f"articles:{len(updates)}")
        return {
            "reclustered": len(updates),
            "touched_clusters": len(touched_clusters),
            "hours": hours,
            "limit": limit,
        }
    except Exception as e:
        from tasks import utils

        utils.record_task_event("recluster_recent", "error", "clusters:recent")
        log.error(f"[tasks] Recent recluster failed: {e}")
        raise


@celery_app.task(rate_limit="1/h")
def repair_split_clusters_task(hours=48, limit=1200, dry_run=False):
    """Merge recent near-duplicate clusters that ingestion split too conservatively."""
    try:
        hours = max(1, int(hours or 48))
        limit = max(2, int(limit or 1200))
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
        rows = db.execute(
            """
            SELECT a.cluster_id,
                   mode() WITHIN GROUP (ORDER BY a.country) as country,
                   mode() WITHIN GROUP (ORDER BY a.category) as category,
                   mode() WITHIN GROUP (ORDER BY a.topic) as topic,
                   COUNT(*) as article_count,
                   MIN(COALESCE(a.ingested_at, a.created_at)) as first_article,
                   MAX(COALESCE(a.ingested_at, a.created_at)) as latest_article,
                   array_agg(DISTINCT a.title) as titles,
                   COALESCE(cm.tags, '{}') as tags,
                   cm.centroid
            FROM articles a
            LEFT JOIN cluster_metadata cm ON cm.cluster_id = a.cluster_id
            WHERE COALESCE(a.ingested_at, a.created_at) >= %s
              AND a.cluster_id IS NOT NULL
            GROUP BY a.cluster_id, cm.tags, cm.centroid
            ORDER BY latest_article DESC
            LIMIT %s
            """,
            (cutoff, limit),
        ) or []

        candidates = []
        for i, left in enumerate(rows):
            for right in rows[i + 1 :]:
                lang = "mk" if left.get("country") == "MK" else "sr"
                score = _split_cluster_merge_score(left, right, lang=lang)
                if score > 0:
                    candidates.append((score, left, right))
        candidates.sort(key=lambda item: item[0], reverse=True)

        row_by_id = {row["cluster_id"]: row for row in rows}
        parent = {row["cluster_id"]: row["cluster_id"] for row in rows}

        def find(cluster_id):
            while parent.get(cluster_id, cluster_id) != cluster_id:
                parent[cluster_id] = parent.get(parent[cluster_id], parent[cluster_id])
                cluster_id = parent[cluster_id]
            return cluster_id

        def choose_target(left_id, right_id):
            left = row_by_id[left_id]
            right = row_by_id[right_id]
            left_count = int(left.get("article_count") or 0)
            right_count = int(right.get("article_count") or 0)
            if left_count > right_count:
                return left_id, right_id
            if right_count > left_count:
                return right_id, left_id
            return (
                (left_id, right_id)
                if (left.get("first_article") or datetime.datetime.max)
                <= (right.get("first_article") or datetime.datetime.max)
                else (right_id, left_id)
            )

        merge_scores = {}
        touched_clusters = set()
        for score, left, right in candidates:
            left_root = find(left["cluster_id"])
            right_root = find(right["cluster_id"])
            if left_root == right_root:
                continue

            target_id, source_id = choose_target(left_root, right_root)
            parent[source_id] = target_id
            merge_scores[source_id] = max(float(score), merge_scores.get(source_id, 0.0))
            touched_clusters.update({target_id, source_id})

        canonical_merges = []
        for source_id, score in sorted(merge_scores.items(), key=lambda item: item[1], reverse=True):
            target_id = find(source_id)
            if source_id != target_id:
                canonical_merges.append({"source": source_id, "target": target_id, "score": round(score, 4)})

        touched_clusters = set()
        for merge in canonical_merges:
            target_id = merge["target"]
            source_id = merge["source"]
            touched_clusters.update({target_id, source_id})

            if not dry_run:
                db.execute(
                    "UPDATE articles SET cluster_id = %s WHERE cluster_id = %s",
                    (target_id, source_id),
                    fetch=False,
                )

        if canonical_merges and not dry_run:
            touched = sorted(touched_clusters)
            for table in ("cluster_summaries", "cluster_metadata", "cluster_entities", "reactions"):
                db.execute(f"DELETE FROM {table} WHERE cluster_id = ANY(%s)", (touched,), fetch=False)

            extract_entities_task.apply_async(kwargs={"hours": hours, "target_clusters": touched}, countdown=5)
            generate_cluster_metadata_task.apply_async(kwargs={"hours": hours, "target_clusters": touched}, countdown=10)
            auto_summarize_task.apply_async(args=(touched,), countdown=20)
            invalidate_public_data_caches()

        from tasks import utils

        utils.record_task_event("repair_split_clusters", "ok", f"merges:{len(canonical_merges)}")
        return {"merges": canonical_merges, "dry_run": bool(dry_run), "hours": hours, "limit": limit}
    except Exception as e:
        from tasks import utils

        utils.record_task_event("repair_split_clusters", "error", "clusters:recent")
        log.error(f"[tasks] Split cluster repair failed: {e}")
        raise


@celery_app.task
def auto_repair_sources_task():
    """Bridge to ingestion module for repair task."""
    from tasks.ingestion_task import auto_repair_sources_task as _task

    return _task()


@celery_app.task(rate_limit="5/m")
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
        if get_celery_queue_depth() >= _BACKFILL_QUEUE_DEPTH_LIMIT:
            log.info("[tasks] Backfill cover art skipping: queue depth limit exceeded.")
            return

        try:
            if redis_client.get(cooldown_key):
                log.info("Cover art backfill paused due to Pollinations cooldown.")
                return
        except Exception as e:
            log.debug(f"Failed to check Redis cooldown: {e}")

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


@celery_app.task
def generate_embeddings_task():
    """Generate pgvector embeddings for articles that don't have one yet."""
    try:
        from core.embeddings import embed_recent_articles

        embed_recent_articles()
    except Exception as e:
        log.warning(f"[tasks] Embedding generation failed: {e}")


@celery_app.task
def discover_storylines_task():
    """Discover evolving storylines from news clusters."""
    try:
        from core.topic_discovery import discovery_engine

        discovery_engine.run_discovery(lookback_hours=48)
        discovery_engine.refresh_storyline_metadata()
    except Exception as e:
        log.warning(f"[tasks] Storyline discovery failed: {e}")


def _is_grounded_synthesis(synthesis_text: str, source_context: str) -> bool:
    if not synthesis_text or not source_context:
        return True

    from nlp.keywords import _extract_capitalized_phrases
    from nlp.utils import transliterate

    source_latin = transliterate(source_context).casefold()
    context_entities = {
        transliterate(phrase).casefold()
        for phrase in _extract_capitalized_phrases(source_context)
        if len(str(phrase or "").strip()) >= 4
    }

    allowed_singletons = {
        "srbij",
        "beograd",
        "albanij",
        "eu",
        "vmro-dpmne",
        "iran",
        "ormuskiot tesnec",
        "dojran",
        "sad",
        "teksas",
        "nato",
        "obedinetite nacii",
        "on",
        "ukrain",
        "rusij",
        "sdsm",
        "vasington",
        "teheran",
        "bliskiot istok",
        "persiskiot zaliv",
        "zapadniot balkan",
        "evropskata unija",
        "brisel",
        "moskva",
        "kiev",
        "izrael",
        "gaza",
        "liban",
        "crna gora",
        "grcij",
        "bugarij",
        "makedon",
        "republik",
        "severn",
        "ahmet",
        "mickosk",
        "siljanovsk",
        "pendarovsk",
        "kovacevsk",
        "filipc",
        "gruevsk",
        "zaev",
        "presek",
        "bitol",
        "ohrid",
        "tetovo",
        "kumanovo",
        "gostivar",
        "skopj",
        "beograd",
        "vinic",
        "veles",
        "stip",
        "strumic",
        "prilep",
        "sri lanka",
        "kiribati",
        "si dzinping",
        "bajden",
        "tramp",
        "putin",
        "zelenski",
        "makron",
        "erdogan",
        "vucic",
        "rama",
        "osman",
        "maricic",
        "kostadinovska-stojcevska",
        "biserka",
        "bocvarski",
        "liga na sampioni",
        "premier liga",
        "real madrid",
        "barselona",
        "mancester junajted",
        "baern minhen",
        "stef kari",
        "lebron dzejms",
        "jokic",
        "doncic",
        "djokovic",
        "alkaraz",
        "siner",
        "janik siner",
        "vinisius",
        "vinisius zunior",
        "mbape",
        "haland",
        "elmas",
        "elif elmas",
        "pandev",
    }

    hallucinated_count = 0
    for phrase in _extract_capitalized_phrases(synthesis_text):
        clean = str(phrase or "").strip().replace("\n", " ")
        if len(clean) < 4:
            continue
        if clean.split()[0].lower() in {"od", "vo", "na", "so", "za", "niz", "u", "iz"}:
            clean_parts = clean.split()[1:]
            if not clean_parts:
                continue
            clean = " ".join(clean_parts)
            if len(clean) < 3:
                continue

        words = [part for part in clean.replace("-", " ").split() if part]
        is_acronym = clean.isupper()

        # Stricter check for multi-word entities (proper names)
        # Single words are often common nouns or noise, so we are more lenient
        if len(words) < 2 and not is_acronym:
            continue

        folded = transliterate(clean).casefold()
        if folded in context_entities:
            continue

        # Check allowed_singletons with word boundary awareness or as substrings for longer phrases
        is_allowed = False
        for allowed in allowed_singletons:
            if allowed == folded:
                is_allowed = True
                break
            if len(allowed) > 5 and allowed in folded:
                is_allowed = True
                break

        if is_allowed:
            continue

        if folded in source_latin:
            continue

        # Fuzzy/partial matching for linguistic variations (e.g., Premijer vs Premierot)
        meaningful_words = [
            word.casefold()
            for word in re.findall(r"[A-Za-zA-Za-z\u0400-\u04FF0-9-]{4,}", folded)
            if word.casefold()
            not in {"ministerkata", "ministerot", "pretsedatelot", "vladata", "premierot", "premijer"}
        ]

        # If it's a multi-word entity, check if the "core" (longest words) are in the source
        if meaningful_words:
            # Check if all long meaningful words are present (even as substrings)
            match_count = 0
            for mw in meaningful_words:
                # Basic substring check for grammatical cases (e.g., Mickoskog -> Mickoski)
                # We check first 6 chars for longer words
                mw_stem = mw[:6] if len(mw) > 7 else mw
                if mw_stem in source_latin or any(mw_stem in s_ent for s_ent in context_entities):
                    match_count += 1

            if match_count >= len(meaningful_words):
                continue

        log.warning(f"[ai/hallucination] Hallucinated entity detected in synthesis: {clean} (folded: {folded})")
        hallucinated_count += 1

    # Allow more minor hallucinations for long syntheses to prevent infinite retry loops
    # especially for Macedonian where capitalization patterns differ
    if hallucinated_count > 3:
        return False
    if hallucinated_count >= 1 and len(synthesis_text) < 1000:
        return False

    return True


@celery_app.task
def backfill_cluster_summaries_task(days=30, lang="sr"):
    """Generate cluster summaries for all existing clusters that don't have them yet."""
    try:
        from core.config import AUTO_SUMMARIZE_MIN_SRC
        from core.database import db_manager as db

        # Get all clusters with articles but no summaries
        rows = db.execute(
            """
            SELECT DISTINCT a.cluster_id
            FROM articles a
            WHERE a.cluster_id IS NOT NULL
            AND a.created_at >= NOW() - make_interval(days => %s)
            AND NOT EXISTS (
                SELECT 1 FROM cluster_summaries cs
                WHERE cs.cluster_id = a.cluster_id AND cs.lang = %s
            )
            """,
            (days, lang),
        )

        if not rows:
            log.info(f"[tasks] No clusters found for backfill (lang={lang})")
            return

        cluster_ids = [row["cluster_id"] for row in rows]
        log.info(f"[tasks] Backfilling summaries for {len(cluster_ids)} clusters (lang={lang})")

        for cluster_id in cluster_ids:
            try:
                # Check if this cluster has enough sources
                src_rows = db.execute(
                    "SELECT DISTINCT source FROM articles WHERE cluster_id = %s",
                    (cluster_id,),
                )

                if len(src_rows) < AUTO_SUMMARIZE_MIN_SRC:
                    log.debug(f"[tasks] Skipping cluster {cluster_id} - only {len(src_rows)} source(s)")
                    continue

                # Load articles for this cluster
                article_rows = db.execute(
                    "SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at ASC",
                    (cluster_id,),
                )

                if not article_rows:
                    continue

                # Generate summary using fallback (local) synthesis
                from nlp.generation import synthesize_cluster_fallback

                fallback_result = synthesize_cluster_fallback(article_rows, lang=lang)

                if fallback_result["summary"] or fallback_result["generated_article"]:
                    # Store the summary in database
                    db.execute(
                        """
                        INSERT INTO cluster_summaries
                        (cluster_id, lang, summary, generated_article, synthetic_headline,
                         synthetic_standfirst, created_at, perspectives, key_facts, analyst_entities)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                        ON CONFLICT (cluster_id, lang) DO UPDATE SET
                        summary = EXCLUDED.summary,
                        generated_article = EXCLUDED.generated_article,
                        synthetic_headline = EXCLUDED.synthetic_headline,
                        synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                        created_at = NOW(),
                        perspectives = EXCLUDED.perspectives,
                        key_facts = EXCLUDED.key_facts,
                        analyst_entities = EXCLUDED.analyst_entities
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
                        ),
                    )
                    log.info(f"[tasks] Generated summary for cluster {cluster_id} (lang={lang})")
                else:
                    log.debug(f"[tasks] No summary generated for cluster {cluster_id}")

            except Exception as e:
                log.warning(f"[tasks] Failed to generate summary for cluster {cluster_id}: {e}")

        log.info(f"[tasks] Completed backfill for {lang} language clusters")

    except Exception as e:
        log.error(f"[tasks] Backfill cluster summaries failed: {e}")
        raise


@celery_app.task
def refine_knowledge_graph_sentiment_task():
    """Asynchronously refine entities and relationships in the knowledge graph using deep LLM sentiment analysis."""
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
