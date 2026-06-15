from core.api_helpers import normalize_citation_sources, normalize_perspectives, normalize_summary_text
from core.ingestion import cosine_dist
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

import datetime
import json
import os
import re
import sys
import threading

from tasks.intelligence._queue import _skip_when_intel_backlog, _skip_when_intel_full
from tasks.intelligence.metadata import (
    auto_summarize_task,
    extract_entities_task,
    generate_cluster_metadata_task,
)
from tasks.intelligence.synthesis import _split_cluster_merge_score

@celery_app.task(name="tasks.intelligence.recluster_recent_articles_task")
def recluster_recent_articles_task(hours=24, limit=800):
    """Re-assign cluster IDs for recent articles using the current clustering logic."""
    if _skip_when_intel_full("recent recluster"):
        return
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
                    dist = cosine_dist(parsed_embedding, candidate["embedding"])
                    if dist >= (clustering.VECTOR_THRESHOLD * 0.92):
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
                        if not shared_entities and phrase_overlap < 0.28:
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


@celery_app.task(name="tasks.intelligence.repair_split_clusters_task")
def repair_split_clusters_task(hours=48, limit=1200, dry_run=False):
    """Merge recent near-duplicate clusters that ingestion split too conservatively."""
    if _skip_when_intel_full("split cluster repair"):
        return
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

_DELEGATED = frozenset({'CLUSTER_LOOKBACK', '_call_ai', '_sanitize_synthesis_outputs', 'acquire_task_lock', 'analyst', 'average_embeddings', 'celery_app', 'clean_extracted_article_text', 'clean_json_response', 'db', 'deShout', 'detect_category', 'detect_topic', 'extract_clean_summary_text', 'extract_cluster_tags_locally', 'extract_entities', 'filter_cluster_tags', 'generate_cover_art', 'generate_local_placeholder', 'get_celery_queue_depth', 'get_dominant_color', 'invalidate_cluster_caches', 'invalidate_public_data_caches', 'log', 'normalize_citation_sources', 'normalize_headline', 'normalize_perspectives', 'normalize_summary_text', 'parse_embedding_value', 'record_runtime_event', 'redis_client', 'release_task_lock', 'schedule_task_once', 'summarize_article_fallback', 'synthesize_cluster_fallback', 'validate_person_names'})

def __getattr__(name: str):
    if name in _DELEGATED:
        from tasks.intelligence import _constants
        return getattr(_constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

