from tasks.intelligence import synthesis_scheduling as _synthesis_scheduling
from tasks.intelligence._constants import *  # noqa: F403
from tasks.intelligence._queue import intelligence_soft_deferred
from tasks.intelligence.synthesis_pipeline import run_cluster_synthesis
from tasks.utils import (
    log,
    schedule_task_once,
)


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


@celery_app.task(name="tasks.intelligence.upgrade_fast_synthesis_task", queue="synthesis")
def upgrade_fast_synthesis_task(cluster_id, content=None, defer_attempt=0):
    """Run full-quality synthesis after fast-mode publish, deferring when intel-heavy is congested."""
    from core.runtime_limits import FAST_SYNTHESIS_UPGRADE_FORCE_AFTER_DEFERS, FAST_SYNTHESIS_UPGRADE_QUEUE

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
def synthesize_urgent_task(cluster_id, content=None, force_llm=False):
    """Priority synthesis for new clusters."""
    return synthesize_cluster_task(cluster_id, content, fast_mode=True, force_llm=force_llm)


@celery_app.task(name="tasks.intelligence.synthesize_cluster_task", rate_limit="60/m", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def synthesize_cluster_task(cluster_id, content, retry_attempt=0, fast_mode=False, force_llm=False):
    """Generates a multi-perspective synthesis for a cluster with historical continuity."""

    return run_cluster_synthesis(cluster_id, content, fast_mode=fast_mode, force_llm=force_llm)


_DELEGATED = frozenset({'CLUSTER_LOOKBACK', '_call_ai', '_sanitize_synthesis_outputs', 'acquire_task_lock', 'analyst', 'average_embeddings', 'celery_app', 'clean_extracted_article_text', 'clean_json_response', 'db', 'deShout', 'detect_category', 'detect_topic', 'extract_clean_summary_text', 'extract_cluster_tags_locally', 'extract_entities', 'filter_cluster_tags', 'generate_cover_art', 'generate_local_placeholder', 'get_celery_queue_depth', 'get_dominant_color', 'invalidate_cluster_caches', 'invalidate_public_data_caches', 'log', 'normalize_citation_sources', 'normalize_headline', 'normalize_perspectives', 'normalize_summary_text', 'parse_embedding_value', 'record_runtime_event', 'redis_client', 'release_task_lock', 'schedule_task_once', 'summarize_article_fallback', 'synthesize_cluster_fallback', 'validate_person_names'})

def __getattr__(name: str):
    if name in _DELEGATED:
        from tasks.intelligence import _constants
        return getattr(_constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
