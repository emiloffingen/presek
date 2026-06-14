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

from tasks.intelligence._constants import *  # noqa: F401,F403
from tasks.intelligence._queue import *  # noqa: F401,F403
from tasks.intelligence.summarization import *  # noqa: F401,F403
from tasks.intelligence.synthesis import *  # noqa: F401,F403
from tasks.intelligence.style import *  # noqa: F401,F403
from tasks.intelligence.metadata import *  # noqa: F401,F403
from tasks.intelligence.cluster_ops import *  # noqa: F401,F403
from tasks.intelligence.backfill import *  # noqa: F401,F403

# Re-export private helpers for tests, scripts, and patch targets.
from tasks.intelligence import synthesis as _synthesis_mod

for _name in dir(_synthesis_mod):
    if _name.startswith("_") and not _name.startswith("__"):
        globals()[_name] = getattr(_synthesis_mod, _name)

from tasks.intelligence import metadata as _metadata_mod

for _name in dir(_metadata_mod):
    if _name.startswith("_") and not _name.startswith("__"):
        globals()[_name] = getattr(_metadata_mod, _name)

from tasks.intelligence import backfill as _backfill_mod

for _name in dir(_backfill_mod):
    if _name.startswith("_") and not _name.startswith("__"):
        globals()[_name] = getattr(_backfill_mod, _name)

from tasks.intelligence import _queue as _queue_mod

for _name in dir(_queue_mod):
    if _name.startswith("_") and not _name.startswith("__"):
        globals()[_name] = getattr(_queue_mod, _name)

del _synthesis_mod, _metadata_mod, _backfill_mod, _queue_mod, _name
