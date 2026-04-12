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
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from collections import defaultdict

log = logging.getLogger(__name__)


import urllib.request
import json as _json

def send_newsletter_to_all_subscribers(days: int = 1) -> int:
    """Sends the daily HTML digest to all active newsletter subscribers."""
    import os
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        log.warning("Newsletter skipped: SMTP credentials not set.")
        return 0

    stories = fetch_top_stories(days=days)
    if not stories:
        log.info("Newsletter skipped: No stories found.")
        return 0

    now = datetime.now()
    start = now - timedelta(days=days)
    html = render_html(stories, start, now)
    subject = f"Пресек — Утрински Брифинг ({mk_date(now)})"

    try:
        from database import db_manager as db
        subscribers = db.execute("SELECT email FROM newsletter_subscribers WHERE is_active = TRUE")
        if not subscribers:
            log.info("Newsletter skipped: No active subscribers.")
            return 0

        sent_count = 0
        for sub in subscribers:
            if send_email(html, subject, smtp_user, smtp_pass, sub["email"]):
                sent_count += 1
        
        return sent_count
    except Exception as e:
        log.error(f"Newsletter distribution error: {e}")
        return 0

def send_ntfy_digest(stories_by_cat: dict, topic: str, period_days: int = 1) -> bool:
    """Send a compact daily digest to ntfy.sh."""
    if not topic:
        return False

    total = sum(len(v) for v in stories_by_cat.values())
    lines = [f"📰 ПРЕСЕК — Дневен преглед ({total} приказни)\n"]

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
        log.info(f"ntfy {'sent' if ok else 'failed'} to topic '{topic}'")
        return ok
    except Exception as e:
        log.warning(f"ntfy error: {e}")
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
        log.error(f"DB error: {e}")
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
    """Render the full HTML digest email with a premium editorial design."""

    # 1. Calculate Pulse Stats for the header
    total_stories = sum(len(v) for v in stories_by_cat.values())
    total_sources = len({a.get("source") for articles in stories_by_cat.values() for a in articles if a.get("source")})

    cat_blocks = ""
    for cat, articles in stories_by_cat.items():
        items = ""
        for a in articles:
            summary_html = ""
            if a.get("summary"):
                # Clean up summary: remove emoji markers and truncate
                clean = " ".join(
                    l for l in a["summary"].split("\n")
                    if l.strip() and not l.strip().startswith("#")
                )
                summary_html = f'<p style="margin:8px 0 0;color:#4a4a4a;font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif;font-size:14px;line-height:1.55;letter-spacing:-0.01em">{clean[:220]}…</p>'

            sources_badge = ""
            if a.get("source_count", 1) > 1:
                sources_badge = f'<span style="background:#b91c1c;color:#ffffff;font-family:sans-serif;font-size:10px;font-weight:bold;padding:2px 6px;text-transform:uppercase;letter-spacing:0.05em;border-radius:2px;margin-left:8px;vertical-align:middle">{a["source_count"]} извори</span>'

            items += f"""
            <tr>
              <td style="padding:20px 0;border-bottom:1px solid #e5e7eb">
                <p style="margin:0 0 6px;font-family:sans-serif;font-size:10px;font-weight:bold;color:#b91c1c;text-transform:uppercase;letter-spacing:0.1em">{a.get('source','') or 'ИЗВОР'}</p>
                <a href="{a['link']}" style="font-family:Georgia,\'Times New Roman\',serif;font-size:19px;font-weight:900;color:#111827;text-decoration:none;line-height:1.25;display:block">
                  {a['title']}
                </a>
                {summary_html}
                <div style="margin-top:12px">
                    <a href="{a['link']}" style="font-family:sans-serif;font-size:11px;font-weight:bold;color:#6b7280;text-decoration:none;text-transform:uppercase;letter-spacing:0.05em">Прочитај ја веста →</a>
                    {sources_badge}
                </div>
              </td>
            </tr>"""

        cat_blocks += f"""
        <tr>
          <td style="padding:48px 0 12px">
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td style="font-family:sans-serif;font-size:12px;font-weight:900;letter-spacing:0.2em;text-transform:uppercase;color:#111827;padding-bottom:8px">{cat}</td>
                </tr>
                <tr>
                    <td style="height:2px;background:#111827"></td>
                </tr>
            </table>
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
<body style="margin:0;padding:0;background-color:#f9fafb;font-family:Georgia,serif;-webkit-font-smoothing:antialiased">

  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f9fafb;padding:40px 20px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border:1px solid #e5e7eb;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1)">

        <!-- Masthead -->
        <tr>
          <td style="padding:40px 40px 30px;text-align:center;border-bottom:4px double #111827">
            <h1 style="margin:0;font-family:Georgia,\'Times New Roman\',serif;font-size:42px;font-weight:900;color:#111827;letter-spacing:-1.5px;text-transform:uppercase">
              ПРЕСЕК
            </h1>
            <p style="margin:10px 0 0;font-family:sans-serif;font-size:11px;font-weight:bold;letter-spacing:0.3em;text-transform:uppercase;color:#6b7280">
              Повеќе од вести
            </p>
          </td>
        </tr>

        <!-- Media Pulse Bar -->
        <tr>
          <td style="background-color:#111827;padding:12px 40px;text-align:center">
            <p style="margin:0;font-family:sans-serif;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">
              <span style="color:#ffffff">МЕДИУМСКИ ПУЛС:</span> &nbsp; {total_stories} теми во фокус &nbsp; • &nbsp; {total_sources} извори анализирани
            </p>
          </td>
        </tr>

        <!-- Edition Info -->
        <tr>
          <td style="padding:24px 40px 0;text-align:center">
            <p style="margin:0;font-family:sans-serif;font-size:12px;color:#6b7280;letter-spacing:0.05em">
              {period_str}
            </p>
          </td>
        </tr>

        <!-- Stories Content -->
        <tr>
          <td style="padding:0 40px 40px">
            <table width="100%" cellpadding="0" cellspacing="0">
              {cat_blocks}
            </table>
          </td>
        </tr>

        <!-- Bottom CTA -->
        <tr>
            <td style="padding:0 40px 40px;text-align:center">
                <a href="https://presek.live" style="display:inline-block;padding:14px 28px;background-color:#111827;color:#ffffff;font-family:sans-serif;font-size:12px;font-weight:bold;text-decoration:none;text-transform:uppercase;letter-spacing:0.15em;border-radius:2px">
                    Отвори го целосното издание
                </a>
            </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:30px 40px;text-align:center;background-color:#f3f4f6;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-family:sans-serif;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">
              Пресек · Македонски вести · Паметен агрегатор
            </p>
            <p style="margin:8px 0 0;font-family:sans-serif;font-size:10px;color:#9ca3af;line-height:1.5">
              Овој преглед е генериран автоматски од нашите алгоритми за групирање.<br>
              Доколку сакате да се одјавите, променете ги вашите <a href="https://presek.live/settings" style="color:#6b7280;text-decoration:underline">поставки</a>.
            </p>
          </td>
        </tr>

      </table>
      
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
        <tr>
            <td style="padding:20px 0;text-align:center">
                <p style="margin:0;font-family:sans-serif;font-size:10px;color:#9ca3af">
                    © {datetime.now().year} Пресек. Сите права се задржани.
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
               smtp_host: str = None,
               smtp_port: int = None) -> bool:
    """Send HTML email via SMTP."""
    import os
    host = smtp_host or os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(smtp_port or os.environ.get("SMTP_PORT", 587))
    from_addr = os.environ.get("EMAIL_FROM", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_address
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_address, msg.as_string())
        log.info(f"Email sent to {to_address} via {host}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        log.error(f"SMTP auth failure on {host} (permanent): {e}")
        return False
    except smtplib.SMTPRecipientsRefused as e:
        log.error(f"SMTP recipient refused {to_address} (permanent): {e}")
        return False
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError) as e:
        log.warning(f"SMTP transient error on {host} (retryable): {e}")
        return False
    except Exception as e:
        log.warning(f"SMTP error on {host}: {e}")
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
        log.info(f"Saved to {save_path}")

    if smtp_user and smtp_pass and to_address:
        subject = f"Пресек — Дневен преглед {mk_date(start)} — {mk_date(now)}"
        send_email(html, subject, smtp_user, smtp_pass, to_address)

    return html


def send_digest(days: int = 1) -> bool:
    """
    Entry point called by send_daily_digest_task in tasks.py.
    Sends digest via ntfy and optionally email if SMTP env vars are set.
    Returns True if at least one delivery succeeded.
    """
    import os
    ntfy_topic = os.environ.get("NTFY_TOPIC", "")
    smtp_user  = os.environ.get("SMTP_USER", "")
    smtp_pass  = os.environ.get("SMTP_PASS", "")
    to_address = os.environ.get("DIGEST_TO", "")

    stories = fetch_top_stories(days=days)
    if not stories:
        log.info("No stories found, skipping digest.")
        return False

    ok = False

    if ntfy_topic:
        ok = send_ntfy_digest(stories, ntfy_topic, period_days=days) or ok

    if smtp_user and smtp_pass and to_address:
        now   = datetime.now()
        start = now - timedelta(days=days)
        html  = render_html(stories, start, now)
        subject = f"Пресек — Дневен преглед {mk_date(start)} — {mk_date(now)}"
        ok = send_email(html, subject, smtp_user, smtp_pass, to_address) or ok

    return ok


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
