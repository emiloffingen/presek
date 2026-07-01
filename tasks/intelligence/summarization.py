import re

from core.entities import validate_person_names
from core.prompts import (
    SUMMARY_SYSTEM_PROMPT_MK,
    SUMMARY_SYSTEM_PROMPT_SR,
)
from nlp import (
    summarize_article_fallback,
)
from nlp.utils import extract_clean_summary_text
from tasks.intelligence._constants import *  # noqa: F403
from tasks.intelligence._queue import _skip_when_intel_backlog
from tasks.utils import (
    invalidate_public_data_caches,
    log,
)


@celery_app.task(
    name="tasks.intelligence.summarize_articles_batch_task",
    soft_time_limit=2700,
    time_limit=3000,
)
def summarize_articles_batch_task(article_ids):
    """Batch processes AI summarization for articles."""
    for article_id in article_ids:
        summarize_article_task(article_id)


@celery_app.task(
    name="tasks.intelligence.summarize_articles_local_batch_task",
    soft_time_limit=2700,
    time_limit=3000,
)
def summarize_articles_local_batch_task(article_ids):
    """Batch summarize using local Gemma only (no paid/limited API providers)."""
    for article_id in article_ids:
        summarize_article_task(article_id, local_only=True)


@celery_app.task(name="tasks.intelligence.detect_global_stories_batch_task")
def detect_global_stories_batch_task(article_ids):
    """Batch processes global story detection for articles."""
    if _skip_when_intel_backlog("global story detection batch"):
        return
    for article_id in article_ids:
        detect_global_story_task(article_id)


@celery_app.task(name="tasks.intelligence.standardize_article_styles_batch_task")
def standardize_article_styles_batch_task(article_ids):
    """Batch processes style standardization for articles."""
    if _skip_when_intel_backlog("style standardization batch"):
        return
    for article_id in article_ids:
        standardize_article_style_task(article_id)


@celery_app.task(name="tasks.intelligence.summarize_article_task", rate_limit="50/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def summarize_article_task(article_id, final_title=None, local_only=False):
    """Refines article content using AI summarization."""
    row = db.execute_one(
        "SELECT title, description, full_content, topic, category, summary FROM articles WHERE id = %s",
        (article_id,),
    )
    if not row:
        return
    if row.get("summary"):
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
        provider_override="local" if local_only else None,
        exclude_providers=_REMOTE_SUMMARY_PROVIDERS if local_only else None,
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
        final_text = validate_person_names(extract_clean_summary_text(final_text))
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
            clean_fallback = extract_clean_summary_text(fallback)
            db.execute(
                "UPDATE articles SET summary = %s WHERE id = %s",
                (clean_fallback, article_id),
                fetch=False,
            )
            invalidate_public_data_caches()

_DELEGATED = frozenset({'CLUSTER_LOOKBACK', '_call_ai', '_sanitize_synthesis_outputs', 'acquire_task_lock', 'analyst', 'average_embeddings', 'celery_app', 'clean_extracted_article_text', 'clean_json_response', 'db', 'deShout', 'detect_category', 'detect_topic', 'extract_clean_summary_text', 'extract_cluster_tags_locally', 'extract_entities', 'filter_cluster_tags', 'generate_cover_art', 'generate_local_placeholder', 'get_celery_queue_depth', 'get_dominant_color', 'invalidate_cluster_caches', 'invalidate_public_data_caches', 'log', 'normalize_citation_sources', 'normalize_headline', 'normalize_perspectives', 'normalize_summary_text', 'parse_embedding_value', 'record_runtime_event', 'redis_client', 'release_task_lock', 'schedule_task_once', 'summarize_article_fallback', 'synthesize_cluster_fallback', 'validate_person_names'})

def __getattr__(name: str):
    if name in _DELEGATED:
        from tasks.intelligence import _constants
        return getattr(_constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

