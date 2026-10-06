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


def _load_daily_brief_clusters(limit=18, lang="mk", briefing_date=None):
    from .email import _load_weekly_digest_clusters

    return _load_weekly_digest_clusters(limit=limit)


def _prepare_daily_brief():
    from tasks.utils import log

    from .morning_brief import prepare_and_store_brief

    try:
        count = prepare_and_store_brief()
        log.info(f"[briefing] daily brief prepared ({count} clusters)")
        return count
    except Exception as e:
        log.warning(f"[briefing] daily brief generation failed: {e}")
        return 0


@celery_app.task(name="tasks.delivery.briefing.generate_all_daily_briefs_task")
def generate_all_daily_briefs_task(*a, **kw):
    return _prepare_daily_brief()


@celery_app.task(name="tasks.delivery.briefing.generate_daily_brief_task")
def generate_daily_brief_task(*a, **kw):
    return _prepare_daily_brief()


@celery_app.task(name="tasks.delivery.briefing.send_profile_breaking_alerts_task")
def send_profile_breaking_alerts_task(*a, **kw):
    """Email opted-in subscribers a short 'Итна вест' for a new high-signal cluster."""
    import datetime
    import json
    import os

    from core.database import db_manager as db
    from tasks.utils import log, send_email

    from .core import _parse_row_datetime
    from .morning_brief import render_breaking_email
    from .subscribers import _load_active_delivery_rows

    try:
        clusters = db.execute(
            """SELECT cluster_id, synthetic_headline, summary, pluralism_score
               FROM cluster_summaries
               WHERE created_at >= NOW() - INTERVAL '3 hours'
               ORDER BY pluralism_score DESC NULLS LAST
               LIMIT 5"""
        )
    except Exception as e:
        log.warning(f"[briefing] breaking cluster lookup failed: {e}")
        return 0
    if not clusters:
        return 0

    now = datetime.datetime.now(datetime.timezone.utc)
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    sent = 0
    for row in _load_active_delivery_rows():
        if str(row.get("channel") or "").strip().lower() != "email":
            continue
        if not (row.get("breaking_topics") or row.get("breaking_sources")):
            continue
        target = str(row.get("target") or "").strip()
        if not target:
            continue
        last = _parse_row_datetime(row.get("last_breaking_sent_at"))
        if last:
            if last.tzinfo is None:
                last = last.replace(tzinfo=datetime.timezone.utc)
            if (now - last.astimezone(datetime.timezone.utc)).total_seconds() < 3 * 3600:
                continue
        seen = set(row.get("last_alert_cluster_ids") or [])
        fresh = [c for c in clusters if str(c.get("cluster_id")) not in seen]
        if not fresh:
            continue
        cluster = fresh[0]
        subject = f"Пресек — Итна вест: {str(cluster.get('synthetic_headline') or '')[:80]}".strip()
        if send_email(render_breaking_email(cluster), subject, smtp_user, smtp_pass, target):
            db.execute(
                "UPDATE synced_delivery_subscriptions SET last_breaking_sent_at = NOW(), "
                "last_alert_cluster_ids = %s::jsonb, updated_at = NOW() WHERE sync_token = %s",
                (json.dumps([str(cluster.get("cluster_id"))]), row["sync_token"]),
                fetch=False,
            )
            sent += 1
    log.info(f"[briefing] breaking alerts sent: {sent}")
    return sent


@celery_app.task(name="tasks.delivery.briefing.send_profile_briefings_task")
def send_profile_briefings_task(*a, **kw):
    """Deliver the MK morning briefing to active synced email subscribers."""
    import datetime

    from core.database import db_manager as db
    from tasks.utils import log

    from .core import _parse_row_datetime
    from .morning_brief import send_morning_brief_to
    from .subscribers import _load_active_delivery_rows

    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        rows = _load_active_delivery_rows()
    except Exception as e:
        log.warning(f"[briefing] could not load subscribers: {e}")
        return 0

    targets: dict[str, str] = {}
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
        targets[target] = row["sync_token"]
    if not targets:
        return 0

    delivered = send_morning_brief_to(list(targets.keys()))
    for email in delivered:
        db.execute(
            "UPDATE synced_delivery_subscriptions SET last_morning_sent_at = NOW(), updated_at = NOW() WHERE sync_token = %s",
            (targets[email],),
            fetch=False,
        )
    log.info(f"[briefing] morning briefings sent: {len(delivered)}")
    return len(delivered)
