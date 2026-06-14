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

import os
import sys

from tasks.utils import get_celery_queue_depth, log

def _queue_backlog_high(limit=_BACKFILL_QUEUE_DEPTH_LIMIT) -> bool:
    return get_celery_queue_depth("intel-heavy") >= limit


def intelligence_soft_deferred() -> bool:
    """True when secondary ingestion batches should yield to summarization."""
    return get_celery_queue_depth("intel-heavy") >= _INTEL_QUEUE_SOFT_DEFER_LIMIT


def intelligence_secondary_deferred() -> bool:
    """True when non-critical intel work (detect/standardize/beat) should wait."""
    return get_celery_queue_depth("intel-heavy") >= _INTEL_QUEUE_SECONDARY_DEFER_LIMIT


def intelligence_batches_deferred() -> bool:
    """True when even summarize batches should wait for queue space."""
    return get_celery_queue_depth("intel-heavy") >= _INTEL_QUEUE_FULL_DEFER_LIMIT


def _historical_summary_dispatch_limit(explicit_limit=None) -> int:
    """Scale historical backfill batch size to available queue headroom."""
    if explicit_limit is not None:
        return max(1, int(explicit_limit))
    base = _HISTORICAL_SUMMARY_DISPATCH_LIMIT
    depth = get_celery_queue_depth("intel-heavy")
    target_depth = _INTEL_QUEUE_SECONDARY_DEFER_LIMIT - _HISTORICAL_SUMMARY_QUEUE_BUFFER
    can_add_tasks = max(0, target_depth - depth)
    scaled = can_add_tasks * _ARTICLE_BATCH_SIZE
    return max(base, min(_HISTORICAL_SUMMARY_DISPATCH_MAX, scaled))


def _skip_when_intel_backlog(task_label: str) -> bool:
    if intelligence_soft_deferred():
        log.info("[tasks] Skipping %s while intel-heavy backlog is high.", task_label)
        return True
    return False


def _dispatch_batched(task, ids, batch_size=_ARTICLE_BATCH_SIZE):
    if not ids:
        return
    for start in range(0, len(ids), batch_size):
        task.delay(ids[start : start + batch_size])

# Ensure project root is in path for Celery workers
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

