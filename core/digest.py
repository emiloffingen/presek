"""
digest.py — Weekly HTML digest generator for Presek
Generates a localized styled HTML email digest of the top stories.
Can send via Gmail SMTP or save to file.
"""

import argparse
import logging
import os
import smtplib
import ssl
from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote

import core.database as database

log = logging.getLogger(__name__)

# ── Localization Configuration ────────────────────────────────────────────────

LOCALES = {
    "sr": {
        "months": [
            "januar",
            "februar",
            "mart",
            "april",
            "maj",
            "jun",
            "jul",
            "avgust",
            "septembar",
            "oktobar",
            "novembar",
            "decembar",
        ],
        "days": ["Ponedeljak", "Utorak", "Sreda", "Cetvrtak", "Petak", "Subota", "Nedelja"],
        "default_cat": "Srbija",
        "subject": "Presek — Jutarnji Brifing",
        "masthead": "PRESEK",
        "tagline": "Mediumska transparentnost i javen uvid",
        "pulse": "MEDIUMSKI PULS",
        "temi": "temi vo fokus",
        "izvori": "izvori analizirani",
        "cta": "Otvori ga celosnoto izdanie",
        "footer_tagline": "Presek · Mediumska transparentnost · Sistemska sinteza",
        "footer_disclaimer": "Ovoj pregled e sistemski sintetiziran preku nasiot redakciski algoritam.",
        "unsubscribe": "Dokolku sakate da se odjavite, kliknete",
        "here": "ovde",
        "rights": "Site prava se zadrzani",
        "url": "https://presek.live",
        "lang_code": "sr",
        "country_code": "RS",
        "read_more": "Procitaj me vesta →",
        "format_source": lambda c: "1 izvor" if c == 1 else f"{c} izvori",
    },
    "mk": {
        "months": [
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
        ],
        "days": ["Понеделник", "Вторник", "Среда", "Четврток", "Петок", "Сабота", "Недела"],
        "default_cat": "Македонија",
        "subject": "Пресек — Утрински брифинг",
        "masthead": "ПРЕСЕК",
        "tagline": "Медиумска транспарентност и јавен увид",
        "pulse": "МЕДИУМСКИ ПУЛС",
        "temi": "теми во фокус",
        "izvori": "извори анализирани",
        "cta": "Отвори го целосното издание",
        "footer_tagline": "Пресек · Медиумска транспарентност · Системска синтеза",
        "footer_disclaimer": "Овој преглед е системски синтетизиран преку нашиот редакциски алгоритам.",
        "unsubscribe": "Доколку сакате да се одјавите, кликнете",
        "here": "овде",
        "rights": "Сите права се задржани",
        "url": "https://presek.mk",
        "lang_code": "mk",
        "country_code": "MK",
        "read_more": "Прочитај ја веста →",
        "format_source": lambda c: "1 извор" if c == 1 else f"{c} извори",
    },
}

# Backward compatibility aliases for tests
SR_MONTHS = LOCALES["sr"]["months"]
SR_DAYS = LOCALES["sr"]["days"]


def format_date(dt: datetime, locale: str = "sr") -> str:
    conf = LOCALES.get(locale, LOCALES["sr"])
    return f"{conf['days'][dt.weekday()]}, {dt.day} {conf['months'][dt.month-1]} {dt.year}"


def sr_date(dt: datetime) -> str:
    return format_date(dt, "sr")


def mk_date(dt: datetime) -> str:
    return format_date(dt, "mk")


def format_sources(count: int, locale: str = "sr") -> str:
    conf = LOCALES.get(locale, LOCALES["sr"])
    return conf["format_source"](count)


# ── Logic ───────────────────────────────────────────────────────────────────


def fetch_top_stories(days: int = 7, per_category: int = 3, locale: str = "sr") -> dict[str, list[dict]]:
    """
    Fetch top articles from the last N days, grouped by category.
    Filtered by locale (country).
    """
    conf = LOCALES.get(locale, LOCALES["sr"])
    country = conf["country_code"]

    try:
        with database.get_db() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.title, a.link, a.source, a.category, a.summary, a.cluster_id, a.created_at, a.country, a.is_global, COALESCE(s.credibility, 0.5) as credibility
                FROM articles a
                LEFT JOIN sources s ON a.source = s.name
                WHERE a.created_at >= NOW() - (INTERVAL '1 day' * %s)
                  AND (a.country = %s OR a.is_global = TRUE)
                ORDER BY a.created_at DESC
            """,
                (days, country),
            ).fetchall()
    except Exception as e:
        log.error(f"DB error in fetch_top_stories: {e}")
        return {}

    # Group by cluster
    clusters: dict[str, list] = defaultdict(list)
    for row in rows:
        clusters[row["cluster_id"]].append(dict(row))

    # Sort each cluster's articles by credibility desc, created_at desc
    # This picks the highest credibility article as cluster[0]!
    for cid in clusters:
        clusters[cid].sort(key=lambda x: (float(x.get("credibility") or 0.5), x["created_at"]), reverse=True)

    # Sort clusters by size desc
    sorted_clusters = sorted(clusters.values(), key=len, reverse=True)

    # Group top clusters by category
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for cluster in sorted_clusters:
        main = cluster[0]
        cat = main.get("category") or conf["default_cat"]
        if len(by_cat[cat]) < per_category:
            main["source_count"] = len(cluster)
            by_cat[cat].append(main)

    # Fetch synthesis details (synthetic headlines/summaries) for selected clusters
    top_cluster_ids = [main["cluster_id"] for cat_list in by_cat.values() for main in cat_list]
    if top_cluster_ids:
        try:
            with database.get_db() as conn:
                summary_rows = conn.execute(
                    """
                    SELECT cluster_id, summary, synthetic_headline, synthetic_standfirst
                    FROM cluster_summaries
                    WHERE cluster_id = ANY(%s) AND lang = %s
                """,
                    (top_cluster_ids, locale),
                ).fetchall()
                
                summaries_by_cid = {r["cluster_id"]: r for r in summary_rows}
                
                # Enrich selected articles with synthesis metadata
                for cat in by_cat:
                    for main in by_cat[cat]:
                        cid = main["cluster_id"]
                        if cid in summaries_by_cid:
                            s = summaries_by_cid[cid]
                            if s.get("summary"):
                                main["synthesis_summary"] = s["summary"]
                            if s.get("synthetic_headline"):
                                main["synthetic_headline"] = s["synthetic_headline"]
                            if s.get("synthetic_standfirst"):
                                main["synthetic_standfirst"] = s["synthetic_standfirst"]
        except Exception as e:
            log.error(f"DB error fetching cluster summaries for digest: {e}")

    return dict(by_cat)


def render_html(
    stories_by_cat: dict[str, list[dict]], period_start: datetime, period_end: datetime, locale: str = "sr"
) -> str:
    """Render the full HTML digest email with localized strings."""
    conf = LOCALES.get(locale, LOCALES["sr"])

    total_stories = sum(len(v) for v in stories_by_cat.values())
    total_sources = len({a.get("source") for articles in stories_by_cat.values() for a in articles if a.get("source")})

    cat_blocks = ""
    for cat, articles in stories_by_cat.items():
        items = ""
        for a in articles:
            headline = a.get("synthetic_headline") or a.get("title") or ""
            summary_text = a.get("synthesis_summary") or a.get("summary") or ""
            summary_html = ""
            if summary_text:
                clean = " ".join(
                    line for line in summary_text.split("\n") if line.strip() and not line.strip().startswith("#")
                )
                summary_html = f"<p style=\"margin:8px 0 0;color:#4a4a4a;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:14px;line-height:1.55;letter-spacing:-0.01em\">{clean[:220]}…</p>"

            sources_badge = ""
            if a.get("source_count", 1) > 1:
                sources_badge = f'<span style="background:#b91c1c;color:#ffffff;font-family:sans-serif;font-size:10px;font-weight:bold;padding:2px 6px;text-transform:uppercase;letter-spacing:0.05em;border-radius:2px;margin-left:8px;vertical-align:middle">{format_sources(a["source_count"], locale)}</span>'

            items += f"""
            <tr>
              <td style="padding:20px 0;border-bottom:1px solid #e5e7eb">
                <p style="margin:0 0 6px;font-family:sans-serif;font-size:10px;font-weight:bold;color:#b91c1c;text-transform:uppercase;letter-spacing:0.1em">{a.get('source','') or 'izvor'}</p>
                <a href="{a['link']}" style="font-family:Georgia,\'Times New Roman\',serif;font-size:19px;font-weight:900;color:#111827;text-decoration:none;line-height:1.25;display:block">
                  {headline}
                </a>
                {summary_html}
                <div style="margin-top:12px">
                    <a href="{a['link']}" style="font-family:sans-serif;font-size:11px;font-weight:bold;color:#6b7280;text-decoration:none;text-transform:uppercase;letter-spacing:0.05em">{conf['read_more']}</a>
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

    period_str = f"{format_date(period_start, locale)} — {format_date(period_end, locale)}"

    html = f"""<!DOCTYPE html>
<html lang="{conf['lang_code']}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{conf['masthead']} — {conf['subject']}</title>
</head>
<body style="margin:0;padding:0;background-color:#f9fafb;font-family:Georgia,serif;-webkit-font-smoothing:antialiased">

  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f9fafb;padding:40px 20px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border:1px solid #e5e7eb;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1)">

        <!-- Masthead -->
        <tr>
          <td style="padding:40px 40px 30px;text-align:center;border-bottom:4px double #111827">
            <h1 style="margin:0;font-family:Georgia,\'Times New Roman\',serif;font-size:42px;font-weight:900;color:#111827;letter-spacing:-1.5px;text-transform:uppercase">
              {conf['masthead']}
            </h1>
            <p style="margin:10px 0 0;font-family:sans-serif;font-size:11px;font-weight:bold;letter-spacing:0.3em;text-transform:uppercase;color:#6b7280">
              {conf['tagline']}
            </p>
          </td>
        </tr>

        <!-- Media Pulse Bar -->
        <tr>
          <td style="background-color:#111827;padding:12px 40px;text-align:center">
            <p style="margin:0;font-family:sans-serif;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">
              <span style="color:#ffffff">{conf['pulse']}:</span> &nbsp; {total_stories} {conf['temi']} &nbsp; • &nbsp; {total_sources} {conf['izvori']}
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
                <a href="{conf['url']}" style="display:inline-block;padding:14px 28px;background-color:#111827;color:#ffffff;font-family:sans-serif;font-size:12px;font-weight:bold;text-decoration:none;text-transform:uppercase;letter-spacing:0.15em;border-radius:2px">
                    {conf['cta']}
                </a>
            </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:30px 40px;text-align:center;background-color:#f3f4f6;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-family:sans-serif;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">
              {conf['footer_tagline']}
            </p>
            <p style="margin:8px 0 0;font-family:sans-serif;font-size:10px;color:#9ca3af;line-height:1.5">
              {conf['footer_disclaimer']}<br>
              {conf['unsubscribe']} <a href="{{UNSUBSCRIBE_URL}}" style="color:#6b7280;text-decoration:underline">{conf['here']}</a>.
            </p>
          </td>
        </tr>

      </table>

      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
        <tr>
            <td style="padding:20px 0;text-align:center">
                <p style="margin:0;font-family:sans-serif;font-size:10px;color:#9ca3af">
                    © {datetime.now().year} Presek. {conf['rights']}.
                </p>
            </td>
        </tr>
      </table>
    </td></tr>
  </table>

</body>
</html>"""

    return html.replace("{{UNSUBSCRIBE_URL}}", f"{conf['url']}/settings")


def send_newsletter_to_all_subscribers(days: int = 1) -> int:
    """Sends localized daily HTML digests to all active newsletter subscribers."""
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        log.warning("Newsletter skipped: SMTP credentials not set.")
        return 0

    from core.database import db_manager as db

    # Pre-generate digests for each locale to avoid redundant DB calls and rendering
    digests = {}
    now = datetime.now()
    start = now - timedelta(days=days)

    for loc in LOCALES:
        stories = fetch_top_stories(days=days, locale=loc)
        if stories:
            digests[loc] = {
                "html": render_html(stories, start, now, locale=loc),
                "subject": f"{LOCALES[loc]['subject']} ({format_date(now, loc)})",
            }

    try:
        subscribers = db.execute("SELECT email, locale FROM subscribers WHERE is_active = TRUE")
        if not subscribers:
            log.info("Newsletter skipped: No active subscribers.")
            return 0

        sent_count = 0
        for sub in subscribers:
            user_email = sub["email"]
            loc = sub.get("locale") or "sr"  # fallback
            if loc not in digests:
                continue  # Skip if no stories for this locale

            digest = digests[loc]
            unsubscribe_url = (
                f"{LOCALES[loc]['url']}/api/newsletter/unsubscribe"
                f"?email={quote(user_email)}&lang={loc}"
            )
            personalized_html = digest["html"].replace("{{UNSUBSCRIBE_URL}}", unsubscribe_url)

            if send_email(personalized_html, digest["subject"], smtp_user, smtp_pass, user_email):
                sent_count += 1

        return sent_count
    except Exception as e:
        log.error(f"Newsletter distribution error: {e}")
        return 0


def send_email(
    html: str,
    subject: str,
    smtp_user: str,
    smtp_pass: str,
    to_address: str,
    smtp_host: str = None,
    smtp_port: int = None,
) -> bool:
    """Send HTML email via SMTP."""
    host = smtp_host or os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(smtp_port or os.environ.get("SMTP_PORT", 587))
    from_addr = os.environ.get("EMAIL_FROM", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_address
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
    except Exception as e:
        log.warning(f"SMTP error on {host} to {to_address}: {e}")
        return False


def send_digest(days: int = 1) -> bool:
    """
    Entry point for automated daily tasks.
    """
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    to_address = os.environ.get("DIGEST_TO", "")  # Admin recipient

    ok = False

    if smtp_user and smtp_pass and to_address:
        # Send admin digests
        for loc in ["mk", "sr"]:
            stories = fetch_top_stories(days=days, locale=loc)
            if stories:
                now = datetime.now()
                start = now - timedelta(days=days)
                html = render_html(stories, start, now, locale=loc)
                subject = f"Presek [{loc.upper()}] — Dneven pregled {format_date(start, loc)}"
                ok = send_email(html, subject, smtp_user, smtp_pass, to_address) or ok

    return ok


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Presek digest generator")
    parser.add_argument("--days", default=1, type=int, help="Days to look back")
    parser.add_argument("--save", default=None, help="Save HTML to file")
    parser.add_argument("--to", default=None, help="Recipient email")
    parser.add_argument("--locale", default="sr", choices=["sr", "mk"], help="Locale")
    args = parser.parse_args()

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    now = datetime.now()
    start = now - timedelta(days=args.days)
    stories = fetch_top_stories(days=args.days, locale=args.locale)
    html = render_html(stories, start, now, locale=args.locale)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved to {args.save}")

    if smtp_user and smtp_pass and args.to:
        subject = f"Presek — Dneven pregled {format_date(start, args.locale)}"
        send_email(html, subject, smtp_user, smtp_pass, args.to)
        print(f"Sent to {args.to}")
