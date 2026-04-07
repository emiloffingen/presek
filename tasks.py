import logging
import datetime
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from celery_app import celery_app
from ingestion import ingest_feeds, ingest_diaspora_feeds
from database import db_manager as db, prune_db
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, OPENCLAW_URL, OPENCLAW_TOKEN, NTFY_TOPIC, BREAKING_SCORE_THRESHOLD
from ai_engine import (
    translate_to_macedonian,
    sync_call_ai as _call_ai, clean_json_response, generate_cover_art
)
from prompts import (
    TAGGING_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT, 
    SYNTHESIS_SYSTEM_PROMPT, TOPIC_SYSTEM_PROMPT, 
    DAILY_BRIEF_SYSTEM_PROMPT, ENTITY_EXTRACTION_PROMPT
)
from categories import ALLOWED_CATEGORIES, detect_topic, detect_category, THEMATIC_TOPICS
from entities import extract_entities
from health import record_refresh, record_task_event
from utils import rank_articles_in_cluster, score_cluster, score_cluster_for_homepage, redis_client, delete_cache, delete_cache_prefix, assess_cluster_synthesis_freshness
from local_nlp import (
    summarize_article_fallback,
    synthesize_cluster_fallback,
    generate_daily_brief_fallback,
    extract_cluster_tags_locally,
    filter_cluster_tags,
)
from api_helpers import normalize_perspectives, normalize_summary_text

log = logging.getLogger("presek_celery")
_PUBLIC_SITE_URL = str(os.environ.get("PUBLIC_SITE_URL") or "https://presek.live").rstrip("/")


def invalidate_public_data_caches():
    delete_cache_prefix("v4:news:")
    delete_cache("ssr:index:top_clusters")
    delete_cache("trending")
    delete_cache("stats:full")


def invalidate_cluster_caches(cluster_id=None):
    if cluster_id:
        delete_cache(f"cluster:detail:{cluster_id}")
    invalidate_public_data_caches()


def _load_cluster_articles_for_synthesis(cluster_id):
    return db.execute(
        "SELECT title, description, source, link, created_at, category FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
        (cluster_id,)
    )


def _normalize_cluster_synthesis(summary, perspectives, article_rows):
    clean_summary = normalize_summary_text(summary)
    clean_perspectives = normalize_perspectives(perspectives)

    if clean_summary and clean_perspectives:
        return clean_summary, clean_perspectives

    fallback = synthesize_cluster_fallback(article_rows)
    fallback_summary = normalize_summary_text(fallback.get("summary", ""))
    fallback_perspectives = normalize_perspectives(fallback.get("perspectives", []))

    if not clean_summary:
        clean_summary = fallback_summary
    if not clean_perspectives:
        clean_perspectives = fallback_perspectives

    return clean_summary, clean_perspectives


def _load_daily_brief_clusters(limit=6):
    rows = db.execute(
        "SELECT cluster_id, title, description, summary, source, category, topic, created_at FROM articles "
        "WHERE created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC LIMIT 180"
    )
    clusters = {}
    for row in rows:
        clusters.setdefault(row["cluster_id"], []).append(row)

    ranked_clusters = []
    for cluster_id, articles in clusters.items():
        ranked = rank_articles_in_cluster(articles)
        if not ranked:
            continue
        lead = ranked[0]
        synthesis_row = db.execute_one(
            "SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s",
            (cluster_id,),
        )
        normalized_perspectives = normalize_perspectives((synthesis_row or {}).get("perspectives") or [])
        open_point = ""
        difference_point = ""
        if normalized_perspectives:
            for item in normalized_perspectives:
                angle = str(item.get("angle") or "").lower()
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                if not difference_point and ("различ" in angle or "акцент" in angle):
                    difference_point = content
                if not open_point and ("отвор" in angle or "нејас" in angle):
                    open_point = content
        ranked_clusters.append({
            "cluster_id": cluster_id,
            "title": lead.get("title"),
            "description": lead.get("summary") or lead.get("description") or "",
            "source": lead.get("source"),
            "category": lead.get("category"),
            "topic": lead.get("topic"),
            "created_at": lead.get("created_at"),
            "source_count": len({a.get("source") for a in ranked if a.get("source")}),
            "difference_point": difference_point,
            "open_point": open_point,
            "cluster_summary": (synthesis_row or {}).get("summary") or "",
            "score": score_cluster_for_homepage(ranked),
            "other_titles": [str(item.get("title") or "").strip() for item in ranked[1:4] if str(item.get("title") or "").strip()],
        })

    ranked_clusters.sort(key=lambda item: item["score"], reverse=True)
    return ranked_clusters[:limit]


def _build_daily_brief_context(clusters):
    blocks = []
    for index, cluster in enumerate(clusters[:6], start=1):
        blocks.append(
            "\n".join([
                f"### Кластер {index}",
                f"Наслов: {cluster.get('title') or ''}",
                f"Категорија: {cluster.get('category') or cluster.get('topic') or 'Вести'}",
                f"Водечки извор: {cluster.get('source') or 'Извор'}",
                f"Број на извори: {cluster.get('source_count') or 1}",
                f"Краток контекст: {cluster.get('description') or ''}",
                f"Синтеза: {cluster.get('cluster_summary') or ''}",
                f"Други агли: {' | '.join(cluster.get('other_titles') or [])}",
                f"Разлики: {cluster.get('difference_point') or ''}",
                f"Отворено: {cluster.get('open_point') or ''}",
            ])
        )
    return "\n\n".join(blocks)


def _normalize_synced_profile_for_delivery(profile):
    profile = profile or {}
    return {
        "followedTopics": [str(item or "").strip() for item in profile.get("followedTopics") or [] if str(item or "").strip()],
        "followedSources": [str(item or "").strip() for item in profile.get("followedSources") or [] if str(item or "").strip()],
        "recentClusters": profile.get("recentClusters") or [],
        "deliveryPreferences": profile.get("deliveryPreferences") or {},
    }


def _load_active_delivery_rows():
    return db.execute(
        """SELECT s.sync_token, s.channel, s.target, s.morning_briefing, s.weekly_digest, s.breaking_topics,
                  s.breaking_sources, s.is_active, s.last_morning_sent_at, s.last_weekly_sent_at, s.last_breaking_sent_at,
                  s.last_alert_cluster_ids, s.last_alert_context, p.profile_data
           FROM synced_delivery_subscriptions s
           JOIN synced_reader_profiles p ON p.sync_token = s.sync_token
           WHERE s.is_active = TRUE"""
    )


def _cluster_delivery_match(cluster, profile, *, include_topics=True, include_sources=True):
    followed_topics = {str(item or "").strip() for item in profile.get("followedTopics") or [] if str(item or "").strip()}
    followed_sources = {str(item or "").strip() for item in profile.get("followedSources") or [] if str(item or "").strip()}

    cluster_topics = {
        str(cluster.get("category") or "").strip(),
        str(cluster.get("topic") or "").strip(),
    }
    lead_source = str(cluster.get("source") or "").strip()

    score = 0.0
    reasons = []

    topic_hits = sorted(topic for topic in cluster_topics if topic and topic in followed_topics)
    if include_topics and topic_hits:
        score += 2.8 + (0.4 * len(topic_hits))
        reasons.append(f"следена тема: {', '.join(topic_hits[:2])}")

    if include_sources and lead_source and lead_source in followed_sources:
        score += 2.4
        reasons.append(f"следен извор: {lead_source}")

    score += min(1.0, max(0, int(cluster.get("source_count") or 0) - 1) * 0.2)
    score += min(0.9, float(cluster.get("score") or 0) * 0.12)

    return score, reasons, topic_hits, [lead_source] if lead_source and lead_source in followed_sources else []


def _build_profile_briefing_message(profile, clusters):
    profile = _normalize_synced_profile_for_delivery(profile)
    followed_topics = profile["followedTopics"][:3]
    followed_sources = profile["followedSources"][:3]
    lines = ["Пресек персонализиран брифинг"]

    if followed_topics:
        lines.append(f"Следени теми: {', '.join(followed_topics)}")
    if followed_sources:
        lines.append(f"Следени извори: {', '.join(followed_sources)}")

    for cluster in clusters[:4]:
        reason_text = cluster.get("match_reason") or "важна развојна линија"
        lines.append("")
        lines.append(f"• {cluster.get('title') or 'Важна приказна'}")
        lines.append(f"  {cluster.get('source') or 'Извор'} · {cluster.get('source_count') or 1} извори · {reason_text}")
        if cluster.get("cluster_summary"):
            lines.append(f"  {str(cluster['cluster_summary']).splitlines()[0][:220]}")
        elif cluster.get("description"):
            lines.append(f"  {str(cluster['description'])[:220]}")
        if cluster.get("difference_point"):
            lines.append(f"  Разлика: {str(cluster['difference_point'])[:180]}")
        elif cluster.get("open_point"):
            lines.append(f"  Отворено: {str(cluster['open_point'])[:180]}")

    return "\n".join(line for line in lines if line is not None).strip()


def _briefing_cluster_editorial_bonus(cluster):
    bonus = 0.0
    if str(cluster.get("difference_point") or "").strip():
        bonus += 0.45
    if str(cluster.get("open_point") or "").strip():
        bonus += 0.35
    if str(cluster.get("cluster_summary") or "").strip():
        bonus += 0.2
    if int(cluster.get("source_count") or 0) >= 3:
        bonus += 0.18
    if len(cluster.get("other_titles") or []) >= 2:
        bonus += 0.12
    return bonus


def _dedupe_briefing_candidates(candidates, limit=4):
    selected = []
    topic_counts = {}
    seen_titles = []

    for item in candidates:
        title = str(item.get("title") or "").strip()
        topic = str(item.get("topic") or item.get("category") or "Вести").strip()
        if not title:
            continue

        # Avoid stacking near-identical leads in the same brief.
        if any(
            str(other_title).casefold() == title.casefold()
            or (len(set(title.lower().split()) | set(str(other_title).lower().split())) and
                len(set(title.lower().split()) & set(str(other_title).lower().split())) /
                len(set(title.lower().split()) | set(str(other_title).lower().split())) >= 0.72)
            for other_title in seen_titles
        ):
            continue

        # Keep variety across topics/categories; allow two if the score is clearly strong.
        count = topic_counts.get(topic, 0)
        if count >= 2:
            continue
        if count >= 1:
            strength = float(item.get("match_score") or item.get("score") or 0.0)
            has_editorial_depth = bool(item.get("difference_point") or item.get("open_point"))
            if strength < 4.4 or not has_editorial_depth:
                continue

        selected.append(item)
        seen_titles.append(title)
        topic_counts[topic] = count + 1
        if len(selected) >= limit:
            break

    return selected


def _load_weekly_digest_clusters(limit=32):
    rows = db.execute(
        "SELECT cluster_id, title, description, summary, source, category, topic, created_at "
        "FROM articles WHERE created_at >= NOW() - INTERVAL '7 days' ORDER BY created_at DESC LIMIT 420"
    )
    clusters = {}
    for row in rows:
        clusters.setdefault(row["cluster_id"], []).append(row)

    ranked_clusters = []
    for cluster_id, articles in clusters.items():
        ranked = rank_articles_in_cluster(articles)
        if not ranked:
            continue
        lead = ranked[0]
        synthesis_row = db.execute_one(
            "SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s",
            (cluster_id,),
        )
        normalized_perspectives = normalize_perspectives((synthesis_row or {}).get("perspectives") or [])
        difference_point = ""
        open_point = ""
        for item in normalized_perspectives:
            angle = str(item.get("angle") or "").lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            if not difference_point and ("различ" in angle or "акцент" in angle):
                difference_point = content
            if not open_point and ("отвор" in angle or "нејас" in angle):
                open_point = content

        ranked_clusters.append({
            "cluster_id": cluster_id,
            "title": lead.get("title"),
            "description": lead.get("summary") or lead.get("description") or "",
            "source": lead.get("source"),
            "category": lead.get("category"),
            "topic": lead.get("topic"),
            "created_at": lead.get("created_at"),
            "source_count": len({a.get("source") for a in ranked if a.get("source")}),
            "difference_point": difference_point,
            "open_point": open_point,
            "cluster_summary": (synthesis_row or {}).get("summary") or "",
            "score": score_cluster_for_homepage(ranked),
            "other_titles": [str(item.get("title") or "").strip() for item in ranked[1:5] if str(item.get("title") or "").strip()],
        })

    ranked_clusters.sort(key=lambda item: item["score"], reverse=True)
    return ranked_clusters[:limit]


def _load_weekly_cluster_engagement(days=45):
    send_rows = db.execute(
        "SELECT id, cluster_id, metadata "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type = 'send' "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )
    child_rows = db.execute(
        "SELECT parent_event_id, event_type "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type IN ('open', 'click') "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )

    child_map = {}
    for row in child_rows or []:
        parent_id = int(row.get("parent_event_id") or 0)
        if parent_id <= 0:
            continue
        bucket = child_map.setdefault(parent_id, {"opens": 0, "clicks": 0})
        event_type = str(row.get("event_type") or "").strip()
        if event_type == "open":
            bucket["opens"] += 1
        elif event_type == "click":
            bucket["clicks"] += 1

    engagement = {}
    for row in send_rows or []:
        event_id = int(row.get("id") or 0)
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        cluster_ids = []
        for cluster_id in (metadata.get("cluster_ids") or []):
            clean_id = str(cluster_id or "").strip()
            if clean_id:
                cluster_ids.append(clean_id)
        if not cluster_ids:
            clean_id = str(row.get("cluster_id") or "").strip()
            if clean_id:
                cluster_ids.append(clean_id)
        if not cluster_ids:
            continue

        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}
        for cluster_id in cluster_ids:
            bucket = engagement.setdefault(cluster_id, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

    for cluster_id, bucket in engagement.items():
        sends = int(bucket.get("sends") or 0)
        opens = int(bucket.get("opens") or 0)
        clicks = int(bucket.get("clicks") or 0)
        bucket["open_rate"] = (opens / sends) if sends else 0.0
        bucket["click_rate"] = (clicks / sends) if sends else 0.0
        bucket["engagement_score"] = round(
            min(1.1, bucket["click_rate"] * 1.5 + bucket["open_rate"] * 0.55 + min(0.25, clicks * 0.05)),
            3,
        )
    return engagement


def _load_weekly_topic_engagement(days=45):
    send_rows = db.execute(
        "SELECT id, metadata "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type = 'send' "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )
    child_rows = db.execute(
        "SELECT parent_event_id, event_type "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type IN ('open', 'click') "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )

    child_map = {}
    for row in child_rows or []:
        parent_id = int(row.get("parent_event_id") or 0)
        if parent_id <= 0:
            continue
        bucket = child_map.setdefault(parent_id, {"opens": 0, "clicks": 0})
        event_type = str(row.get("event_type") or "").strip()
        if event_type == "open":
            bucket["opens"] += 1
        elif event_type == "click":
            bucket["clicks"] += 1

    topic_map = {}
    for row in send_rows or []:
        event_id = int(row.get("id") or 0)
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}
        for topic in (metadata.get("focus_topics") or []):
            clean = str(topic or "").strip()
            if not clean:
                continue
            bucket = topic_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

    for bucket in topic_map.values():
        sends = int(bucket.get("sends") or 0)
        opens = int(bucket.get("opens") or 0)
        clicks = int(bucket.get("clicks") or 0)
        bucket["open_rate"] = (opens / sends) if sends else 0.0
        bucket["click_rate"] = (clicks / sends) if sends else 0.0
        bucket["section_score"] = round(
            min(1.2, bucket["click_rate"] * 1.8 + bucket["open_rate"] * 0.7 + min(0.2, clicks * 0.04)),
            3,
        )
    return topic_map


def _load_weekly_source_engagement(days=45):
    send_rows = db.execute(
        "SELECT id, metadata "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type = 'send' "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )
    child_rows = db.execute(
        "SELECT parent_event_id, event_type "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type IN ('open', 'click') "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )

    child_map = {}
    for row in child_rows or []:
        parent_id = int(row.get("parent_event_id") or 0)
        if parent_id <= 0:
            continue
        bucket = child_map.setdefault(parent_id, {"opens": 0, "clicks": 0})
        event_type = str(row.get("event_type") or "").strip()
        if event_type == "open":
            bucket["opens"] += 1
        elif event_type == "click":
            bucket["clicks"] += 1

    source_map = {}
    for row in send_rows or []:
        event_id = int(row.get("id") or 0)
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}
        for source in (metadata.get("focus_sources") or []):
            clean = str(source or "").strip()
            if not clean:
                continue
            bucket = source_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

    for bucket in source_map.values():
        sends = int(bucket.get("sends") or 0)
        opens = int(bucket.get("opens") or 0)
        clicks = int(bucket.get("clicks") or 0)
        bucket["open_rate"] = (opens / sends) if sends else 0.0
        bucket["click_rate"] = (clicks / sends) if sends else 0.0
        bucket["section_score"] = round(
            min(1.15, bucket["click_rate"] * 1.75 + bucket["open_rate"] * 0.6 + min(0.18, clicks * 0.04)),
            3,
        )
    return source_map


def _build_weekly_digest_sections(profile, clusters, topic_engagement=None, source_engagement=None):
    profile = _normalize_synced_profile_for_delivery(profile)
    followed_topics = [topic for topic in profile["followedTopics"] if topic]
    followed_sources = [source for source in profile["followedSources"] if source]
    topic_engagement = topic_engagement or {}
    source_engagement = source_engagement or {}

    lead_cluster = clusters[0] if clusters else None
    sections = []

    if lead_cluster:
        sections.append({
            "title": "Што најмногу се помести",
            "subtitle": lead_cluster.get("match_reason") or "главен неделен развој",
            "clusters": [lead_cluster],
        })

    topic_sections = []
    for topic in followed_topics:
        matches = [
            cluster for cluster in clusters
            if topic in {
                str(cluster.get("topic") or "").strip(),
                str(cluster.get("category") or "").strip(),
            }
        ]
        if not matches:
            continue
        performance = topic_engagement.get(topic) or {}
        topic_sections.append({
            "title": f"Следена тема: {topic}",
            "subtitle": (
                "силен интерес во претходните неделни прегледи"
                if float(performance.get("section_score") or 0.0) >= 0.65
                else "најважните линии за темата што ја следите"
            ),
            "clusters": matches[:2],
            "score": float(performance.get("section_score") or 0.0) + max(float(matches[0].get("match_score") or 0.0), 0.0),
        })
    topic_sections.sort(key=lambda item: item.get("score") or 0.0, reverse=True)
    sections.extend(topic_sections[:2])

    source_focus = []
    if followed_sources:
        for source in followed_sources[:3]:
            source_cluster = next((cluster for cluster in clusters if str(cluster.get("source") or "").strip() == source), None)
            if source_cluster:
                source_focus.append((source, source_cluster))
    if source_focus:
        source_focus.sort(
            key=lambda item: (
                float((source_engagement.get(item[0]) or {}).get("section_score") or 0.0),
                float(item[1].get("match_score") or 0.0),
                float(item[1].get("score") or 0.0),
            ),
            reverse=True,
        )
        source_clusters = [cluster for _, cluster in source_focus[:2]]
        strongest_source = source_focus[0][0]
        strongest_source_perf = source_engagement.get(strongest_source) or {}
        sections.append({
            "title": "Извори што ги следите",
            "subtitle": (
                f"{strongest_source} носи најсилен одзив меѓу следените извори оваа недела"
                if float(strongest_source_perf.get("section_score") or 0.0) >= 0.6
                else "каде следените извори ја водат или потврдуваат неделата"
            ),
            "clusters": source_clusters,
            "score": float(strongest_source_perf.get("section_score") or 0.0) + max(float(source_clusters[0].get("match_score") or 0.0), 0.0),
        })

    open_items = [cluster for cluster in clusters if cluster.get("open_point")]
    if open_items:
        sections.append({
            "title": "Што останува отворено",
            "subtitle": "линии што влегуваат во следната недела без целосна потврда",
            "clusters": open_items[:2],
            "score": max(float(open_items[0].get("match_score") or 0.0), 0.0),
        })

    static_lead = sections[:1]
    dynamic_sections = sections[1:]
    dynamic_sections.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return (static_lead + dynamic_sections)[:4]


def _select_profile_weekly_clusters(profile, limit=5):
    profile = _normalize_synced_profile_for_delivery(profile)
    engagement_map = _load_weekly_cluster_engagement()
    ranked = []
    for cluster in _load_weekly_digest_clusters(limit=28):
        match_score, reasons, _, _ = _cluster_delivery_match(cluster, profile)
        engagement = engagement_map.get(str(cluster.get("cluster_id") or "").strip()) or {}
        engagement_bonus = 0.0
        engagement_note = ""
        sends = int(engagement.get("sends") or 0)
        open_rate = float(engagement.get("open_rate") or 0.0)
        click_rate = float(engagement.get("click_rate") or 0.0)
        if sends >= 2 and click_rate >= 0.22:
            engagement_bonus = 0.85
            engagement_note = "силен одзив во неделните прегледи"
        elif sends >= 2 and open_rate >= 0.55:
            engagement_bonus = 0.45
            engagement_note = "добар одзив во неделните прегледи"
        elif sends >= 3 and open_rate < 0.25 and int(engagement.get("clicks") or 0) == 0:
            engagement_bonus = -0.35
            engagement_note = "послаб одзив во неделните прегледи"

        total_score = (
            match_score
            + min(1.6, float(cluster.get("score") or 0) * 0.2)
            + engagement_bonus
            + min(0.55, float(engagement.get("engagement_score") or 0.0) * 0.35)
        )
        match_reason = "; ".join(reasons[:2]) or "неделна важност"
        if engagement_note:
            match_reason = f"{match_reason}; {engagement_note}"
        ranked.append({
            **cluster,
            "match_score": total_score + _briefing_cluster_editorial_bonus(cluster),
            "match_reason": match_reason,
        })

    personalized = [item for item in ranked if item["match_score"] >= 1.9]
    personalized.sort(key=lambda item: (item["match_score"], item.get("score") or 0), reverse=True)
    return _dedupe_briefing_candidates(personalized or ranked, limit=limit)


def _build_profile_weekly_digest_message(profile, clusters):
    profile = _normalize_synced_profile_for_delivery(profile)
    followed_topics = profile["followedTopics"][:4]
    followed_sources = profile["followedSources"][:4]
    sections = _build_weekly_digest_sections(
        profile,
        clusters,
        _load_weekly_topic_engagement(),
        _load_weekly_source_engagement(),
    )

    lines = ["Пресек неделен преглед"]
    if followed_topics:
        lines.append(f"Фокус теми: {', '.join(followed_topics)}")
    if followed_sources:
        lines.append(f"Фокус извори: {', '.join(followed_sources)}")

    rendered_cluster_ids = set()
    for section in sections:
        section_clusters = []
        for cluster in section.get("clusters") or []:
            cluster_id = str(cluster.get("cluster_id") or "").strip()
            if not cluster_id or cluster_id in rendered_cluster_ids:
                continue
            rendered_cluster_ids.add(cluster_id)
            section_clusters.append(cluster)
        if not section_clusters:
            continue

        lines.append("")
        lines.append(f"## {section.get('title') or 'Клучен дел'}")
        if section.get("subtitle"):
            lines.append(str(section["subtitle"]))

        for cluster in section_clusters[:2]:
            lines.append(f"• {cluster.get('title') or 'Клучна приказна неделава'}")
            lines.append(f"  {cluster.get('source') or 'Извор'} · {cluster.get('source_count') or 1} извори · {cluster.get('match_reason') or 'неделен контекст'}")
            if cluster.get("cluster_summary"):
                lines.append(f"  {str(cluster['cluster_summary']).splitlines()[0][:220]}")
            elif cluster.get("description"):
                lines.append(f"  {str(cluster['description'])[:220]}")
            if cluster.get("difference_point"):
                lines.append(f"  Главна разлика: {str(cluster['difference_point'])[:180]}")
            elif cluster.get("open_point"):
                lines.append(f"  Што остана отворено: {str(cluster['open_point'])[:180]}")

    lines.append("")
    lines.append("Што да следите понатаму: Проверете ги темите и кластерите што остануваат отворени или влегуваат во нова фаза.")
    return "\n".join(line for line in lines if line is not None).strip()


def _select_profile_brief_clusters(profile, limit=4):
    profile = _normalize_synced_profile_for_delivery(profile)
    ranked = []
    for cluster in _load_daily_brief_clusters(limit=18):
        match_score, reasons, _, _ = _cluster_delivery_match(cluster, profile)
        total_score = match_score + min(1.4, float(cluster.get("score") or 0) * 0.18)
        ranked.append({
            **cluster,
            "match_score": total_score + _briefing_cluster_editorial_bonus(cluster),
            "match_reason": "; ".join(reasons[:2]),
        })

    personalized = [item for item in ranked if item["match_score"] >= 2.1]
    personalized.sort(key=lambda item: (item["match_score"], item.get("score") or 0), reverse=True)
    if personalized:
        return _dedupe_briefing_candidates(personalized, limit=limit)

    ranked.sort(key=lambda item: item.get("score") or 0, reverse=True)
    return _dedupe_briefing_candidates(ranked, limit=min(limit, 3))


def _parse_row_datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _record_delivery_tracking_event(sync_token, event_type, delivery_kind, *, channel="ntfy", target="", cluster_id=None, parent_event_id=None, metadata=None):
    row = db.execute_one(
        """INSERT INTO delivery_tracking_events
           (sync_token, parent_event_id, event_type, delivery_kind, channel, target, cluster_id, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
           RETURNING id""",
        (
            sync_token,
            parent_event_id,
            str(event_type or "").strip(),
            str(delivery_kind or "").strip(),
            str(channel or "ntfy").strip() or "ntfy",
            str(target or "").strip(),
            str(cluster_id or "").strip() or None,
            json.dumps(metadata or {}),
        ),
    )
    return int((row or {}).get("id") or 0)


def _tracked_delivery_url(event_id, event_type, path):
    event_id = int(event_id or 0)
    clean_path = str(path or "").strip()
    if not clean_path.startswith("/"):
        clean_path = "/briefing"
    query = urllib.parse.urlencode({"event_id": event_id, "redirect": clean_path})
    return f"{_PUBLIC_SITE_URL}/api/delivery/track/{urllib.parse.quote(str(event_type or 'click'), safe='')}?{query}"


def _send_ntfy_message(topic, title, message, tags="newspaper", click_url=None):
    clean_topic = str(topic or "").strip()
    clean_message = str(message or "").strip()
    if not clean_topic or not clean_message:
        return False

    headers = {
        "Title": str(title or "Пресек").strip()[:120],
        "Tags": str(tags or "newspaper"),
        "Priority": "default",
    }
    if click_url:
        headers["Click"] = str(click_url).strip()[:500]

    url = f"https://ntfy.sh/{urllib.parse.quote(clean_topic, safe='')}"
    req = urllib.request.Request(
        url,
        data=clean_message.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except urllib.error.URLError as e:
        log.warning(f"[tasks] ntfy delivery failed for topic {clean_topic}: {e}")
        return False


def _load_recent_breaking_clusters(hours=4, limit=24):
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


def _normalize_alert_context(context):
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception:
            return {}
    if not isinstance(context, dict):
        return {}
    clean = {}
    for key, value in context.items():
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if key_text and value_text:
            clean[key_text] = value_text
    return clean


def _load_cluster_alert_material(cluster_id):
    articles = db.execute(
        "SELECT title, description, source, link, created_at, category, topic FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
        (cluster_id,),
    )
    summary_row = db.execute_one(
        "SELECT created_at FROM cluster_summaries WHERE cluster_id = %s",
        (cluster_id,),
    )
    return articles, (summary_row or {}).get("created_at")


def _load_delivery_kind_performance(days=30):
    rows = db.execute(
        "SELECT delivery_kind, "
        "COUNT(*) FILTER (WHERE event_type = 'send') AS sends, "
        "COUNT(*) FILTER (WHERE event_type = 'open') AS opens, "
        "COUNT(*) FILTER (WHERE event_type = 'click') AS clicks "
        "FROM delivery_tracking_events "
        "WHERE created_at >= NOW() - (%s * INTERVAL '1 day') "
        "GROUP BY delivery_kind",
        (days,),
    )
    performance = {}
    for row in rows or []:
        kind = str(row.get("delivery_kind") or "").strip()
        if not kind:
            continue
        sends = int(row.get("sends") or 0)
        opens = int(row.get("opens") or 0)
        clicks = int(row.get("clicks") or 0)
        performance[kind] = {
            "sends": sends,
            "opens": opens,
            "clicks": clicks,
            "open_rate": (opens / sends) if sends else 0.0,
            "click_rate": (clicks / sends) if sends else 0.0,
        }
    return performance


def _load_breaking_target_performance(days=45):
    send_rows = db.execute(
        "SELECT id, metadata "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'breaking' AND event_type = 'send' "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )
    child_rows = db.execute(
        "SELECT parent_event_id, event_type "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'breaking' AND event_type IN ('open', 'click') "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )

    child_map = {}
    for row in child_rows or []:
        parent_id = int(row.get("parent_event_id") or 0)
        if parent_id <= 0:
            continue
        bucket = child_map.setdefault(parent_id, {"opens": 0, "clicks": 0})
        event_type = str(row.get("event_type") or "").strip()
        if event_type == "open":
            bucket["opens"] += 1
        elif event_type == "click":
            bucket["clicks"] += 1

    topic_map = {}
    source_map = {}
    for row in send_rows or []:
        event_id = int(row.get("id") or 0)
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}

        for topic in (metadata.get("matched_topics") or []):
            clean = str(topic or "").strip()
            if not clean:
                continue
            bucket = topic_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

        for source in (metadata.get("matched_sources") or []):
            clean = str(source or "").strip()
            if not clean:
                continue
            bucket = source_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

    for mapping in (topic_map, source_map):
        for _, bucket in mapping.items():
            sends = int(bucket.get("sends") or 0)
            opens = int(bucket.get("opens") or 0)
            clicks = int(bucket.get("clicks") or 0)
            bucket["open_rate"] = (opens / sends) if sends else 0.0
            bucket["click_rate"] = (clicks / sends) if sends else 0.0

    return {"topics": topic_map, "sources": source_map}


def _classify_alert_candidate(cluster, freshness, matched_topics, matched_sources, delivery_performance=None, target_performance=None):
    reasons = freshness.get("reasons") or []
    freshness_score = float(freshness.get("freshness_score") or 0.0)
    base_score = float(cluster.get("score") or 0.0)
    delivery_performance = delivery_performance or {}
    target_performance = target_performance or {}
    breaking_perf = delivery_performance.get("breaking") or {}
    breaking_sends = int(breaking_perf.get("sends") or 0)
    breaking_open_rate = float(breaking_perf.get("open_rate") or 0.0)
    breaking_click_rate = float(breaking_perf.get("click_rate") or 0.0)

    alert_label = "Важно ажурирање"
    alert_reason = cluster.get("match_reason") or "оваа приказна силно се врзува со вашите следени теми или извори"
    alert_tags = "newspaper"
    min_gap_minutes = 90
    topic_gap_minutes = 240
    source_gap_minutes = 180
    severity_rank = 1
    score_adjustment = 0.0
    engagement_label = "Нормален одзив"

    if "credible_new_reporting" in reasons or "new_sources" in reasons or base_score >= BREAKING_SCORE_THRESHOLD + 1.4:
        alert_label = "Итно ажурирање"
        alert_reason = "се појави нов доверлив извор или значаен развој"
        alert_tags = "rotating_light,newspaper"
        min_gap_minutes = 30
        topic_gap_minutes = 120
        source_gap_minutes = 90
        severity_rank = 3
    elif "new_numbers" in reasons or "new_angle" in reasons or freshness_score >= 1.8:
        alert_label = "Нова важна промена"
        alert_reason = "има нов агол, бројки или појасна промена во известувањето"
        alert_tags = "newspaper,warning"
        min_gap_minutes = 60
        topic_gap_minutes = 180
        source_gap_minutes = 150
        severity_rank = 2
    elif "multiple_new_reports" in reasons:
        alert_label = "Следен развој"
        alert_reason = "се натрупуваат повеќе нови извештаи околу истата приказна"
        alert_tags = "newspaper"
        min_gap_minutes = 120
        topic_gap_minutes = 360
        source_gap_minutes = 240

    if breaking_sends >= 8 and breaking_click_rate < 0.12 and breaking_open_rate < 0.35:
        engagement_label = "Слаб одзив"
        min_gap_minutes += 75
        topic_gap_minutes += 180
        source_gap_minutes += 120
        if severity_rank < 3:
            score_adjustment -= 0.45
            alert_reason = f"{alert_reason}; праќаме само посилни ажурирања додека одзивот е низок"
    elif breaking_sends >= 6 and (breaking_click_rate >= 0.22 or breaking_open_rate >= 0.58):
        engagement_label = "Силен одзив"
        min_gap_minutes = max(20, min_gap_minutes - 15)
        topic_gap_minutes = max(90, topic_gap_minutes - 45)
        source_gap_minutes = max(75, source_gap_minutes - 30)
        if severity_rank >= 2:
            score_adjustment += 0.25
            alert_reason = f"{alert_reason}; вакви ажурирања и претходно добиваа силен одзив"

    topic_performance = target_performance.get("topics") or {}
    source_performance = target_performance.get("sources") or {}

    topic_rates = [
        topic_performance.get(topic)
        for topic in matched_topics or []
        if topic_performance.get(topic)
    ]
    source_rates = [
        source_performance.get(source)
        for source in matched_sources or []
        if source_performance.get(source)
    ]

    strong_target_signal = any(
        int(item.get("sends") or 0) >= 2 and (
            float(item.get("click_rate") or 0.0) >= 0.22 or
            float(item.get("open_rate") or 0.0) >= 0.65
        )
        for item in topic_rates + source_rates
    )
    weak_target_signal = any(
        int(item.get("sends") or 0) >= 3 and
        float(item.get("open_rate") or 0.0) < 0.2 and
        float(item.get("click_rate") or 0.0) == 0.0
        for item in topic_rates + source_rates
    )

    if strong_target_signal:
        engagement_label = "Силен одзив за следеното"
        min_gap_minutes = max(20, min_gap_minutes - 15)
        topic_gap_minutes = max(75, topic_gap_minutes - 60)
        source_gap_minutes = max(60, source_gap_minutes - 45)
        score_adjustment += 0.3
        alert_reason = f"{alert_reason}; оваа тема или извор претходно добивале силен одзив"
    elif weak_target_signal and severity_rank < 3:
        engagement_label = "Слаб одзив за следеното"
        min_gap_minutes += 60
        topic_gap_minutes += 120
        source_gap_minutes += 120
        score_adjustment -= 0.35
        alert_reason = f"{alert_reason}; оваа тема или извор претходно имале слаб одзив"

    throttle_keys = [f"cluster:{str(cluster.get('cluster_id') or '').strip()}"]
    throttle_keys.extend(f"topic:{topic}" for topic in matched_topics[:2])
    throttle_keys.extend(f"source:{source}" for source in matched_sources[:2])

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
        age_minutes = (now - last_global.astimezone(datetime.timezone.utc)).total_seconds() / 60.0
        if age_minutes < candidate["min_gap_minutes"]:
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


def _next_alert_context(existing_context, candidate):
    context = _normalize_alert_context(existing_context)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for key in candidate["throttle_keys"]:
        context[key] = now
    return context


def _select_breaking_cluster_for_profile(profile, seen_cluster_ids, alert_context=None, last_breaking_sent_at=None, *, include_topics=True, include_sources=True):
    profile = _normalize_synced_profile_for_delivery(profile)
    seen = {str(item or "").strip() for item in seen_cluster_ids or [] if str(item or "").strip()}
    delivery_performance = _load_delivery_kind_performance()
    target_performance = _load_breaking_target_performance()

    candidates = []
    for cluster in _load_recent_breaking_clusters():
        cluster_id = str(cluster.get("cluster_id") or "").strip()
        if not cluster_id:
            continue
        match_score, reasons, matched_topics, matched_sources = _cluster_delivery_match(
            cluster,
            profile,
            include_topics=include_topics,
            include_sources=include_sources,
        )
        if match_score < 2.0:
            continue
        articles, synthesis_created_at = _load_cluster_alert_material(cluster_id)
        freshness = assess_cluster_synthesis_freshness(articles, synthesis_created_at)
        alert_meta = _classify_alert_candidate(
            cluster,
            freshness,
            matched_topics,
            matched_sources,
            delivery_performance,
            target_performance,
        )
        if cluster_id in seen and not freshness.get("refresh_needed"):
            continue
        candidates.append({
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
        })

    candidates.sort(key=lambda item: item["match_score"], reverse=True)
    for candidate in candidates:
        if not _alert_throttled(last_breaking_sent_at, alert_context, candidate):
            return candidate
    return None

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def translate_article_task(article_id, title, description):
    """Translates non-Macedonian articles to Macedonian."""
    try:
        translated_title = translate_to_macedonian(title)
        translated_desc = translate_to_macedonian(description) if description else None

        title_changed = bool(translated_title and translated_title.strip() and translated_title != title)
        desc_changed = bool(description and translated_desc is not None and translated_desc != description)

        if translated_title:
            db.execute(
                "UPDATE articles SET title = %s, description = %s, is_translated = %s WHERE id = %s",
                (translated_title, translated_desc, 1 if (title_changed or desc_changed) else 0, article_id), fetch=False
            )
            invalidate_public_data_caches()
            log.info(f"Translated article {article_id}")
    except Exception as e:
        log.error(f"[tasks] Translation failed for {article_id}: {e}")

@celery_app.task(rate_limit='10/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def summarize_article_task(article_id, title, retry_attempt=0):
    """Generates an AI summary for a single article using Presek 4.0 DAL."""
    desc_row = db.execute_one("SELECT description, topic FROM articles WHERE id = %s", (article_id,))
    description = (desc_row or {}).get("description")
    topic = (desc_row or {}).get("topic")
    prompt_parts = [str(title or "").strip()]
    if description:
        prompt_parts.append(f"Опис: {str(description).strip()}")
    prompt = "\n".join(part for part in prompt_parts if part)

    try:
        summary, _ = _call_ai(prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize", topic=topic)
        if summary:
            clean = clean_json_response(summary)
            final = clean.get('summary', str(clean)) if isinstance(clean, dict) else clean
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (final, article_id), fetch=False)
            invalidate_public_data_caches()
            record_task_event("summarize_article", "ok", f"article:{article_id}")
            log.info(f"Successfully summarized article {article_id}")
        else:
            fallback = summarize_article_fallback(title, description, topic=topic)
            if fallback:
                db.execute("UPDATE articles SET summary = %s WHERE id = %s", (fallback, article_id), fetch=False)
                invalidate_public_data_caches()
                record_task_event("summarize_article", "fallback", f"article:{article_id}")
                log.info(f"Stored local fallback summary for article {article_id}")
                if retry_attempt < 2:
                    summarize_article_task.apply_async(args=(article_id, title, retry_attempt + 1), countdown=1800)
            else:
                log.warning(f"No summary generated for article {article_id}")
    except Exception as e:
        fallback = summarize_article_fallback(title, description, topic=topic)
        if fallback:
            db.execute("UPDATE articles SET summary = %s WHERE id = %s", (fallback, article_id), fetch=False)
            invalidate_public_data_caches()
            record_task_event("summarize_article", "fallback", f"article:{article_id}")
            log.warning(f"[tasks] Summarize failed for {article_id}; stored local fallback")
            if retry_attempt < 2:
                summarize_article_task.apply_async(args=(article_id, title, retry_attempt + 1), countdown=1800)
        else:
            record_task_event("summarize_article", "error", f"article:{article_id}")
            log.error(f"[tasks] Summarize failed for {article_id}: {e}")

@celery_app.task(rate_limit='5/m', autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def synthesize_cluster_task(cluster_id, content, retry_attempt=0):
    """Generates a multi-perspective synthesis for a cluster."""
    article_rows = _load_cluster_articles_for_synthesis(cluster_id)
    try:
        raw, _ = _call_ai(f"Статии:\n{content}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True, task_type="synthesis")
        if raw:
            res = clean_json_response(raw)
            summary = res.get('summary', '') if isinstance(res, dict) else res
            generated_article = res.get('article', '') if isinstance(res, dict) else ''
            perspectives = res.get('perspectives', []) if isinstance(res, dict) else []

            sentiment_data = {
                "sentiment": res.get('sentiment', {}),
                "tone_analysis": res.get('tone_analysis', {})
            }

            summary, perspectives = _normalize_cluster_synthesis(summary, perspectives, article_rows)
        else:
            fallback = synthesize_cluster_fallback(article_rows)
            sentiment_data = {"sentiment": {"score": 0, "label": "неутрален"}, "tone_analysis": {}}
            summary, perspectives = _normalize_cluster_synthesis(
                fallback.get("summary", ""),
                fallback.get("perspectives", []),
                article_rows,
            )
            generated_article = ""
            if (summary or perspectives) and retry_attempt < 2:
                synthesize_cluster_task.apply_async(args=(cluster_id, content, retry_attempt + 1), countdown=1800)

        if summary or perspectives:
            db.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, generated_article, perspectives, created_at, sentiment)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE
                   SET summary = EXCLUDED.summary,
                       generated_article = EXCLUDED.generated_article,
                       perspectives = EXCLUDED.perspectives,
                       created_at = EXCLUDED.created_at,
                       sentiment = EXCLUDED.sentiment""",
                (cluster_id, summary, generated_article, json.dumps(perspectives), datetime.datetime.now(), json.dumps(sentiment_data)),
                fetch=False
            )
            any_img = db.execute_one("SELECT 1 FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL LIMIT 1", (cluster_id,))
            if not any_img:
                img_url = generate_cover_art(cluster_id, summary)
                if img_url:
                    db.execute("UPDATE articles SET image_url = %s WHERE id = (SELECT id FROM articles WHERE cluster_id = %s LIMIT 1)", (img_url, cluster_id), fetch=False)
            invalidate_cluster_caches(cluster_id)
            record_task_event("synthesize_cluster", "ok", f"cluster:{cluster_id}")
            log.info(f"Successfully synthesized cluster {cluster_id}")
        else:
            record_task_event("synthesize_cluster", "empty", f"cluster:{cluster_id}")
            log.warning(f"No synthesis generated for cluster {cluster_id}")
    except Exception as e:
        fallback = synthesize_cluster_fallback(article_rows)
        sentiment_data = {"sentiment": {"score": 0, "label": "неутрален"}, "tone_analysis": {}}
        summary, perspectives = _normalize_cluster_synthesis(
            fallback.get("summary", ""),
            fallback.get("perspectives", []),
            article_rows,
        )
        if summary or perspectives:
            db.execute(
                """INSERT INTO cluster_summaries (cluster_id, summary, generated_article, perspectives, created_at, sentiment)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (cluster_id) DO UPDATE
                   SET summary = EXCLUDED.summary, 
                       generated_article = EXCLUDED.generated_article,
                       perspectives = EXCLUDED.perspectives, 
                       created_at = EXCLUDED.created_at,
                       sentiment = EXCLUDED.sentiment""",
                (cluster_id, summary, "", json.dumps(perspectives), datetime.datetime.now(), json.dumps(sentiment_data)),
                fetch=False
            )
            invalidate_cluster_caches(cluster_id)
            record_task_event("synthesize_cluster", "fallback", f"cluster:{cluster_id}")
            log.warning(f"[tasks] Synthesis failed for {cluster_id}; stored local fallback")
            if retry_attempt < 2:
                synthesize_cluster_task.apply_async(args=(cluster_id, content, retry_attempt + 1), countdown=1800)
        else:
            record_task_event("synthesize_cluster", "error", f"cluster:{cluster_id}")
            log.error(f"[tasks] Synthesis failed for {cluster_id}: {e}")

@celery_app.task
def run_ingestion():
    """
    Main ingestion orchestrator. 
    Serialized for efficiency and to prevent DB/API bottlenecks.
    """
    log.info("Presek 4.0: Starting unified ingestion cycle...")
    new_count, errors = ingest_feeds()
    
    # Record health metrics
    record_refresh(new_count, errors)
    record_task_event("run_ingestion", "ok" if not errors else "warning", f"new_articles:{new_count}")
    if new_count > 0:
        invalidate_public_data_caches()
    
    if new_count > 0:
        # Chain dependent tasks to prevent resource spikes
        # 1. Embed new articles first (crucial for clustering/search)
        # 2. Extract metadata & entities
        # 3. Categorize & summarize
        (
            generate_embeddings_task.si() |
            generate_cluster_metadata_task.si() |
            classify_topics_task.si() |
            extract_entities_task.si() |
            recategorize_clusters_task.si() |
            auto_summarize_task.si()
        ).apply_async()
        
    log.info(f"Ingestion cycle orchestrated. Added {new_count} articles.")

@celery_app.task
def auto_summarize_task():
    """Dispatch summarization/synthesis tasks for top clusters."""
    from ai_engine import auto_summarize_top_clusters
    auto_summarize_top_clusters()


@celery_app.task
def extract_entities_task():
    """Extract entities for top clusters using free rule-based logic first."""
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        rows = db.execute("""
            SELECT cluster_id, array_agg(DISTINCT title) as titles, MAX(description) as desc
            FROM articles WHERE created_at >= %s GROUP BY cluster_id
            HAVING COUNT(DISTINCT source) >= 2 LIMIT 20
        """, (cutoff,))

        for r in rows:
            text = f"{' '.join(r['titles'])} {r['desc'] or ''}"
            
            # Rule-based (Free)
            entities = extract_entities(text)
            
            if entities:
                from entities import update_knowledge_graph
                # Pass context text for local sentiment calculation
                update_knowledge_graph(entities, context_text=text)

            for ent in entities:
                db.execute(
                    "INSERT INTO cluster_entities (cluster_id, entity_name, entity_type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (r['cluster_id'], ent.get('name'), ent.get('type')), fetch=False
                )
        invalidate_public_data_caches()
        record_task_event("extract_entities", "ok", "clusters:recent")
    except Exception as e:
        record_task_event("extract_entities", "error", "clusters:recent")
        log.error(f"[tasks] Entity extraction failed: {e}")

@celery_app.task
def classify_topics_task():
    """Classify default 'Вести' clusters into specific topics using rule-based detection first."""
    try:
        rows = db.execute("SELECT cluster_id, title FROM articles WHERE topic = 'Вести' LIMIT 50")
        for r in rows:
            # Rule-based first (Free)
            topic = detect_topic(r['title'])
            if topic != 'Вести':
                db.execute("UPDATE articles SET topic = %s WHERE cluster_id = %s", (topic, r['cluster_id']), fetch=False)
                continue
            
            # AI Fallback (Optional, commented out to save money as requested)
            """
            res, _ = _call_ai(r['title'], TOPIC_SYSTEM_PROMPT, task_type="topic", max_tokens=20)
            if res:
                topic = res.strip().strip('"').strip('.')
                if topic in THEMATIC_TOPICS:
                    db.execute("UPDATE articles SET topic = %s WHERE cluster_id = %s", (topic, r['cluster_id']), fetch=False)
            """
    except Exception as e:
        record_task_event("classify_topics", "error", "clusters:recent")
        log.error(f"[tasks] Topic classification failed: {e}")
    else:
        invalidate_public_data_caches()
        record_task_event("classify_topics", "ok", "clusters:recent")

@celery_app.task
def recategorize_clusters_task():
    """Verify if 'Македонија' articles belong in specialized categories using rule-based detection."""
    try:
        rows = db.execute("SELECT cluster_id, title, description FROM articles WHERE category = 'Македонија' LIMIT 20")
        for r in rows:
            # Rule-based first (Free)
            res = detect_category(r['title'], description=r.get('description', ''))
            if res != 'Македонија':
                db.execute("UPDATE articles SET category = %s WHERE cluster_id = %s", (res, r['cluster_id']), fetch=False)
                continue

            # AI Fallback (Commented out to save money)
            """
            res, _ = _call_ai(r['title'], "Категоризирај ја веста: " + r['title'], task_type="categorize", max_tokens=20)
            if res and res in ALLOWED_CATEGORIES and res != 'Македонија':
                db.execute("UPDATE articles SET category = %s WHERE cluster_id = %s", (res, r['cluster_id']), fetch=False)
            """
    except Exception as e:
        record_task_event("recategorize_clusters", "error", "clusters:recent")
        log.error(f"[tasks] Recategorization failed: {e}")
    else:
        invalidate_public_data_caches()
        record_task_event("recategorize_clusters", "ok", "clusters:recent")

@celery_app.task
def generate_daily_brief_task(retry_attempt=0):
    """Generate the flagship morning briefing."""
    try:
        clusters = _load_daily_brief_clusters(limit=6)
        context = _build_daily_brief_context(clusters)
        brief, _ = _call_ai(context, DAILY_BRIEF_SYSTEM_PROMPT, task_type="daily_brief")
        final_brief = brief or generate_daily_brief_fallback(clusters)
        if final_brief:
            db.execute("INSERT INTO daily_briefings (date, content) VALUES (CURRENT_DATE, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content", (final_brief,), fetch=False)
            delete_cache("daily_brief:latest")
            record_task_event("daily_brief", "ok" if brief else "fallback", "date:current")
            if not brief and retry_attempt < 2:
                generate_daily_brief_task.apply_async(args=(retry_attempt + 1,), countdown=1800)
    except Exception as e:
        clusters = _load_daily_brief_clusters(limit=6)
        fallback = generate_daily_brief_fallback(clusters)
        if fallback:
            db.execute("INSERT INTO daily_briefings (date, content) VALUES (CURRENT_DATE, %s) ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content", (fallback,), fetch=False)
            delete_cache("daily_brief:latest")
            record_task_event("daily_brief", "fallback", "date:current")
            log.warning("[tasks] Daily brief failed; stored local fallback briefing")
            if retry_attempt < 2:
                generate_daily_brief_task.apply_async(args=(retry_attempt + 1,), countdown=1800)
        else:
            record_task_event("daily_brief", "error", "date:current")
            log.error(f"[tasks] Daily brief failed: {e}")

@celery_app.task
def run_prune_db():
    """Standard maintenance."""
    prune_db()
    from ai_engine import cleanup_cover_art
    cleanup_cover_art()


@celery_app.task
def generate_cluster_metadata_task():
    """Tag recent clusters with metadata (entities, source count, and representative image)."""
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        rows = db.execute("""
            SELECT cluster_id, array_agg(DISTINCT source) as sources, array_agg(DISTINCT title) as titles
            FROM articles WHERE created_at >= %s
            GROUP BY cluster_id HAVING COUNT(*) >= 2
        """, (cutoff,))
        for r in rows:
            entities = db.execute(
                "SELECT entity_name, entity_type FROM cluster_entities WHERE cluster_id = %s",
                (r['cluster_id'],)
            )
            entity_candidates = [dict(e) for e in entities]
            final_tags = extract_cluster_tags_locally(
                titles=r['titles'],
                entity_names=entity_candidates,
                sources=r['sources'],
                top_n=8,
            )
            if not final_tags:
                final_tags = filter_cluster_tags(r['sources'], limit=4)
            
            # 3. Representative Image Selection
            # We ONLY use images that belong to this specific cluster.
            # Using fallbacks from "similar clusters" causes massive duplication.
            img_row = db.execute_one(
                "SELECT image_url FROM articles WHERE cluster_id = %s AND image_url IS NOT NULL ORDER BY created_at DESC LIMIT 1",
                (r['cluster_id'],)
            )
            rep_image = img_row['image_url'] if img_row else None

            # If still no image after all extraction attempts, trigger a placeholder generation
            if not rep_image:
                rep_image = generate_cover_art(r['cluster_id'], r['titles'][0] if r['titles'] else 'Вест')

            db.execute(
                """INSERT INTO cluster_metadata (cluster_id, tags, representative_image, updated_at)
                   VALUES (%s, %s, %s, NOW())
                   ON CONFLICT (cluster_id) DO UPDATE SET 
                   tags = EXCLUDED.tags, 
                   representative_image = EXCLUDED.representative_image,
                   updated_at = NOW()""",
                (r['cluster_id'], final_tags, rep_image), fetch=False
            )
        invalidate_public_data_caches()
        record_task_event("cluster_metadata", "ok", "clusters:recent")
    except Exception as e:
        record_task_event("cluster_metadata", "error", "clusters:recent")
        log.error(f"[tasks] Cluster metadata generation failed: {e}")


@celery_app.task
def send_daily_digest_task():
    """Send daily email digest. Placeholder — implement with digest module."""
    try:
        import digest as digest_module
        digest_module.send_digest()
    except Exception as e:
        log.warning(f"[tasks] Daily digest skipped: {e}")


@celery_app.task
def send_telegram_briefing_task():
    """Send daily briefing to Telegram channel."""
    try:
        row = db.execute_one(
            "SELECT content FROM daily_briefings WHERE date = CURRENT_DATE"
        )
        if not row or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            return
        import urllib.request
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": row["content"][:4096]}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        log.info("[tasks] Telegram briefing sent.")
    except Exception as e:
        log.warning(f"[tasks] Telegram briefing failed: {e}")


@celery_app.task
def send_profile_briefings_task():
    """Send scheduled morning briefings for synced delivery subscriptions."""
    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0

    try:
        rows = _load_active_delivery_rows()
        for row in rows:
            if not row.get("morning_briefing"):
                continue

            last_sent = _parse_row_datetime(row.get("last_morning_sent_at"))
            if last_sent and last_sent.date() == now.date():
                continue

            target = str(row.get("target") or NTFY_TOPIC).strip()
            profile = _normalize_synced_profile_for_delivery(row.get("profile_data") or {})
            clusters = _select_profile_brief_clusters(profile)
            if not clusters:
                continue

            message = _build_profile_briefing_message(profile, clusters)
            if not message:
                continue

            primary_cluster_id = str((clusters[0] or {}).get("cluster_id") or "").strip() or None
            send_event_id = _record_delivery_tracking_event(
                row["sync_token"],
                "send",
                "morning",
                target=target,
                cluster_id=primary_cluster_id,
                metadata={"cluster_ids": [str(item.get("cluster_id") or "").strip() for item in clusters[:4] if str(item.get("cluster_id") or "").strip()]},
            )
            click_url = _tracked_delivery_url(send_event_id, "open", "/briefing") if send_event_id else None
            click_track_url = _tracked_delivery_url(send_event_id, "click", "/briefing") if send_event_id else None
            message_with_link = message if not click_track_url else f"{message}\n\nОтвори брифинг: {click_track_url}"
            if _send_ntfy_message(
                target,
                "Пресек · Утрински брифинг",
                message_with_link,
                tags="newspaper,sunrise",
                click_url=click_url,
            ):
                db.execute(
                    "UPDATE synced_delivery_subscriptions SET last_morning_sent_at = NOW(), updated_at = NOW() WHERE sync_token = %s",
                    (row["sync_token"],),
                    fetch=False,
                )
                sent += 1
    except Exception as e:
        log.warning(f"[tasks] Profile briefings failed: {e}")
    else:
        if sent:
            log.info(f"[tasks] Sent {sent} scheduled profile briefings.")


@celery_app.task
def send_profile_weekly_digests_task():
    """Send scheduled weekly digests for synced delivery subscriptions."""
    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0

    try:
        rows = _load_active_delivery_rows()
        for row in rows:
            if not row.get("weekly_digest"):
                continue

            last_sent = _parse_row_datetime(row.get("last_weekly_sent_at"))
            if last_sent:
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=datetime.timezone.utc)
                if (now - last_sent.astimezone(datetime.timezone.utc)).total_seconds() < 6.5 * 24 * 3600:
                    continue

            target = str(row.get("target") or NTFY_TOPIC).strip()
            profile = _normalize_synced_profile_for_delivery(row.get("profile_data") or {})
            clusters = _select_profile_weekly_clusters(profile)
            if not clusters:
                continue

            message = _build_profile_weekly_digest_message(profile, clusters)
            if not message:
                continue

            primary_cluster_id = str((clusters[0] or {}).get("cluster_id") or "").strip() or None
            send_event_id = _record_delivery_tracking_event(
                row["sync_token"],
                "send",
                "weekly",
                target=target,
                cluster_id=primary_cluster_id,
                metadata={"cluster_ids": [str(item.get("cluster_id") or "").strip() for item in clusters[:5] if str(item.get("cluster_id") or "").strip()]},
            )
            click_url = _tracked_delivery_url(send_event_id, "open", "/briefing") if send_event_id else None
            click_track_url = _tracked_delivery_url(send_event_id, "click", "/briefing") if send_event_id else None
            message_with_link = message if not click_track_url else f"{message}\n\nОтвори преглед: {click_track_url}"
            if _send_ntfy_message(
                target,
                "Пресек · Неделен преглед",
                message_with_link,
                tags="spiral_calendar,newspaper",
                click_url=click_url,
            ):
                db.execute(
                    "UPDATE synced_delivery_subscriptions SET last_weekly_sent_at = NOW(), updated_at = NOW() WHERE sync_token = %s",
                    (row["sync_token"],),
                    fetch=False,
                )
                sent += 1
    except Exception as e:
        log.warning(f"[tasks] Weekly digests failed: {e}")
    else:
        if sent:
            log.info(f"[tasks] Sent {sent} weekly profile digests.")


@celery_app.task
def send_profile_breaking_alerts_task():
    """Send breaking alerts for followed topics and sources through active synced subscriptions."""
    sent = 0

    try:
        rows = _load_active_delivery_rows()
        for row in rows:
            if not row.get("breaking_topics") and not row.get("breaking_sources"):
                continue

            target = str(row.get("target") or NTFY_TOPIC).strip()
            profile = _normalize_synced_profile_for_delivery(row.get("profile_data") or {})
            existing_ids = row.get("last_alert_cluster_ids") or []
            candidate = _select_breaking_cluster_for_profile(
                profile,
                existing_ids,
                alert_context=row.get("last_alert_context"),
                last_breaking_sent_at=row.get("last_breaking_sent_at"),
                include_topics=bool(row.get("breaking_topics")),
                include_sources=bool(row.get("breaking_sources")),
            )
            if not candidate:
                continue

            title = f"Пресек · {candidate.get('alert_label') or 'Важно ажурирање'}"
            message_lines = [
                candidate.get("title") or "Нова важна развојна линија",
                f"{candidate.get('source') or 'Извор'} · {candidate.get('source_count') or 1} извори",
            ]
            why_now = candidate.get("alert_reason") or candidate.get("match_reason")
            if why_now:
                message_lines.append(f"Зошто сега: {why_now}")
            if candidate.get("match_reason"):
                message_lines.append(f"Зошто го добивате ова: {candidate['match_reason']}")
            if candidate.get("cluster_summary"):
                message_lines.append(str(candidate["cluster_summary"]).splitlines()[0][:240])
            elif candidate.get("description"):
                message_lines.append(str(candidate["description"])[:240])
            if candidate.get("difference_point"):
                message_lines.append(f"Разлика: {str(candidate['difference_point'])[:180]}")
            elif candidate.get("open_point"):
                message_lines.append(f"Отворено: {str(candidate['open_point'])[:180]}")

            cluster_id = str(candidate.get("cluster_id") or "").strip() or None
            send_event_id = _record_delivery_tracking_event(
                row["sync_token"],
                "send",
                "breaking",
                target=target,
                cluster_id=cluster_id,
                metadata={
                    "matched_topics": candidate.get("matched_topics") or [],
                    "matched_sources": candidate.get("matched_sources") or [],
                    "label": candidate.get("alert_label") or "",
                },
            )
            open_url = _tracked_delivery_url(send_event_id, "open", f"/cluster/{cluster_id}") if send_event_id and cluster_id else (_tracked_delivery_url(send_event_id, "open", "/briefing") if send_event_id else None)
            click_track_url = _tracked_delivery_url(send_event_id, "click", f"/cluster/{cluster_id}") if send_event_id and cluster_id else (_tracked_delivery_url(send_event_id, "click", "/briefing") if send_event_id else None)
            message_text = "\n".join(message_lines)
            if click_track_url:
                message_text = f"{message_text}\nОтвори кластер: {click_track_url}"
            if _send_ntfy_message(
                target,
                title,
                message_text,
                tags=candidate.get("alert_tags") or "newspaper",
                click_url=open_url,
            ):
                next_ids = [str(candidate.get("cluster_id") or "").strip()]
                next_ids.extend(
                    str(item or "").strip()
                    for item in existing_ids
                    if str(item or "").strip() and str(item or "").strip() != str(candidate.get("cluster_id") or "").strip()
                )
                next_context = _next_alert_context(row.get("last_alert_context"), candidate)
                db.execute(
                    "UPDATE synced_delivery_subscriptions "
                    "SET last_breaking_sent_at = NOW(), last_alert_cluster_ids = %s::jsonb, last_alert_context = %s::jsonb, updated_at = NOW() "
                    "WHERE sync_token = %s",
                    (json.dumps(next_ids[:24]), json.dumps(next_context), row["sync_token"]),
                    fetch=False,
                )
                sent += 1
    except Exception as e:
        log.warning(f"[tasks] Profile breaking alerts failed: {e}")
    else:
        if sent:
            log.info(f"[tasks] Sent {sent} profile breaking alerts.")


@celery_app.task(rate_limit='10/m')
def backfill_cover_art_single_task(cluster_id, title):
    """Generate cover art for a single cluster without blocking a worker."""
    try:
        img_url = generate_cover_art(cluster_id, title or '')
        if img_url:
            db.execute(
                "UPDATE articles SET image_url = %s WHERE cluster_id = %s AND image_url IS NULL",
                (img_url, cluster_id), fetch=False
            )
    except Exception as e:
        log.warning(f"[tasks] Cover art generation failed for {cluster_id}: {e}")


@celery_app.task
def backfill_cover_art_task():
    """Queue cover art generation without blocking a worker between items."""
    try:
        rows = db.execute("""
            SELECT DISTINCT a.cluster_id, 
                   (SELECT title FROM articles WHERE cluster_id = a.cluster_id ORDER BY created_at DESC LIMIT 1) as title
            FROM articles a
            WHERE a.image_url IS NULL
              AND a.created_at >= NOW() - INTERVAL '24 hours'
            LIMIT 50
        """)
        for idx, r in enumerate(rows):
            backfill_cover_art_single_task.apply_async(
                args=(r['cluster_id'], r['title'] or ''),
                countdown=idx * 2,
            )
    except Exception as e:
        log.warning(f"[tasks] Cover art backfill failed: {e}")


@celery_app.task
def generate_embeddings_task():
    """Generate pgvector embeddings for articles that don't have one yet."""
    try:
        from embeddings import embed_recent_articles
        embed_recent_articles()
    except Exception as e:
        log.warning(f"[tasks] Embedding generation failed: {e}")
