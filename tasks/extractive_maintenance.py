"""Deterministic (LLM-free) maintenance tasks for the MK-only deployment.

These replace the no-op `tasks.intelligence.*` stubs for jobs that do not
actually need a language model: entity extraction, storylines, cover art,
clustering/repair and sentiment. They rely only on regex/lexicon helpers that
remain available with PRESEK_AI_ENABLED=0.
"""

from __future__ import annotations

import time
from collections import defaultdict

from core.celery_app import celery_app
from core.database import db_manager as db
from core.entities import NameStats, build_aliases, extract_cluster_entities
from tasks.utils import log

# --- entity extraction (regex + corpus statistics, no model) -----------------
# The extraction logic lives in core.entities; this module owns the database I/O.

_STATS_WINDOW_DAYS = 7
_STATS_MAX_TITLES = 20000
_STATS_TTL_SECONDS = 3600
_MAX_ARTICLES_PER_CLUSTER = 40
_stats_cache: dict = {"at": 0.0, "stats": None}


def _corpus_name_stats() -> NameStats:
    """Capitalisation statistics over the last week of headlines, cached per process."""
    now = time.monotonic()
    cached = _stats_cache["stats"]
    if cached is not None and now - _stats_cache["at"] < _STATS_TTL_SECONDS:
        return cached
    rows = db.execute(
        """
        SELECT title FROM articles
        WHERE COALESCE(ingested_at, created_at) >= NOW() - make_interval(days => %s)
        ORDER BY COALESCE(ingested_at, created_at) DESC
        LIMIT %s
        """,
        (_STATS_WINDOW_DAYS, _STATS_MAX_TITLES),
    )
    stats = NameStats().add_texts(r.get("title") or "" for r in rows or [])
    _stats_cache.update(at=now, stats=stats)
    return stats


def _cluster_articles(cluster_ids: list[str]) -> dict[str, list[dict]]:
    """Articles of whole clusters (newest first), so a cluster's entities never depend on
    which of its articles happened to be ingested recently."""
    rows = db.execute(
        """
        SELECT cluster_id, title, description FROM (
            SELECT cluster_id, title, description,
                   ROW_NUMBER() OVER (
                       PARTITION BY cluster_id ORDER BY COALESCE(ingested_at, created_at) DESC
                   ) AS rn
            FROM articles WHERE cluster_id = ANY(%s)
        ) t WHERE rn <= %s
        """,
        (cluster_ids, _MAX_ARTICLES_PER_CLUSTER),
    )
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows or []:
        grouped[row["cluster_id"]].append(row)
    return grouped


# --- tasks -------------------------------------------------------------------


@celery_app.task(name="tasks.extractive.extract_entities_task")
def extract_entities_task(hours: int = 48, limit: int = 200):
    """Rebuild cluster_entities (and refresh knowledge_entities) for recently active clusters."""
    try:
        recent = db.execute(
            """
            SELECT cluster_id FROM articles
            WHERE cluster_id IS NOT NULL
              AND COALESCE(ingested_at, created_at) >= NOW() - make_interval(hours => %s)
            GROUP BY cluster_id
            ORDER BY MAX(COALESCE(ingested_at, created_at)) DESC
            LIMIT %s
            """,
            (hours, limit),
        )
        cluster_ids = [r["cluster_id"] for r in recent or []]
        if not cluster_ids:
            return {"status": "success", "links": 0}

        stats = _corpus_name_stats()
        articles_by_cluster = _cluster_articles(cluster_ids)
        raw = {cid: extract_cluster_entities(arts, stats) for cid, arts in articles_by_cluster.items()}
        # Surname -> full name folding needs the whole batch: «Трамп» and «Доналд Трамп» are
        # usually in different clusters.
        aliases = build_aliases(e["name"] for ents in raw.values() for e in ents)
        final = {cid: extract_cluster_entities(arts, stats, aliases) for cid, arts in articles_by_cluster.items()}

        rows = sorted((cid, e["name"], e["type"], e["mentions"]) for cid, ents in final.items() for e in ents)
        if rows:
            db.executemany(
                "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type, mentions) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (cluster_id, entity_name) DO UPDATE SET "
                "entity_type = EXCLUDED.entity_type, mentions = EXCLUDED.mentions",
                rows,
            )
        # Drop what this cluster no longer yields (old junk included).
        db.execute(
            """
            DELETE FROM cluster_entities ce
            WHERE ce.cluster_id = ANY(%s)
              AND NOT EXISTS (
                SELECT 1 FROM unnest(%s::text[], %s::text[]) AS k(cid, nm)
                WHERE k.cid = ce.cluster_id AND k.nm = ce.entity_name
              )
            """,
            (list(final), [r[0] for r in rows], [r[1] for r in rows]),
            fetch=False,
        )
        names = sorted({(r[1], r[2]) for r in rows})
        if names:
            # total_mentions is recomputed from cluster_entities rather than incremented, so
            # re-running the task over the same clusters no longer inflates it.
            db.executemany(
                """
                INSERT INTO knowledge_entities (name, type, total_mentions, first_seen, last_seen)
                VALUES (%s, %s,
                        (SELECT COALESCE(SUM(mentions), 0) FROM cluster_entities WHERE entity_name = %s),
                        NOW(), NOW())
                ON CONFLICT (name) DO UPDATE SET
                    type = EXCLUDED.type,
                    total_mentions = EXCLUDED.total_mentions,
                    last_seen = NOW()
                """,
                [(n, t, n) for n, t in names],
            )
        log.info("[extractive] extract_entities: %s links across %s clusters", len(rows), len(final))
        return {"status": "success", "links": len(rows), "clusters": len(final)}
    except Exception as e:
        log.error("[extractive] extract_entities failed: %s", e)
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="tasks.extractive.refine_knowledge_graph_sentiment_task")
def refine_knowledge_graph_sentiment_task(limit: int = 400):
    """Score entity sentiment with a deterministic lexicon (no model)."""
    from nlp.sentiment import analyze_sentiment_locally

    try:
        rows = db.execute(
            """
            SELECT ke.name, string_agg(a.title || ' ' || COALESCE(a.description, ''), ' ') AS blob
            FROM knowledge_entities ke
            JOIN cluster_entities ce ON ce.entity_name = ke.name
            JOIN articles a ON a.cluster_id = ce.cluster_id
            WHERE COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '14 days'
            GROUP BY ke.name
            LIMIT %s
            """,
            (limit,),
        )
        # One batched UPDATE instead of a round trip per entity (slow from CI).
        scores = sorted((row.get("name"), analyze_sentiment_locally(row.get("blob") or "")) for row in rows or [])
        if scores:
            db.executemany(
                "UPDATE knowledge_entities SET sentiment_score = %s WHERE name = %s",
                [(score, name) for name, score in scores],
            )
        updated = len(scores)
        log.info("[extractive] refined sentiment for %s entities", updated)
        return {"status": "success", "updated": updated}
    except Exception as e:
        log.error("[extractive] sentiment refine failed: %s", e)
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="tasks.extractive.discover_storylines_task")
def discover_storylines_task(min_shared: int = 2, limit: int = 500):
    """Relate co-occurring entities in knowledge_relationships (entity graph).

    knowledge_relationships links entity -> entity by name, so we weight edges
    by how often two entities appear in the same cluster.
    """
    try:
        rows = db.execute(
            """
            SELECT ce1.entity_name AS a, ce2.entity_name AS b, COUNT(*) AS shared
            FROM cluster_entities ce1
            JOIN cluster_entities ce2
              ON ce1.cluster_id = ce2.cluster_id
             AND ce1.entity_name < ce2.entity_name
            GROUP BY ce1.entity_name, ce2.entity_name
            HAVING COUNT(*) >= %s
            ORDER BY shared DESC
            LIMIT %s
            """,
            (min_shared, limit),
        )
        links = 0
        for r in rows or []:
            a, b = r.get("a"), r.get("b")
            if not a or not b:
                continue
            # Ensure both endpoints exist (FK target) before linking.
            for name in (a, b):
                db.execute(
                    """
                    INSERT INTO knowledge_entities (name, type, total_mentions)
                    VALUES (%s, 'MISC', 1)
                    ON CONFLICT (name) DO NOTHING
                    """,
                    (name,),
                    fetch=False,
                )
            db.execute(
                """
                INSERT INTO knowledge_relationships (entity_a, entity_b, weight, last_seen)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (entity_a, entity_b) DO UPDATE SET
                    weight = EXCLUDED.weight, last_seen = NOW()
                """,
                (a, b, r.get("shared")),
                fetch=False,
            )
            links += 1
        log.info("[extractive] discover_storylines: %s entity links", links)
        return {"status": "success", "links": links}
    except Exception as e:
        log.error("[extractive] discover_storylines failed: %s", e)
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="tasks.extractive.backfill_cover_art_task")
def backfill_cover_art_task(limit: int = 200):
    """Assign a representative image to clusters missing one."""
    try:
        rows = db.execute(
            """
            SELECT a.cluster_id
            FROM articles a
            LEFT JOIN cluster_metadata cm ON cm.cluster_id = a.cluster_id
            WHERE a.cluster_id IS NOT NULL
              AND a.image_url IS NOT NULL AND a.image_url <> ''
              AND (cm.representative_image IS NULL OR cm.representative_image = '')
              AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '7 days'
            GROUP BY a.cluster_id
            ORDER BY MAX(COALESCE(a.ingested_at, a.created_at)) DESC
            LIMIT %s
            """,
            (limit,),
        )
        filled = 0
        for r in rows or []:
            cid = r.get("cluster_id")
            img = db.execute_one(
                """
                SELECT image_url FROM articles
                WHERE cluster_id = %s AND image_url IS NOT NULL AND image_url <> ''
                ORDER BY ingested_at DESC NULLS LAST
                LIMIT 1
                """,
                (cid,),
            )
            if not img or not img.get("image_url"):
                continue
            db.execute(
                """
                INSERT INTO cluster_metadata (cluster_id, representative_image, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (cluster_id) DO UPDATE SET
                    representative_image = EXCLUDED.representative_image,
                    updated_at = NOW()
                """,
                (cid, img["image_url"]),
                fetch=False,
            )
            filled += 1
        log.info("[extractive] backfill_cover_art: %s clusters", filled)
        return {"status": "success", "filled": filled}
    except Exception as e:
        log.error("[extractive] backfill_cover_art failed: %s", e)
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="tasks.extractive.repair_split_clusters_task")
def repair_split_clusters_task(hours: int = 48, limit: int = 300):
    """Merge clusters whose representative headlines are near-duplicates."""
    from core.clustering import _cluster_title_overlap

    try:
        clusters = db.execute(
            """
            SELECT a.cluster_id, MAX(a.title) AS title, COUNT(*) AS n
            FROM articles a
            WHERE a.cluster_id IS NOT NULL
              AND COALESCE(a.ingested_at, a.created_at) >= NOW() - make_interval(hours => %s)
            GROUP BY a.cluster_id
            ORDER BY MAX(COALESCE(a.ingested_at, a.created_at)) DESC
            LIMIT %s
            """,
            (hours, limit),
        )
        clusters = list(clusters or [])
        merged = 0
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                a, b = clusters[i], clusters[j]
                if a.get("cluster_id") == b.get("cluster_id"):
                    continue
                if _cluster_title_overlap(a.get("title"), b.get("title")) >= 0.9:
                    db.execute(
                        "UPDATE articles SET cluster_id = %s WHERE cluster_id = %s",
                        (a["cluster_id"], b["cluster_id"]),
                        fetch=False,
                    )
                    db.execute(
                        "DELETE FROM cluster_entities WHERE cluster_id = %s",
                        (b["cluster_id"],),
                        fetch=False,
                    )
                    b["cluster_id"] = a["cluster_id"]  # avoid re-merging
                    merged += 1
        log.info("[extractive] repair_split_clusters: %s merges", merged)
        return {"status": "success", "merged": merged}
    except Exception as e:
        log.error("[extractive] repair_split_clusters failed: %s", e)
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="tasks.extractive.recluster_recent_articles_task")
def recluster_recent_articles_task(hours: int = 6, limit: int = 500):
    """Re-run entity extraction + split repair (extractive reclustering)."""
    extract_entities_task(hours=hours, limit=limit)
    return repair_split_clusters_task(hours=max(hours, 48), limit=limit)


@celery_app.task(name="tasks.extractive.schedule_backfill_cluster_summaries_task")
def schedule_backfill_cluster_summaries_task(lang: str = "mk"):
    """Enqueue the extractive cluster-overview builder."""
    from tasks.summarization import build_extractive_clusters_task

    build_extractive_clusters_task.delay(hours=168, limit=100)
    return {"status": "success"}


@celery_app.task(name="tasks.extractive.schedule_backfill_historical_summaries_task")
def schedule_backfill_historical_summaries_task(days: int = 30, limit: int = 200):
    """Build extractive overviews for older clusters too."""
    from tasks.summarization import build_extractive_clusters_task

    build_extractive_clusters_task.delay(hours=days * 24, limit=limit)
    return {"status": "success"}
