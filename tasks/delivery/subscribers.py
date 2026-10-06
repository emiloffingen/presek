import json

from core.database import db_manager as db
from tasks.utils import log


def _normalize_synced_profile_for_delivery(profile):
    profile = profile or {}
    return {
        "followedTopics": [
            str(item or "").strip() for item in profile.get("followedTopics") or [] if str(item or "").strip()
        ],
        "followedSources": [
            str(item or "").strip() for item in profile.get("followedSources") or [] if str(item or "").strip()
        ],
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


def _load_newsletter_subscribers():
    """Plain email newsletter signups (the `subscribers` table)."""
    try:
        rows = db.execute("SELECT email FROM subscribers WHERE is_active = TRUE AND email IS NOT NULL")
        return [str(r.get("email") or "").strip() for r in rows if str(r.get("email") or "").strip()]
    except Exception as e:
        log.warning(f"[subscribers] could not load newsletter subscribers: {e}")
        return []


def _cluster_delivery_match(cluster, profile, *, include_topics=True, include_sources=True):
    followed_topics = {
        str(item or "").strip() for item in profile.get("followedTopics") or [] if str(item or "").strip()
    }
    followed_sources = {
        str(item or "").strip() for item in profile.get("followedSources") or [] if str(item or "").strip()
    }

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
        reasons.append(f"sledena tema: {', '.join(topic_hits[:2])}")

    if include_sources and lead_source and lead_source in followed_sources:
        score += 2.4
        reasons.append(f"sledeci izvor: {lead_source}")

    score += min(1.0, max(0, int(cluster.get("source_count") or 0) - 1) * 0.2)
    score += min(0.9, float(cluster.get("score") or 0) * 0.12)

    return (
        score,
        reasons,
        topic_hits,
        [lead_source] if lead_source and lead_source in followed_sources else [],
    )


def _load_weekly_cluster_engagement(days=45):
    send_rows = db.execute(
        """SELECT id, cluster_id, metadata
        FROM delivery_tracking_events
        WHERE delivery_kind = 'weekly' AND event_type = 'send'
        AND created_at >= NOW() - (%s * INTERVAL '1 day')""",
        (days,),
    )

    child_rows = db.execute(
        """SELECT parent_event_id, event_type
        FROM delivery_tracking_events
        WHERE delivery_kind = 'weekly' AND event_type IN ('open', 'click')
        AND created_at >= NOW() - (%s * INTERVAL '1 day')""",
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
            except Exception as e:
                log.debug(f"Failed to parse metadata JSON: {e}")
                metadata = {}
        cluster_ids = []
        for cluster_id in metadata.get("cluster_ids") or []:
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
            min(
                1.1,
                bucket["click_rate"] * 1.5 + bucket["open_rate"] * 0.55 + min(0.25, clicks * 0.05),
            ),
            3,
        )
    return engagement


def _load_weekly_topic_engagement(days=45):
    send_rows = db.execute(
        """SELECT id, metadata
        FROM delivery_tracking_events
        WHERE delivery_kind = 'weekly' AND event_type = 'send'
        AND created_at >= NOW() - (%s * INTERVAL '1 day')""",
        (days,),
    )
    child_rows = db.execute(
        """SELECT parent_event_id, event_type
        FROM delivery_tracking_events
        WHERE delivery_kind = 'weekly' AND event_type IN ('open', 'click')
        AND created_at >= NOW() - (%s * INTERVAL '1 day')""",
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
            except Exception as e:
                log.debug(f"Failed to parse metadata JSON: {e}")
                metadata = {}
        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}
        for topic in metadata.get("focus_topics") or []:
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
            min(
                1.2,
                bucket["click_rate"] * 1.8 + bucket["open_rate"] * 0.7 + min(0.2, clicks * 0.04),
            ),
            3,
        )
    return topic_map


def _load_weekly_source_engagement(days=45):
    send_rows = db.execute(
        """SELECT id, metadata
        FROM delivery_tracking_events
        WHERE delivery_kind = 'weekly' AND event_type = 'send'
        AND created_at >= NOW() - (%s * INTERVAL '1 day')""",
        (days,),
    )
    child_rows = db.execute(
        """SELECT parent_event_id, event_type
        FROM delivery_tracking_events
        WHERE delivery_kind = 'weekly' AND event_type IN ('open', 'click')
        AND created_at >= NOW() - (%s * INTERVAL '1 day')""",
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
            except Exception as e:
                log.debug(f"Failed to parse metadata JSON: {e}")
                metadata = {}
        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}
        for source in metadata.get("focus_sources") or []:
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
            min(
                1.15,
                bucket["click_rate"] * 1.75 + bucket["open_rate"] * 0.6 + min(0.18, clicks * 0.04),
            ),
            3,
        )
    return source_map
