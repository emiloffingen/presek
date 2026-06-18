from core.api_helpers import normalize_citation_sources, normalize_perspectives, normalize_summary_text
from core.entities import extract_entities, validate_person_names
from core.prompts import (
    SUMMARY_SYSTEM_PROMPT_MK,
    SUMMARY_SYSTEM_PROMPT_SR,
    SYNTHESIS_SYSTEM_PROMPT_MK,
    SYNTHESIS_SYSTEM_PROMPT_SR,
)
from core.text_extraction import clean_extracted_article_text
from nlp.categories import normalize_headline
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
from nlp.utils import extract_clean_summary_text
from tasks.synthesis_sanitize import sanitize_synthesis_outputs as _sanitize_synthesis_outputs
from tasks.intelligence.synthesis_grounding import (
    _fact_grounding_diagnostics,
    _is_fact_grounded_synthesis,
    _is_grounded_synthesis,
    _synthesis_source_corpus,
)
from tasks.intelligence.synthesis_translation import try_translate_synthesis_to_mk as _try_translate_synthesis_to_mk
from tasks.intelligence.synthesis_generation import (
    _attempt_gemma_rescue,
    _evaluate_synthesis_candidate,
    _generate_synthesis_via_cascade,
    _grounding_retry_suffix,
    _resolve_generation_model,
)
from tasks.intelligence.synthesis_mk_cleanup import _clean_macedonian_spelling_and_script
from tasks.intelligence.synthesis_prompt import (
    _build_cluster_synthesis_content,
    _build_cluster_synthesis_prompt,
    _build_source_comparison_prompt_block,
    _fetch_synthesis_history_context,
    _langs_for_cluster_articles,
    _load_cluster_articles_for_synthesis,
    _order_synthesis_langs,
)
from tasks.intelligence.synthesis_bundle import (
    _build_citation_sources,
    _build_synthesis_source_context,
    _ensure_dict,
    _extract_one_quote_or_fact,
    _fallback_key_facts,
    _normalize_cluster_synthesis,
)
from tasks.intelligence.synthesis_merge import (
    _cluster_tag_set,
    _cluster_text_similarity,
    _compute_centroid_from_values,
    _cosine_dist,
    _split_cluster_merge_score,
)
from tasks.intelligence import synthesis_scheduling as _synthesis_scheduling
from tasks.intelligence.synthesis_scheduling import (
    _COPY_PURITY_RETRY_DELAY_SECONDS,
    _schedule_deep_analyst_work,
    _schedule_fast_synthesis_upgrade,
)

from tasks.intelligence.synthesis_pipeline import run_cluster_synthesis
from tasks.intelligence.synthesis_persist import finalize_cluster_synthesis, persist_lang_synthesis
from tasks.intelligence.synthesis_scoring import (
    _compute_lightweight_quality_score,
    _paragraph_fingerprint,
    _score_editorial_summary,
    _score_synthesis_quality,
    _split_summary_items,
)

from tasks.utils import (
    acquire_task_lock,
    get_celery_queue_depth,
    invalidate_cluster_caches,
    invalidate_public_data_caches,
    log,
    record_runtime_event,
    redis_client,
    release_task_lock,
    schedule_task_once,
)
from utils import get_dominant_color

from tasks.intelligence._constants import *  # noqa: F403

import datetime
import json
import os
import re
import sys
import threading

from tasks.intelligence._queue import intelligence_soft_deferred


def _schedule_copy_purity_retry(cluster_id: str, content, *, lang: str, fast_mode: bool) -> bool:
    original_schedule_task_once = _synthesis_scheduling.schedule_task_once
    _synthesis_scheduling.schedule_task_once = schedule_task_once
    try:
        return _synthesis_scheduling._schedule_copy_purity_retry(
            cluster_id,
            content,
            lang=lang,
            fast_mode=fast_mode,
        )
    finally:
        _synthesis_scheduling.schedule_task_once = original_schedule_task_once


@celery_app.task(name="tasks.intelligence.upgrade_fast_synthesis_task", queue="maintenance")
def upgrade_fast_synthesis_task(cluster_id, content=None, defer_attempt=0):
    """Run full-quality synthesis after fast-mode publish, deferring when intel-heavy is congested."""
    from core.limits import FAST_SYNTHESIS_UPGRADE_FORCE_AFTER_DEFERS, FAST_SYNTHESIS_UPGRADE_QUEUE

    force_run = (
        FAST_SYNTHESIS_UPGRADE_FORCE_AFTER_DEFERS
        and defer_attempt >= _FAST_SYNTHESIS_UPGRADE_MAX_DEFERS
    )
    if intelligence_soft_deferred() and defer_attempt < _FAST_SYNTHESIS_UPGRADE_MAX_DEFERS and not force_run:
        retry_delay = min(900, 120 * (defer_attempt + 1))
        log.info(
            "[tasks/synthesis] Deferring full upgrade for %s (attempt %s, retry in %ss)",
            cluster_id,
            defer_attempt + 1,
            retry_delay,
        )
        upgrade_fast_synthesis_task.apply_async(
            args=(cluster_id,),
            kwargs={"content": content, "defer_attempt": defer_attempt + 1},
            countdown=retry_delay,
            queue=FAST_SYNTHESIS_UPGRADE_QUEUE,
        )
        return {"status": "deferred", "cluster_id": cluster_id, "defer_attempt": defer_attempt + 1}

    if force_run and intelligence_soft_deferred():
        log.warning(
            "[tasks/synthesis] Forcing full upgrade for %s after %s deferrals (queue still busy)",
            cluster_id,
            defer_attempt,
        )

    synthesize_cluster_task(cluster_id, content, fast_mode=False)
    return {"status": "upgraded", "cluster_id": cluster_id}


@celery_app.task(name="tasks.intelligence.synthesize_urgent_task", 
    queue="fast-track",
    rate_limit="60/m",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def synthesize_urgent_task(cluster_id, content=None):
    """Priority synthesis for new clusters."""
    return synthesize_cluster_task(cluster_id, content, fast_mode=True)


@celery_app.task(name="tasks.intelligence.synthesize_cluster_task", rate_limit="60/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def synthesize_cluster_task(cluster_id, content, retry_attempt=0, fast_mode=False):
    """Generates a multi-perspective synthesis for a cluster with historical continuity."""
    from tasks.intelligence.synthesis_pipeline import run_cluster_synthesis

    return run_cluster_synthesis(cluster_id, content, fast_mode=fast_mode)


_DELEGATED = frozenset({'CLUSTER_LOOKBACK', '_call_ai', '_sanitize_synthesis_outputs', 'acquire_task_lock', 'analyst', 'average_embeddings', 'celery_app', 'clean_extracted_article_text', 'clean_json_response', 'db', 'deShout', 'detect_category', 'detect_topic', 'extract_clean_summary_text', 'extract_cluster_tags_locally', 'extract_entities', 'filter_cluster_tags', 'generate_cover_art', 'generate_local_placeholder', 'get_celery_queue_depth', 'get_dominant_color', 'invalidate_cluster_caches', 'invalidate_public_data_caches', 'log', 'normalize_citation_sources', 'normalize_headline', 'normalize_perspectives', 'normalize_summary_text', 'parse_embedding_value', 'record_runtime_event', 'redis_client', 'release_task_lock', 'schedule_task_once', 'summarize_article_fallback', 'synthesize_cluster_fallback', 'validate_person_names'})

def __getattr__(name: str):
    if name in _DELEGATED:
        from tasks.intelligence import _constants
        return getattr(_constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
