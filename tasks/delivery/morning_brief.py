"""Morning briefing email for the MK branch.

Curates the day's top clusters (their syntheses already exist), optionally adds
an AI-written editorial intro (DAILY_BRIEF_SYSTEM_PROMPT_MK), stores the full
brief in `daily_briefings`, and delivers the email via SMTP.
"""

from __future__ import annotations

import datetime
import os
import re

from core.database import db_manager as db
from tasks.utils import log, send_email

from .email import _load_weekly_digest_clusters

SITE = str(os.environ.get("PUBLIC_SITE_URL") or "https://presek.mk").rstrip("/")

_MONTHS_MK = [
    "јануари",
    "февруари",
    "март",
    "април",
    "мај",
    "јуни",
    "јули",
    "август",
    "септември",
    "октомври",
    "ноември",
    "декември",
]


def _mk_date(dt: datetime.datetime) -> str:
    return f"{dt.day} {_MONTHS_MK[dt.month - 1]} {dt.year}"


def _similar(a: str, b: str) -> bool:
    a, b = a.lower().split(), b.lower().split()
    if not a or not b:
        return False
    union = set(a) | set(b)
    return bool(union) and len(set(a) & set(b)) / len(union) >= 0.72


def _esc(text: str) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


def _strip_md(line: str) -> str:
    line = re.sub(r"^#+\s*", "", line)
    line = line.replace("**", "").replace("*", "")
    line = re.sub(r"\[\[([^\]]+)\]\]", r"\1", line)
    return line.strip()


def extract_intro(brief_text: str, max_chars: int = 560) -> str:
    """Pull the 'Големата Слика' section (or first paragraphs) as plain text."""
    if not brief_text:
        return ""
    match = re.search(r"##\s*Големата\s+Слика\s*(.*?)(?=\n##\s|\Z)", brief_text, flags=re.S)
    section = match.group(1) if match else brief_text
    paragraphs = []
    for para in section.split("\n\n"):
        clean = _strip_md(para.replace("\n", " "))
        if len(clean) >= 40:
            paragraphs.append(clean)
        if len(paragraphs) >= 2 or sum(len(p) for p in paragraphs) >= max_chars:
            break
    return " ".join(paragraphs)[:max_chars].strip()


def generate_brief_text(clusters: list[dict]) -> str | None:
    """Full daily brief via the AI cascade (MK). None when unavailable."""
    try:
        from core.ai_engine import sync_call_ai
        from core.prompts import DAILY_BRIEF_SYSTEM_PROMPT_MK

        context = "\n".join(
            f"- [{c.get('cluster_id')}] {c.get('title')}: "
            f"{str(c.get('cluster_summary') or c.get('description') or '')[:280]}"
            for c in clusters
        )
        prompt = "Контекст (најважни кластери денес):\n" + context + "\n\nНапиши го дневниот брифинг според правилата."
        result, provider = sync_call_ai(
            prompt, DAILY_BRIEF_SYSTEM_PROMPT_MK, task_type="daily_brief", max_tokens=1000, lang="mk"
        )
        if result and str(result).strip():
            log.info(f"[morning_brief] AI brief via {provider} ({len(str(result))} chars)")
            return str(result).strip()
    except Exception as e:
        log.warning(f"[morning_brief] AI brief failed: {e}")
    return None


def _fallback_text(clusters: list[dict], brief_date: datetime.datetime) -> str:
    lines = [f"# Утрински брифинг — {_mk_date(brief_date)}", ""]
    for cluster in clusters:
        lines.append(f"### {cluster.get('title')} [[{cluster.get('cluster_id')}]]")
        summary = str(cluster.get("cluster_summary") or cluster.get("description") or "").strip()
        if summary:
            lines.append(f"* **Што се случи:** {summary.splitlines()[0][:220]}")
        lines.append("")
    return "\n".join(lines).strip()


def load_today_briefing() -> str | None:
    try:
        row = db.execute_one("SELECT content FROM daily_briefings WHERE date = CURRENT_DATE")
        return (row or {}).get("content")
    except Exception as e:
        log.warning(f"[morning_brief] could not load today's briefing: {e}")
        return None


def store_daily_briefing(brief_date: datetime.datetime, content: str) -> None:
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


def prepare_and_store_brief(brief_date: datetime.datetime | None = None) -> int:
    """Generate (AI, else fallback) + store today's brief. Returns cluster count."""
    brief_date = brief_date or datetime.datetime.now()
    clusters = pick_morning_clusters(limit=5)
    if not clusters:
        return 0
    text = generate_brief_text(clusters) or _fallback_text(clusters, brief_date)
    store_daily_briefing(brief_date, text)
    return len(clusters)


def _intro_html(intro: str) -> str:
    if not intro:
        return ""
    return (
        '<tr><td style="padding:18px 30px 0 30px;font:400 16px/1.6 Georgia,serif;color:#222;">'
        f'<p style="margin:0;">{_esc(intro)}</p></td></tr>'
    )


def render_morning_brief_html(
    clusters: list[dict], brief_date: datetime.datetime, unsubscribe_url: str, intro: str = ""
) -> str:
    site = SITE
    rows = []
    for cluster in clusters:
        cid = str(cluster.get("cluster_id") or "").strip()
        url = f"{site}/mk/cluster/{cid}" if cid else site
        title = _esc(cluster.get("title"))
        # Truncate before escaping so the cut never splits an HTML entity.
        summary = str(cluster.get("cluster_summary") or cluster.get("description") or "").strip()
        if len(summary) > 320:
            summary = summary[:317].rstrip() + "…"
        summary = _esc(summary)
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

    body = (
        "".join(rows)
        or '<tr><td style="font:400 15px/1.5 Georgia,serif;color:#555;">Денес нема доволно нови содржини за брифинг.</td></tr>'
    )
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
  {_intro_html(intro)}
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


def render_breaking_email(cluster: dict, unsubscribe_url: str = "") -> str:
    cid = str(cluster.get("cluster_id") or "").strip()
    url = f"{SITE}/mk/cluster/{cid}" if cid else SITE
    title = _esc(cluster.get("title") or cluster.get("synthetic_headline"))
    summary = _esc(str(cluster.get("summary") or cluster.get("cluster_summary") or "").strip()[:400])
    unsub = f'<a href="{unsubscribe_url}" style="color:#888;">Одјава</a>' if unsubscribe_url else ""
    return f"""<!doctype html><html lang="mk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f1ea;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 14px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#fff;border:1px solid #e6e0d4;">
<tr><td style="padding:22px 28px 6px 28px;">
  <div style="font:700 12px/1.4 Arial,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:#b3261e;">Итна вест</div>
  <a href="{url}" style="display:block;margin:8px 0;font:700 22px/1.3 Georgia,serif;color:#111;text-decoration:none;">{title}</a>
  <div style="font:400 15px/1.55 Georgia,serif;color:#333;">{summary}</div>
  <div style="margin:16px 0 4px 0;"><a href="{url}" style="font:600 13px/1 Arial,sans-serif;color:#b3261e;text-decoration:none;">Прочитај повеќе →</a></div>
</td></tr>
<tr><td style="padding:14px 28px 22px 28px;border-top:1px solid #eee;font:12px/1.5 Arial,sans-serif;color:#888;">Пресек · {unsub}</td></tr>
</table></td></tr></table></body></html>"""


def build_morning_brief(
    brief_date: datetime.datetime | None = None,
    subscriber_email: str = "",
    clusters: list[dict] | None = None,
    intro: str = "",
) -> tuple[str, str, list[dict]]:
    from core.signed_tokens import build_newsletter_unsubscribe_url

    brief_date = brief_date or datetime.datetime.now()
    clusters = clusters if clusters is not None else pick_morning_clusters(limit=5)
    unsubscribe_url = build_newsletter_unsubscribe_url(SITE, subscriber_email, "mk")
    subject = f"Пресек — Утрински брифинг ({_mk_date(brief_date)})"
    html = render_morning_brief_html(clusters, brief_date, unsubscribe_url, intro)
    return subject, html, clusters


def send_morning_brief_to(targets: list[str], brief_date: datetime.datetime | None = None) -> list[str]:
    """Send the morning brief to each email address. Returns delivered targets."""
    brief_date = brief_date or datetime.datetime.now()
    clusters = pick_morning_clusters(limit=5)
    if not clusters:
        log.warning("[morning_brief] no clusters to send")
        return []
    text = load_today_briefing() or generate_brief_text(clusters) or _fallback_text(clusters, brief_date)
    if not load_today_briefing():
        store_daily_briefing(brief_date, text)
    intro = extract_intro(text)
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    delivered: list[str] = []
    for target in dict.fromkeys(t.strip() for t in targets if t and t.strip()):
        subject, html, _ = build_morning_brief(brief_date, target, clusters, intro)
        if send_email(html, subject, smtp_user, smtp_pass, target):
            delivered.append(target)
    log.info(f"[morning_brief] delivered {len(delivered)}/{len(targets)} briefings")
    return delivered


def send_morning_brief(to_address: str, lang: str = "mk") -> bool:
    return to_address in send_morning_brief_to([to_address])
