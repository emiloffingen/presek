"""Breaking-alert candidate loading, classification, and profile selection."""

from __future__ import annotations

import datetime

from core.config import BREAKING_SCORE_THRESHOLD
from core.database import db_manager as db
from tasks.utils import log
from utils import assess_cluster_synthesis_freshness

from .core import (
    _load_breaking_target_performance,
    _load_delivery_kind_performance,
    _normalize_alert_context,
    _parse_row_datetime,
)
from .subscribers import _cluster_delivery_match, _normalize_synced_profile_for_delivery

def _load_recent_breaking_clusters(hours=4, limit=24):
    from .briefing import _load_daily_brief_clusters

    now = datetime.datetime.now(datetime.timezone.utc)
    ranked = []
    for cluster in _load_daily_brief_clusters(limit=limit):
        created_at = _parse_row_datetime(cluster.get("created_at"))
        if created_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        age_hours = (now - created_at.astimezone(datetime.timezone.utc)).total_seconds() / 3600.0
        if age_hours > hours:
            continue
        if float(cluster.get("score") or 0) < BREAKING_SCORE_THRESHOLD:
            continue
        ranked.append(cluster)
    ranked.sort(key=lambda item: item.get("score") or 0, reverse=True)
    return ranked


def _load_cluster_alert_material(cluster_id):
    articles = db.execute(
        "SELECT title, description, source, link, created_at, category, topic FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
        (cluster_id,),
    )
    summary_row = db.execute_one("SELECT created_at FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,))
    return articles, (summary_row or {}).get("created_at")


def _batch_load_cluster_alert_materials(cluster_ids):
    if not cluster_ids:
        return {}
    cluster_id_tuple = tuple(cluster_ids)
    articles_by_cluster = {}
    rows = db.execute(
        "SELECT title, description, source, link, created_at, category, topic, cluster_id FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
        (cluster_id_tuple,),
    )
    for row in rows or []:
        cid = str(row.get("cluster_id") or "")
        if cid not in articles_by_cluster:
            articles_by_cluster[cid] = []
        articles_by_cluster[cid].append(row)
    for cid in articles_by_cluster:
        articles_by_cluster[cid] = articles_by_cluster[cid][:8]
    summary_rows = db.execute(
        "SELECT cluster_id, created_at FROM cluster_summaries WHERE cluster_id = ANY(%s)", (cluster_id_tuple,)
    )
    summaries_by_cluster = {str(row.get("cluster_id") or ""): row.get("created_at") for row in summary_rows or []}
    return {
        str(cid): {
            "articles": articles_by_cluster.get(str(cid), []),
            "summary_date": summaries_by_cluster.get(str(cid)),
        }
        for cid in cluster_ids
    }


def _classify_alert_candidate(
    cluster, freshness, matched_topics, matched_sources, delivery_performance=None, target_performance=None
):
    reasons = freshness.get("reasons") or []
    freshness_score = float(freshness.get("freshness_score") or 0.0)
    base_score = float(cluster.get("score") or 0.0)
    delivery_performance = delivery_performance or {}
    target_performance = target_performance or {}
    breaking_perf = delivery_performance.get("breaking") or {}
    breaking_sends = int(breaking_perf.get("sends") or 0)
    breaking_open_rate = float(breaking_perf.get("open_rate") or 0.0)
    breaking_click_rate = float(breaking_perf.get("click_rate") or 0.0)
    alert_label = "Vazno azuriranje"
    alert_reason = cluster.get("match_reason") or "ova prica silno se vrzuva so vasite sledeni temi ili izvori"
    alert_tags = "newspaper"
    min_gap_minutes = 90
    topic_gap_minutes = 240
    source_gap_minutes = 180
    severity_rank = 1
    score_adjustment = 0.0
    engagement_label = "Normalen odziv"
    if "credible_new_reporting" in reasons or "new_sources" in reasons or base_score >= BREAKING_SCORE_THRESHOLD + 1.4:
        alert_label = "Itno azuriranje"
        alert_reason = "se pojavi nov doverliv izvor ili znacaen razvoj"
        alert_tags = "rotating_light,newspaper"
        min_gap_minutes = 30
        topic_gap_minutes = 120
        source_gap_minutes = 90
        severity_rank = 3
    elif "new_numbers" in reasons or "new_angle" in reasons or freshness_score >= 1.8:
        alert_label = "nova vazna promena"
        alert_reason = "ima nov ugao, brojki ili pojasna promena vo izvestaj"
        alert_tags = "newspaper,warning"
        min_gap_minutes = 60
        topic_gap_minutes = 180
        source_gap_minutes = 150
        severity_rank = 2
    elif "multiple_new_reports" in reasons:
        alert_label = "Sleden razvoj"
        alert_reason = "se natrupuvaat povece novi izvestai okolu istata prica"
        alert_tags = "newspaper"
        min_gap_minutes = 120
        topic_gap_minutes = 360
        source_gap_minutes = 240
    if breaking_sends >= 8 and breaking_click_rate < 0.12 and breaking_open_rate < 0.35:
        engagement_label = "Slab odziv"
        min_gap_minutes += 75
        topic_gap_minutes += 180
        source_gap_minutes += 120
        if severity_rank < 3:
            score_adjustment -= 0.45
            alert_reason = f"{alert_reason}; pracame samo posilni azuriranja dodeka odzivot e nizok"
    elif breaking_sends >= 6 and (breaking_click_rate >= 0.22 or breaking_open_rate >= 0.58):
        engagement_label = "Silen odziv"
        min_gap_minutes = max(20, min_gap_minutes - 15)
        topic_gap_minutes = max(90, topic_gap_minutes - 45)
        source_gap_minutes = max(75, source_gap_minutes - 30)
        if severity_rank >= 2:
            score_adjustment += 0.25
            alert_reason = f"{alert_reason}; vakvi azuriranja i prethodno dobivaa silen odziv"
    topic_perf = target_performance.get("topics") or {}
    source_perf = target_performance.get("sources") or {}
    topic_rates = [topic_perf.get(t) for t in matched_topics or [] if topic_perf.get(t)]
    source_rates = [source_perf.get(s) for s in matched_sources or [] if source_perf.get(s)]
    if any(
        int(i.get("sends") or 0) >= 2
        and (float(i.get("click_rate") or 0.0) >= 0.22 or float(i.get("open_rate") or 0.0) >= 0.65)
        for i in topic_rates + source_rates
    ):
        engagement_label = "Silen odziv za sledenoto"
        min_gap_minutes = max(20, min_gap_minutes - 15)
        topic_gap_minutes = max(75, topic_gap_minutes - 60)
        source_gap_minutes = max(60, source_gap_minutes - 45)
        score_adjustment += 0.3
        alert_reason = f"{alert_reason}; ova tema ili izvor prethodno dobivale silen odziv"
    elif (
        any(
            int(i.get("sends") or 0) >= 3
            and float(i.get("open_rate") or 0.0) < 0.2
            and float(i.get("click_rate") or 0.0) == 0.0
            for i in topic_rates + source_rates
        )
        and severity_rank < 3
    ):
        engagement_label = "Slab odziv za sledenoto"
        min_gap_minutes += 60
        topic_gap_minutes += 120
        source_gap_minutes += 120
        score_adjustment -= 0.35
        alert_reason = f"{alert_reason}; ova tema ili izvor prethodno imale slab odziv"
    throttle_keys = [f"cluster:{str(cluster.get('cluster_id') or '').strip()}"]
    throttle_keys.extend(f"topic:{t}" for t in matched_topics[:2])
    throttle_keys.extend(f"source:{s}" for s in matched_sources[:2])
    return {
        "alert_label": alert_label,
        "alert_reason": alert_reason,
        "alert_tags": alert_tags,
        "min_gap_minutes": min_gap_minutes,
        "topic_gap_minutes": topic_gap_minutes,
        "source_gap_minutes": source_gap_minutes,
        "throttle_keys": throttle_keys,
        "engagement_label": engagement_label,
        "score_adjustment": score_adjustment,
    }


def _alert_throttled(last_breaking_sent_at, alert_context, candidate):
    last_global = _parse_row_datetime(last_breaking_sent_at)
    now = datetime.datetime.now(datetime.timezone.utc)
    if last_global:
        if last_global.tzinfo is None:
            last_global = last_global.replace(tzinfo=datetime.timezone.utc)
        if (now - last_global.astimezone(datetime.timezone.utc)).total_seconds() / 60.0 < candidate["min_gap_minutes"]:
            return True
    context = _normalize_alert_context(alert_context)
    for key in candidate["throttle_keys"]:
        last_value = _parse_row_datetime(context.get(key))
        if not last_value:
            continue
        if last_value.tzinfo is None:
            last_value = last_value.replace(tzinfo=datetime.timezone.utc)
        age_minutes = (now - last_value.astimezone(datetime.timezone.utc)).total_seconds() / 60.0
        if key.startswith("cluster:") and age_minutes < max(180, candidate["min_gap_minutes"] * 2):
            return True
        if key.startswith("topic:") and age_minutes < candidate["topic_gap_minutes"]:
            return True
        if key.startswith("source:") and age_minutes < candidate["source_gap_minutes"]:
            return True
    return False


def _select_breaking_cluster_for_profile(
    profile,
    seen_cluster_ids,
    alert_context=None,
    last_breaking_sent_at=None,
    *,
    include_topics=True,
    include_sources=True,
    _cached_clusters=None,
    _cached_materials=None,
    _cached_delivery_perf=None,
    _cached_target_perf=None,
):
    profile = _normalize_synced_profile_for_delivery(profile)
    seen = {str(item or "").strip() for item in seen_cluster_ids or [] if str(item or "").strip()}
    delivery_perf = _cached_delivery_perf if _cached_delivery_perf is not None else _load_delivery_kind_performance()
    target_perf = _cached_target_perf if _cached_target_perf is not None else _load_breaking_target_performance()
    candidates = []
    clusters = _cached_clusters if _cached_clusters is not None else _load_recent_breaking_clusters()
    for cluster in clusters:
        cluster_id = str(cluster.get("cluster_id") or "").strip()
        if not cluster_id:
            continue
        match_score, reasons, matched_topics, matched_sources = _cluster_delivery_match(
            cluster, profile, include_topics=include_topics, include_sources=include_sources
        )
        if match_score < 2.0:
            continue
        if _cached_materials and cluster_id in _cached_materials:
            articles = _cached_materials[cluster_id]["articles"]
            synthesis_created_at = _cached_materials[cluster_id]["summary_date"]
        else:
            articles, synthesis_created_at = _load_cluster_alert_material(cluster_id)
        freshness = assess_cluster_synthesis_freshness(articles, synthesis_created_at)
        alert_meta = _classify_alert_candidate(
            cluster, freshness, matched_topics, matched_sources, delivery_perf, target_perf
        )
        if cluster_id in seen and not freshness.get("refresh_needed"):
            continue
        candidates.append(
            {
                **cluster,
                "match_score": (
                    match_score
                    + min(1.5, float(cluster.get("score") or 0) * 0.15)
                    + min(1.2, float(freshness.get("freshness_score") or 0.0) * 0.4)
                    + float(alert_meta.get("score_adjustment") or 0.0)
                ),
                "match_reason": "; ".join(reasons[:2]),
                "matched_topics": matched_topics[:2],
                "matched_sources": matched_sources[:2],
                "freshness": freshness,
                **alert_meta,
            }
        )
    candidates.sort(key=lambda item: item["match_score"], reverse=True)
    for candidate in candidates:
        if not _alert_throttled(last_breaking_sent_at, alert_context, candidate):
            return candidate
    return None
