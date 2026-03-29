"""
digest.py — Weekly HTML digest generator for Пресек
Generates a styled HTML email digest of the top stories.
Can send via Gmail SMTP or save to file.

Usage:
    python3 digest.py --save           # saves digest.html
    python3 digest.py --email you@gmail.com --password yourpass --to recipient@email.com

Cron (every Monday 08:00):
    0 8 * * 1 cd /path/to/timeai && python3 digest.py --email ... >> digest.log 2>&1
"""

import database
import argparse
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from collections import defaultdict


import urllib.request
import json as _json

def send_ntfy_digest(stories_by_cat: dict, topic: str, period_days: int = 1) -> bool:
    """Send a compact daily digest to ntfy.sh."""
    if not topic:
        return False

    total = sum(len(v) for v in stories_by_cat.values())
    lines = [f"📰 Пресек — Дневен преглед ({total} приказни)\n"]

    CAT_ORDER = ['Македонија','Политика','Спорт','Хроника','Економија','Балкан','Свет','Дијаспора']
    cats = [c for c in CAT_ORDER if c in stories_by_cat] +            [c for c in stories_by_cat if c not in CAT_ORDER]

    for cat in cats[:6]:   # max 6 categories in notification
        articles = stories_by_cat[cat]
        lines.append(f"▌ {cat}")
        for a in articles[:2]:   # max 2 per category
            src_count = a.get("source_count", 1)
            badge = f" [{src_count} извори]" if src_count > 1 else ""
            lines.append(f"  • {a['title'][:80]}{badge}")
        lines.append("")

    body = "\n".join(lines).strip()

    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={
                "Title": "Пресек — Дневен преглед",
                "Priority": "default",
                "Tags": "newspaper,macedonia",
                "Content-Type": "text/plain; charset=utf-8",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            ok = r.status == 200
        print(f"[digest] ntfy {'sent' if ok else 'failed'} to topic '{topic}'")
        return ok
    except Exception as e:
        print(f"[digest] ntfy error: {e}")
        return False


MK_MONTHS = ["јануари","февруари","март","април","мај","јуни",
             "јули","август","септември","октомври","ноември","декември"]

MK_DAYS = ["Понеделник","Вторник","Среда","Четврток","Петок","Сабота","Недела"]


def mk_date(dt: datetime) -> str:
    return f"{MK_DAYS[dt.weekday()]}, {dt.day} {MK_MONTHS[dt.month-1]} {dt.year}"


def fetch_top_stories(days: int = 7,
                      per_category: int = 3) -> dict[str, list[dict]]:
    """
    Fetch top articles from the last N days, grouped by category.
    Selects the earliest article per cluster (= most-sourced story).
    """
    try:
        conn = database.get_db()
        # In PostgreSQL, we can use INTERVAL 'N days' or (interval '1 day' * N)
        rows = conn.execute("""
            SELECT id, title, link, source, category, summary, cluster_id, created_at
            FROM articles
            WHERE created_at >= NOW() - (INTERVAL '1 day' * %s)
            ORDER BY created_at DESC
        """, (days,)).fetchall()
        conn.close()
    except Exception as e:
        print(f"[digest] DB error: {e}")
        return {}

    # Group by cluster, pick representative (first/most-cited)
    clusters: dict[str, list] = defaultdict(list)
    for row in rows:
        clusters[row["cluster_id"]].append(dict(row))

    # Sort clusters by size desc (most-covered stories first)
    sorted_clusters = sorted(clusters.values(), key=len, reverse=True)

    # Group top clusters by category
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for cluster in sorted_clusters:
        main = cluster[0]
        cat  = main.get("category") or "Македонија"
        if len(by_cat[cat]) < per_category:
            main["source_count"] = len(cluster)
            by_cat[cat].append(main)

    return dict(by_cat)


def render_html(stories_by_cat: dict[str, list[dict]],
                period_start: datetime,
                period_end: datetime) -> str:
    """Render the full HTML digest email."""

    cat_blocks = ""
    for cat, articles in stories_by_cat.items():
        items = ""
        for a in articles:
            summary_html = ""
            if a.get("summary"):
                # Strip emoji lines for email cleanliness
                clean = " ".join(
                    l for l in a["summary"].split("\n")
                    if l.strip() and not l.strip().startswith("#")
                )
                summary_html = f'<p style="margin:6px 0 0;color:#555;font-size:13px;line-height:1.5">{clean[:200]}…</p>'

            sources_badge = ""
            if a.get("source_count", 1) > 1:
                sources_badge = f'<span style="background:#c0392b;color:#fff;font-size:10px;padding:2px 6px;border-radius:2px;margin-left:8px">{a["source_count"]} извори</span>'

            items += f"""
            <tr>
              <td style="padding:14px 0;border-bottom:1px solid #e8e0d0">
                <a href="{a['link']}" style="font-family:Georgia,serif;font-size:16px;font-weight:bold;color:#0d0d0d;text-decoration:none;line-height:1.3">
                  {a['title']}
                </a>{sources_badge}
                <p style="margin:4px 0 0;font-family:monospace;font-size:11px;color:#999">
                  {a.get('source','') or ''}
                </p>
                {summary_html}
              </td>
            </tr>"""

        cat_blocks += f"""
        <tr>
          <td style="padding:24px 0 8px">
            <p style="margin:0;font-family:monospace;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#c0392b">{cat}</p>
            <hr style="border:none;border-top:2px solid #0d0d0d;margin:6px 0 0">
          </td>
        </tr>
        {items}"""

    period_str = f"{mk_date(period_start)} — {mk_date(period_end)}"

    return f"""<!DOCTYPE html>
<html lang="mk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Пресек — Дневен преглед</title>
</head>
<body style="margin:0;padding:0;background:#f5f0e8;font-family:Georgia,serif">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f0e8;padding:32px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

        <!-- Header -->
        <tr>
          <td style="background:#0d0d0d;padding:28px 32px;text-align:center">
            <h1 style="margin:0;font-family:Georgia,serif;font-size:36px;font-weight:900;color:#f5f0e8;letter-spacing:-1px">
              ПРЕСЕК
            </h1>
            <p style="margin:8px 0 0;font-family:monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#7a7068">
              Дневен преглед · {period_str}
            </p>
          </td>
        </tr>

        <!-- Intro -->
        <tr>
          <td style="background:#ece5d8;padding:16px 32px;border-bottom:2px solid #0d0d0d">
            <p style="margin:0;font-size:13px;color:#555;line-height:1.6">
              Најважните приказни од македонските медиуми оваа недела, групирани и резимирани со вештачка интелигенција.
            </p>
          </td>
        </tr>

        <!-- Stories -->
        <tr>
          <td style="background:#fff;padding:8px 32px 24px">
            <table width="100%" cellpadding="0" cellspacing="0">
              {cat_blocks}
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 32px;text-align:center">
            <p style="margin:0;font-family:monospace;font-size:10px;color:#999;letter-spacing:1px">
              Пресек · Македонски вести со AI · Агрегатор
            </p>
            <p style="margin:6px 0 0;font-family:monospace;font-size:10px;color:#bbb">
              Генерирано автоматски · {datetime.now().strftime('%d.%m.%Y %H:%M')}
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>

</body>
</html>"""


def send_email(html: str, subject: str,
               smtp_user: str, smtp_pass: str,
               to_address: str,
               smtp_host: str = "smtp.gmail.com",
               smtp_port: int = 587) -> bool:
    """Send HTML email via SMTP (Gmail by default)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = to_address
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_address, msg.as_string())
        print(f"[digest] Email sent to {to_address}")
        return True
    except Exception as e:
        print(f"[digest] SMTP error: {e}")
        return False


def generate_digest(days: int = 1,
                    save_path: str | None = None,
                    smtp_user: str | None = None, smtp_pass: str | None = None,
                    to_address: str | None = None,
                    ntfy_topic: str | None = None) -> str:
    """Main entry point. Returns the rendered HTML."""
    now    = datetime.now()
    start  = now - timedelta(days=days)

    stories = fetch_top_stories(days=days)
    html    = render_html(stories, start, now)

    if save_path:
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[digest] Saved to {save_path}")

    if smtp_user and smtp_pass and to_address:
        subject = f"Пресек — Дневен преглед {mk_date(start)} — {mk_date(now)}"
        send_email(html, subject, smtp_user, smtp_pass, to_address)

    return html


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Пресек digest generator")
    parser.add_argument("--days",     default=7, type=int,    help="Days to look back")
    parser.add_argument("--save",     default="digest.html",  help="Save HTML to file")
    parser.add_argument("--email",    default=None,           help="Gmail address (sender)")
    parser.add_argument("--password", default=None,           help="Gmail app password")
    parser.add_argument("--to",       default=None,           help="Recipient email")
    parser.add_argument("--ntfy",     default=None,           help="ntfy.sh topic for push digest")
    args = parser.parse_args()

    generate_digest(
        days=args.days,
        save_path=args.save,
        smtp_user=args.email,
        smtp_pass=args.password,
        to_address=args.to,
        ntfy_topic=args.ntfy,
    )
