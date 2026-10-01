"""Cluster repair/recluster tasks.

Replaces the old no-op stubs. These previously did nothing, so clusters that
were split at ingestion time (the same event landing in several clusters because
title-overlap-only matching failed) were never repaired. That starved pluralism
and synthesis: most single-event clusters stayed one-source forever.

`repair_split_clusters_task` re-evaluates recent articles against each other
using the shared clustering heuristics and repoints articles from duplicate
clusters onto a single canonical cluster.
"""

import logging

from core.celery_app import celery_app

log = logging.getLogger("presek")


def _clusters_match(rep_title, rep_entities, rep, other, max_age_hours):
    """Return True when a representative article pair is the same story.

    Used for the repair pass, which is stricter than ingestion: every star member
    is merged straight into the hub, so a single permissive edge still glues an
    unrelated story onto a cluster. We therefore only merge on (a) near-identical
    titles or (b) a strong combined score anchored by a shared *named* entity.
    Topic/category agreement alone is never enough.
    """
    from core.clustering import (
        _age_hours,
        _cluster_title_overlap,
        _extract_title_entities,
        _entity_token_overlap,
        _TITLE_INSTANT_MERGE,
        _TITLE_BEST_MERGE,
        _TITLE_ANCHORED_MERGE,
    )

    other_title = str(other.get("title") or "")
    if _age_hours(other.get("created_at")) > max_age_hours:
        return False
    overlap = _cluster_title_overlap(rep_title, other_title)
    if overlap >= _TITLE_INSTANT_MERGE:
        return True
    shared = _entity_token_overlap(rep_entities, _extract_title_entities(other_title))
    named_shared = {s for s in shared if not s.isdigit()}
    if not named_shared:
        return False
    # A single shared entity must be backed by meaningful headline overlap;
    # otherwise a person/place mentioned in two unrelated stories would chain
    # them together. Two or more shared entities is a stronger same-story signal.
    if len(named_shared) < 2 and overlap < _TITLE_ANCHORED_MERGE:
        return False
    # Category disagreement is common even for the same story (one outlet files
    # it under Makedonija, another under Srbija), so do not block on it alone
    # when a named entity is shared and the headlines overlap meaningfully.
    if (
        rep.get("category")
        and other.get("category")
        and other["category"] != rep["category"]
        and len(named_shared) < 2
        and overlap < 0.40
    ):
        return False
    same_topic = bool(rep.get("topic") and other.get("topic") and rep["topic"] == other["topic"])
    score = overlap + 0.15
    if len(shared) >= 2:
        score += 0.05
    if same_topic:
        score += 0.06
    return score >= _TITLE_BEST_MERGE


def plan_cluster_merges(articles, *, max_age_hours=48, min_sources_for_merge=1):
    """Group article rows that describe the same story into merge sets.

    `articles` is an iterable of mappings with at least: id, cluster_id,
    title, source, topic, category, created_at. Returns a list of
    (canonical_cluster_id, [duplicate_cluster_id, ...], merged_article_count).

    Uses **bounded star merge** instead of union-find: a merge group is formed
    around a single hub cluster, and every member must pass the pairwise match
    gate *against the hub directly* (depth 1, no transitive chaining). Union-find
    collapsed A~B~C~D chains where no story actually connected the ends — that
    chaining was the dominant source of mixed-story bags.
    """
    from core.clustering import _cluster_title_overlap, _extract_title_entities

    rows = [dict(r) for r in articles or []]
    rows = [r for r in rows if r.get("cluster_id") and str(r.get("title") or "").strip()]

    clusters = {}
    for r in rows:
        clusters.setdefault(r["cluster_id"], []).append(r)

    def source_count(rs):
        return len({str(x.get("source") or "") for x in rs})

    # Pick a deterministic representative article per cluster: the longest title
    # carries the most signal for overlap scoring.
    reps = {}
    for cid, rs in clusters.items():
        rep = max(rs, key=lambda r: len(str(r.get("title") or "")))
        reps[cid] = {
            "title": str(rep.get("title") or ""),
            "entities": _extract_title_entities(str(rep.get("title") or "")),
            "topic": rep.get("topic"),
            "category": rep.get("category"),
            "created_at": rep.get("created_at"),
        }

    ids = list(clusters.keys())

    # Collect every pair that passes the match gate, scored by headline overlap.
    neighbors = {cid: [] for cid in ids}  # cid -> [(overlap, other_cid)]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            rep_a, rep_b = reps[a], reps[b]
            if not _clusters_match(rep_a["title"], rep_a["entities"], rep_a, rep_b, max_age_hours):
                continue
            overlap = _cluster_title_overlap(rep_a["title"], rep_b["title"])
            neighbors[a].append((overlap, b))
            neighbors[b].append((overlap, a))

    # Hub order: highest degree first (most direct matches), then the usual
    # canonical preference (most articles, most sources, stable id).
    hub_order = sorted(
        ids,
        key=lambda c: (
            -len(neighbors[c]),
            -len(clusters[c]),
            -source_count(clusters[c]),
            c,
        ),
    )

    matched = set()
    merges = []
    for hub in hub_order:
        if hub in matched:
            continue
        members = sorted(
            {other for _ov, other in neighbors[hub] if other not in matched}
        )
        if not members:
            continue
        star = [hub] + members
        matched.update(star)
        canonical = min(star, key=lambda c: (-len(clusters[c]), -source_count(clusters[c]), c))
        dups = [c for c in star if c != canonical]
        dup_count = sum(len(clusters[c]) for c in dups)
        merges.append((canonical, dups, dup_count))

    merges.sort(key=lambda m: -m[2])
    return merges


def _candidate_articles(db, hours):
    return db.execute(
        """
        SELECT id, cluster_id, title, source, topic, category, created_at
        FROM articles
        WHERE cluster_id IS NOT NULL
          AND created_at >= NOW() - make_interval(hours => %s)
        ORDER BY created_at DESC
        """,
        (int(hours),),
    )


@celery_app.task(name="tasks.intelligence.repair_split_clusters_task")
def repair_split_clusters_task(hours=48, limit=800, dry_run=False):
    """Merge clusters that are duplicates of the same story."""
    from core.database import db_manager as db

    try:
        rows = _candidate_articles(db, hours)
    except Exception as exc:  # pragma: no cover - DB failure path
        log.warning("[cluster_ops] repair query failed: %s", exc)
        return {"status": "error", "error": str(exc)}

    if not rows:
        return {"status": "ok", "merges": 0, "repointed": 0}

    plan = plan_cluster_merges(rows)
    # A merge set must actually combine clusters and involve real duplicates.
    plan = [m for m in plan if m[1]]
    total_dups = sum(len(m[1]) for m in plan)
    total_articles = sum(m[2] for m in plan)

    if dry_run:
        log.info("[cluster_ops] dry_run: would merge %s clusters", total_dups)
        return {
            "status": "dry_run",
            "chains": len(plan),
            "clusters_merged": total_dups,
            "articles_repointed": total_articles,
            "plan": [{"canonical": m[0], "duplicates": m[1]} for m in plan[:50]],
        }

    repointed = 0
    for canonical, duplicates, _count in plan[: int(limit)]:
        for dup in duplicates:
            if dup == canonical:
                continue
            try:
                moved = db.execute(
                    "UPDATE articles SET cluster_id = %s WHERE cluster_id = %s",
                    (canonical, dup),
                    fetch=False,
                )
                repointed += int(moved or 0)
            except Exception as exc:  # pragma: no cover
                log.warning("[cluster_ops] failed to merge %s -> %s: %s", dup, canonical, exc)

    if repointed:
        # Drop now-orphaned cluster-scoped rows (summaries, metadata, entities,
        # reactions) whose cluster no longer has any articles.
        try:
            for table in ("cluster_summaries", "cluster_metadata", "cluster_entities"):
                db.execute(
                    f"DELETE FROM {table} WHERE NOT EXISTS "
                    "(SELECT 1 FROM articles a WHERE a.cluster_id = " + table + ".cluster_id)",
                    fetch=False,
                )
        except Exception as exc:  # pragma: no cover
            log.warning("[cluster_ops] orphan cleanup skipped: %s", exc)

    log.info(
        "[cluster_ops] repair merged %s clusters, repointed %s articles",
        total_dups,
        repointed,
    )
    return {
        "status": "ok",
        "chains": len(plan),
        "clusters_merged": total_dups,
        "articles_repointed": repointed,
    }


@celery_app.task(name="tasks.intelligence.recluster_recent_articles_task")
def recluster_recent_articles_task(hours=48, limit=600):
    """Alias for the repair pass (kept for the beat schedule/name contract)."""
    return repair_split_clusters_task(hours=hours, limit=limit, dry_run=False)
