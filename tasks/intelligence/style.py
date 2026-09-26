"""Detects whether a Macedonian article mirrors a foreign/global report.

The former local style-normalization task lived here too; it depended on the
removed local analyst and was disabled (ENABLE_EXPENSIVE_STYLE_TASKS=false), so
it was dropped. Ingestion-time headline cleanup is still done by the rule-based
``nlp.categories.normalize_headline``.
"""

import json

from tasks.intelligence._constants import *  # noqa: F403,F405
from tasks.utils import (
    log,
)


@celery_app.task(  # noqa: F405
    name="tasks.intelligence.detect_global_story_task",
    rate_limit="15/m",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def detect_global_story_task(article_id):
    """Detects if a Macedonian article is a translation of a foreign global report."""
    from core.config import LOCAL_TRANSLATION_ENABLED

    if not LOCAL_TRANSLATION_ENABLED:
        return

    row = db.execute_one("SELECT title FROM articles WHERE id = %s", (article_id,))  # noqa: F405
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
            db.execute(  # noqa: F405
                "UPDATE articles SET is_global = TRUE WHERE id = %s",
                (article_id,),
                fetch=False,
            )
            log.info(f"[originality] Flagged article {article_id} as GLOBAL (Sim: {best_similarity:.4f})")

    except Exception as e:
        log.warning(f"[originality] Detection failed for {article_id}: {e}")


_DELEGATED = frozenset(
    {
        "CLUSTER_LOOKBACK",
        "_call_ai",
        "_sanitize_synthesis_outputs",
        "acquire_task_lock",
        "analyst",
        "average_embeddings",
        "celery_app",
        "clean_extracted_article_text",
        "clean_json_response",
        "db",
        "deShout",
        "detect_category",
        "detect_topic",
        "extract_clean_summary_text",
        "extract_cluster_tags_locally",
        "extract_entities",
        "filter_cluster_tags",
        "generate_cover_art",
        "generate_local_placeholder",
        "get_celery_queue_depth",
        "get_dominant_color",
        "invalidate_cluster_caches",
        "invalidate_public_data_caches",
        "log",
        "normalize_citation_sources",
        "normalize_headline",
        "normalize_perspectives",
        "normalize_summary_text",
        "parse_embedding_value",
        "record_runtime_event",
        "redis_client",
        "release_task_lock",
        "schedule_task_once",
        "summarize_article_fallback",
        "synthesize_cluster_fallback",
        "validate_person_names",
    }
)


def __getattr__(name: str):
    if name in _DELEGATED:
        from tasks.intelligence import _constants

        return getattr(_constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
