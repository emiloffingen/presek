"""Minimal delivery stubs retained so Celery can import the MK-only app."""

from core.celery_app import celery_app


def _briefing_cluster_editorial_bonus(*args, **kwargs):
    return 0.0


def _dedupe_briefing_candidates(candidates, *args, **kwargs):
    return candidates or []


def _load_daily_brief_clusters(*a, **kw): return []


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
