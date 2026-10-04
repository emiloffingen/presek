"""Morning briefing email for the MK branch.

Assembles the day's top clusters (their syntheses already exist) into an
editorial "Утрински брифинг" email. No extra AI call: it curates what the
pipeline already produced, so it is deterministic and cheap.
"""

from __future__ import annotations

import datetime
import os

from core.database import db_manager as db
from tasks.utils import log, send_email

from .email import _load_weekly_digest_clusters

SITE = str(os.environ.get("PUBLIC_SITE_URL") or "https://presek.mk").rstrip("/")

_MONTHS_MK = [
    "јануари", "февруари", "март", "април", "мај", "јуни",
    "јули", "август", "септември", "октомври", "ноември", "декември",
]


def _mk_date(dt: datetime.datetime) -> str:
    return f"{dt.day} {_MONTHS_MK[dt.month - 1]} {dt.year}"


def _similar(a: str, b: str) -> bool:
    a, b = a.lower().split(), b.lower().split()
    if not a or not b:
        return False
    union = set(a) | set(b)
    return bool(union) and len(set(a) & set(b)) / len(union) >= 0.72


def pick_morning_clusters(limit: int = 5) -> list[dict]:
    """Top clusters by homepage score, near-dup filtered, max 2 per topic."""
    ranked = sorted(_load_weekly_digest_clusters(limit=28), key=lambda c: c.get("score") or 0, reverse=True)
    chosen: list[dict] = []
    seen_titles: list[str] = []
    topic_counts: dict[str, int] = {}
    for cluster in ranked:
        title = str(cluster.get("title") or "").strip()
        if not title or any(_similar(title, t) for t in seen_titles):
            continue
        topic = str(cluster.get("topic") or cluster.get("category") or "вести").strip()
        if topic_counts.get(topic, 0) >= 2:
            continue
        chosen.append(cluster)
        seen_titles.append(title)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        if len(chosen) >= limit:
            break
    return chosen


def _esc(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_morning_brief_html(clusters: list[dict], brief_date: datetime.datetime, unsubscribe_url: str) -> str:
    site = SITE
    rows = []
    for cluster in clusters:
        cid = str(cluster.get("cluster_id") or "").strip()
        url = f"{site}/mk/cluster/{cid}" if cid else site
        title = _esc(cluster.get("title"))
        summary = _esc(str(cluster.get("cluster_summary") or cluster.get("description") or "").strip())
        if len(summary) > 320:
            summary = summary[:317].rstrip() + "…"
        category = _esc(str(cluster.get("topic") or cluster.get("category") or "").strip())
        source = _esc(cluster.get("source"))
        count = int(cluster.get("source_count") or 1)
        rows.append(f"""
        <tr><td style="padding:0 0 26px 0;">
          <div style="font:600 11px/1.4 Arial,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#b3261e;">{category}</div>
          <a href="{url}" style="display:block;margin:6px 0 8px 0;font:700 21px/1.3 Georgia,serif;color:#111;text-decoration:none;">{title}</a>
          <div style="font:400 15px/1.55 Georgia,serif;color:#333;">{summary}</div>
          <div style="margin-top:8px;font:400 12px/1.4 Arial,sans-serif;color:#777;">{source} · {count} извори</div>
        </td></tr>""")

    body = "".join(rows) or '<tr><td style="font:400 15px/1.5 Georgia,serif;color:#555;">Денес нема доволно нови содржини за брифинг.</td></tr>'
    return f"""<!doctype html>
<html lang="mk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f1ea;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1ea;">
<tr><td align="center" style="padding:28px 14px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border:1px solid #e6e0d4;">
  <tr><td style="padding:28px 30px 10px 30px;border-bottom:2px solid #111;">
    <div style="font:900 30px/1 Georgia,serif;letter-spacing:.04em;color:#111;">ПРЕСЕК</div>
    <div style="margin-top:6px;font:600 12px/1.4 Arial,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:#b3261e;">Утрински брифинг · {_mk_date(brief_date)}</div>
  </td></tr>
  <tr><td style="padding:22px 30px 0 30px;font:400 15px/1.5 Georgia,serif;color:#555;">
    Најважните теми од последните денови, подредени по уреднички интензитет.
  </td></tr>
  <tr><td style="padding:24px 30px 4px 30px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{body}</table>
  </td></tr>
  <tr><td style="padding:8px 30px 26px 30px;border-top:1px solid #eee;font:400 12px/1.5 Arial,sans-serif;color:#888;">
    Го добивате овој брифинг бидејќи сте претплатени на утринскиот преглед на Пресек.<br>
    <a href="{unsubscribe_url}" style="color:#888;">Одјава</a> · <a href="{site}" style="color:#888;">presek.mk</a>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def build_morning_brief(
    brief_date: datetime.datetime | None = None, subscriber_email: str = ""
) -> tuple[str, str, list[dict]]:
    from core.signed_tokens import build_newsletter_unsubscribe_url

    brief_date = brief_date or datetime.datetime.now()
    clusters = pick_morning_clusters(limit=5)
    unsubscribe_url = build_newsletter_unsubscribe_url(SITE, subscriber_email, "mk")
    subject = f"Пресек — Утрински брифинг ({_mk_date(brief_date)})"
    html = render_morning_brief_html(clusters, brief_date, unsubscribe_url)
    return subject, html, clusters


def store_daily_briefing(clusters: list[dict], brief_date: datetime.datetime) -> None:
    """Persist a text digest so /archive/daily-briefing has content."""
    lines = [f"Утрински брифинг — {_mk_date(brief_date)}", ""]
    for cluster in clusters:
        lines.append(f"• {cluster.get('title')}")
        summary = str(cluster.get("cluster_summary") or cluster.get("description") or "").strip()
        if summary:
            lines.append(f"  {summary.splitlines()[0][:220]}")
    content = "\n".join(lines)
    try:
        db.execute(
            """INSERT INTO daily_briefings (date, content, created_at)
               VALUES (%s::date, %s, NOW())
               ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content""",
            (brief_date.date(), content),
            fetch=False,
        )
    except Exception as e:
        log.warning(f"[morning_brief] could not store daily briefing: {e}")


def send_morning_brief(to_address: str, lang: str = "mk") -> bool:
    subject, html, clusters = build_morning_brief(subscriber_email=to_address)
    if not clusters:
        log.warning("[morning_brief] no clusters to send")
        return False
    store_daily_briefing(clusters, datetime.datetime.now())
    ok = send_email(
        html, subject, os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASS", ""), to_address
    )
    log.info(f"[morning_brief] sent={ok} to={to_address} clusters={len(clusters)}")
    return ok
