import datetime

from core.entities import extract_entities
from nlp import (
    extract_cluster_tags_locally,
    filter_cluster_tags,
    generate_local_placeholder,
)
from nlp.categories import detect_category, detect_topic
from tasks.intelligence._constants import *  # noqa: F403
from tasks.intelligence._queue import _queue_backlog_high, _skip_when_intel_backlog
from tasks.intelligence.synthesis_scheduling import _compute_centroid_from_values
from tasks.utils import (
    invalidate_public_data_caches,
    log,
    schedule_task_once,
)
from utils import get_dominant_color


@celery_app.task(name="tasks.intelligence.auto_summarize_task")
def auto_summarize_task(*args, cluster_ids: list[str] = None, **kwargs):
    """Dispatch summarization/synthesis tasks for top clusters or targeted clusters."""
    from core.ai_engine import auto_summarize_top_clusters
    from tasks.utils import pipeline_backpressure_active, synthesis_dispatch_deferred

    if not cluster_ids and (pipeline_backpressure_active() or synthesis_dispatch_deferred()):
        log.info("[tasks] Skipping auto_summarize while pipeline backlog is high.")
        return {"skipped": True, "reason": "pipeline_backlog"}

    auto_summarize_top_clusters(target_cluster_ids=cluster_ids)


@celery_app.task(name="tasks.intelligence.refresh_cluster_centroid_task")
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


@celery_app.task(name="tasks.intelligence.extract_entities_task")
def extract_entities_task(*args, hours=24, target_clusters=None, **kwargs):
    """Extract entities for top clusters using local hybrid logic (Lexicon + spaCy + Regex)."""
    if _skip_when_intel_backlog("entity extraction"):
        return
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


@celery_app.task(name="tasks.intelligence.classify_topics_task")
def classify_topics_task(*args, **kwargs):
    """Classify default 'vesti' clusters using local rule-based detection."""
    if _skip_when_intel_backlog("topic classification"):
        return
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


@celery_app.task(name="tasks.intelligence.recategorize_clusters_task")
def recategorize_clusters_task(*args, **kwargs):
    """Verify if 'Srbija' articles belong in specialized categories using rule-based detection."""
    if _skip_when_intel_backlog("cluster recategorization"):
        return
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


@celery_app.task(name="tasks.intelligence.generate_cluster_metadata_task")
def generate_cluster_metadata_task(*args, hours=24, target_clusters=None, **kwargs):
    """Tag recent clusters with metadata (entities, source count, centroid, and representative image)."""
    try:
        if _queue_backlog_high():
            log.info("[tasks] Skipping cluster metadata generation while queue backlog is high.")
            return

        if target_clusters:
            batch_ids = list(target_clusters)[:_METADATA_BATCH_SIZE]
            pending_ids = list(target_clusters)[_METADATA_BATCH_SIZE:]
            rows = db.execute(
                """
                SELECT cluster_id, array_agg(DISTINCT source) as sources, array_agg(DISTINCT title) as titles,
                       array_agg(DISTINCT topic) as topics,
                       mode() WITHIN GROUP (ORDER BY category) as dominant_category,
                       array_agg(embedding) FILTER (WHERE embedding IS NOT NULL) as embeddings
                FROM articles WHERE cluster_id = ANY(%s)
                GROUP BY cluster_id
            """,
                (batch_ids,),
            )
            has_more = bool(pending_ids)
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
                ORDER BY MAX(created_at) DESC
                LIMIT %s
            """,
                (cutoff, _METADATA_BATCH_SIZE + 1),
            )
            has_more = len(rows) > _METADATA_BATCH_SIZE
            rows = rows[:_METADATA_BATCH_SIZE]
            pending_ids = None
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

            from nlp.image_quality import select_representative_image

            rep_image = select_representative_image(db, r["cluster_id"])

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
        if has_more:
            if pending_ids is not None:
                schedule_task_once(
                    "lock:cluster_metadata_batch",
                    120,
                    generate_cluster_metadata_task,
                    kwargs={"hours": hours, "target_clusters": pending_ids},
                    countdown=30,
                )
            else:
                schedule_task_once(
                    "lock:cluster_metadata_sweep",
                    120,
                    generate_cluster_metadata_task,
                    kwargs={"hours": hours},
                    countdown=30,
                )
    except Exception as e:
        from tasks import utils

        utils.record_task_event("cluster_metadata", "error", "clusters:recent")
        log.error(f"[tasks] Cluster metadata generation failed: {e}")

_DELEGATED = frozenset({'CLUSTER_LOOKBACK', '_call_ai', '_sanitize_synthesis_outputs', 'acquire_task_lock', 'analyst', 'average_embeddings', 'celery_app', 'clean_extracted_article_text', 'clean_json_response', 'db', 'deShout', 'detect_category', 'detect_topic', 'extract_clean_summary_text', 'extract_cluster_tags_locally', 'extract_entities', 'filter_cluster_tags', 'generate_cover_art', 'generate_local_placeholder', 'get_celery_queue_depth', 'get_dominant_color', 'invalidate_cluster_caches', 'invalidate_public_data_caches', 'log', 'normalize_citation_sources', 'normalize_headline', 'normalize_perspectives', 'normalize_summary_text', 'parse_embedding_value', 'record_runtime_event', 'redis_client', 'release_task_lock', 'schedule_task_once', 'summarize_article_fallback', 'synthesize_cluster_fallback', 'validate_person_names'})

def __getattr__(name: str):
    if name in _DELEGATED:
        from tasks.intelligence import _constants
        return getattr(_constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

