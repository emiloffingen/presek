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
    """Deliver the MK morning briefing to active email subscribers."""
    import datetime
    import os

    from core.database import db_manager as db
    from tasks.utils import log, send_email

    from .core import _parse_row_datetime
    from .morning_brief import build_morning_brief, store_daily_briefing
    from .subscribers import _load_active_delivery_rows

    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        rows = _load_active_delivery_rows()
    except Exception as e:
        log.warning(f"[briefing] could not load subscribers: {e}")
        return 0

    sent = 0
    stored = False
    for row in rows:
        if not row.get("morning_briefing"):
            continue
        if str(row.get("channel") or "ntfy").strip().lower() != "email":
            continue
        target = str(row.get("target") or "").strip()
        if not target:
            continue
        last_sent = _parse_row_datetime(row.get("last_morning_sent_at"))
        if last_sent:
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=datetime.timezone.utc)
            if (now - last_sent.astimezone(datetime.timezone.utc)).total_seconds() < 20 * 3600:
                continue

        subject, html, clusters = build_morning_brief(subscriber_email=target)
        if not clusters:
            continue
        if not stored:
            store_daily_briefing(clusters, now)
            stored = True
        if send_email(html, subject, os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASS", ""), target):
            db.execute(
                "UPDATE synced_delivery_subscriptions SET last_morning_sent_at = NOW(), updated_at = NOW() WHERE sync_token = %s",
                (row["sync_token"],),
                fetch=False,
            )
            sent += 1
    log.info(f"[briefing] morning briefings sent: {sent}")
    return sent
