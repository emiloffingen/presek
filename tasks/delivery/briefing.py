"""Minimal delivery stubs retained so Celery can import the MK-only app."""

from core.celery_app import celery_app


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
    """Drop near-duplicate and topic-overloaded candidates, then cap to limit."""
    selected = []
    topic_counts = {}
    seen_titles = []
    for item in candidates:
        title = str(item.get("title") or "").strip()
        topic = str(item.get("topic") or item.get("category") or "vesti").strip()
        if not title:
            continue
        if any(
            str(other_title).casefold() == title.casefold()
            or (
                len(set(title.lower().split()) | set(str(other_title).lower().split()))
                and len(set(title.lower().split()) & set(str(other_title).lower().split()))
                / max(1, len(set(title.lower().split()) | set(str(other_title).lower().split())))
                >= 0.72
            )
            for other_title in seen_titles
        ):
            continue
        count = topic_counts.get(topic, 0)
        if count >= 2:
            continue
        if count >= 1:
            strength = float(item.get("match_score") or item.get("score") or 0.0)
            if strength < 4.4 or not bool(item.get("difference_point") or item.get("open_point")):
                continue
        selected.append(item)
        seen_titles.append(title)
        topic_counts[topic] = count + 1
        if len(selected) >= limit:
            break
    return selected


def _load_daily_brief_clusters(*a, **kw):
    return []


@celery_app.task(name="tasks.delivery.briefing.generate_all_daily_briefs_task")
def generate_all_daily_briefs_task(*a, **kw):
    return None


@celery_app.task(name="tasks.delivery.briefing.generate_daily_brief_task")
def generate_daily_brief_task(*a, **kw):
    return None


@celery_app.task(name="tasks.delivery.briefing.send_profile_breaking_alerts_task")
def send_profile_breaking_alerts_task(*a, **kw):
    return None


@celery_app.task(name="tasks.delivery.briefing.send_profile_briefings_task")
def send_profile_briefings_task(*a, **kw):
    return None
