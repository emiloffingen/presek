"""
digest.py — Weekly HTML digest generator for Presek
Generates a localized styled HTML email digest of the top stories.
Can send via Gmail SMTP or save to file.
"""

import argparse
import html
import json
import logging
import os
import re
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
        "briefing_edition": "Urednicki brifing",
        "big_picture": "Velika slika",
        "open_briefing": "Procitaj pun brifing",
        "listen_audio": "Slusaj audio verziju",
        "also_today": "Jos iz dana",
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
        "briefing_edition": "Уреднички брифинг",
        "big_picture": "Големата слика",
        "open_briefing": "Прочитај го целиот брифинг",
        "listen_audio": "Слушај ја аудио верзијата",
        "also_today": "Уште од денот",
    },
}

_BULLET_RE = re.compile(r"^[-*•]\s+(.+)$")
_BIG_PICTURE_MARKERS = ("velika slika", "golemata slika")

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


def _escape(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def fetch_daily_briefing(locale: str = "sr", days: int = 1) -> dict | None:
    """Load the latest daily editorial briefing for a locale."""
    try:
        with database.get_db() as conn:
            row = conn.execute(
                """
                SELECT date, content, metadata
                FROM daily_briefings
                WHERE lang = %s
                  AND date >= CURRENT_DATE - make_interval(days => %s)
                ORDER BY date DESC
                LIMIT 1
                """,
                (locale, max(days - 1, 0)),
            ).fetchone()
    except Exception as exc:
        log.error(f"DB error in fetch_daily_briefing ({locale}): {exc}")
        return None

    if not row or not row.get("content"):
        return None

    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}

    briefing_date = row.get("date")
    if hasattr(briefing_date, "isoformat"):
        briefing_date = briefing_date.isoformat()

    return {
        "date": briefing_date,
        "content": row["content"],
        "metadata": metadata,
    }


def parse_briefing_for_email(content: str, metadata: dict | None = None) -> dict:
    """Extract headline, big-picture excerpt, and bullet highlights from briefing markdown."""
    metadata = metadata or {}
    title = ""
    big_picture = ""
    bullets: list[str] = []
    in_big_picture = False

    for raw_line in str(content or "").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip().strip("*")
            continue

        if stripped.startswith("##"):
            section_label = stripped.lstrip("#").strip().casefold()
            normalized = (
                section_label.replace("š", "s")
                .replace("č", "c")
                .replace("ć", "c")
                .replace("ž", "z")
            )
            in_big_picture = any(marker in normalized for marker in _BIG_PICTURE_MARKERS)
            continue

        bullet_match = _BULLET_RE.match(stripped)
        if bullet_match:
            bullet_text = bullet_match.group(1).strip().replace("**", "")
            if len(bullet_text) >= 12 and bullet_text not in bullets:
                bullets.append(bullet_text)
            continue

        if in_big_picture and not big_picture:
            big_picture = stripped.replace("**", "")
            if len(big_picture) > 520:
                big_picture = big_picture[:517].rstrip() + "..."

    narratives = metadata.get("key_narratives") or []
    if not bullets:
        for item in narratives[:4]:
            text = str((item or {}).get("text") or "").strip()
            if len(text) >= 12:
                bullets.append(text)

    return {
        "title": title,
        "big_picture": big_picture,
        "bullets": bullets[:4],
        "narratives": narratives[:3],
    }


def _render_story_items(stories_by_cat: dict[str, list[dict]], locale: str, limit: int = 3) -> str:
    conf = LOCALES.get(locale, LOCALES["sr"])
    items = []
    for articles in stories_by_cat.values():
        for article in articles:
            items.append(article)
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break

    if not items:
        return ""

    rows = ""
    for article in items:
        headline = article.get("synthetic_headline") or article.get("title") or ""
        rows += f"""
            <tr>
              <td class="border-light" style="padding:16px 0;border-bottom:1px solid #e5e7eb">
                <p class="sans" style="margin:0 0 6px;font-family:'Manrope',sans-serif;font-size:10px;font-weight:bold;color:#b91c1c;text-transform:uppercase;letter-spacing:0.1em">{_escape(article.get('source') or 'izvor')}</p>
                <a href="{_escape(article.get('link') or conf['url'])}" class="text-title" style="font-family:'Noto Serif',Georgia,serif;font-size:17px;font-weight:900;color:#111827;text-decoration:none;line-height:1.25;display:block">
                  {_escape(headline)}
                </a>
              </td>
            </tr>"""

    return f"""
        <tr>
          <td style="padding:36px 0 12px">
            <p class="text-title sans" style="margin:0;font-family:'Manrope',sans-serif;font-size:12px;font-weight:900;letter-spacing:0.2em;text-transform:uppercase;color:#111827">{_escape(conf['also_today'])}</p>
          </td>
        </tr>
        {rows}"""


def render_morning_briefing_email(
    briefing: dict,
    period_start: datetime,
    period_end: datetime,
    locale: str = "sr",
    stories_by_cat: dict[str, list[dict]] | None = None,
) -> str:
    """Render the daily editorial briefing as the primary morning email body."""
    conf = LOCALES.get(locale, LOCALES["sr"])
    parsed = parse_briefing_for_email(briefing.get("content") or "", briefing.get("metadata") or {})
    stats = (briefing.get("metadata") or {}).get("stats") or {}
    total_articles = stats.get("total_articles") or 0
    pluralism_score = stats.get("pluralism_score") or 0

    title = parsed["title"] or conf["briefing_edition"]
    big_picture = parsed["big_picture"] or title
    bullets = parsed["bullets"]

    bullet_html = ""
    for bullet in bullets:
        bullet_html += f"""
            <tr>
              <td style="padding:0 0 12px">
                <p class="text-body" style="margin:0;color:#4a4a4a;font-family:'Source Serif 4',Georgia,serif;font-size:15px;line-height:1.6">• {_escape(bullet)}</p>
              </td>
            </tr>"""

    briefing_date = briefing.get("date") or period_end.date().isoformat()
    briefing_url = f"{conf['url']}/briefing"
    if briefing_date:
        briefing_url = f"{briefing_url}?date={briefing_date}"
    audio_url = f"{conf['url']}/briefing?date={briefing_date or ''}#audio"

    pulse_bits = [conf["briefing_edition"]]
    if total_articles:
        pulse_bits.append(f"{total_articles} {conf['temi']}")
    if pluralism_score:
        pulse_bits.append(f"{pluralism_score}% {conf['pulse'].lower()}")

    period_str = format_date(period_end, locale)
    story_block = _render_story_items(stories_by_cat or {}, locale, limit=3)

    html_body = f"""<!DOCTYPE html>
<html lang="{conf['lang_code']}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_escape(conf['masthead'])} — {_escape(conf['subject'])}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@800;900&family=Noto+Serif:ital,wght@0,900;1,900&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background-color:#f9fafb;-webkit-font-smoothing:antialiased">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f9fafb;padding:40px 20px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border:1px solid #e5e7eb;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1)">
        <tr>
          <td style="padding:40px 40px 24px;text-align:center;border-bottom:4px double #111827">
            <h1 style="margin:0;font-family:'Noto Serif',Georgia,serif;font-size:38px;font-weight:900;color:#111827;letter-spacing:-1.5px;text-transform:uppercase">{_escape(conf['masthead'])}</h1>
            <p style="margin:10px 0 0;font-family:'Manrope',sans-serif;font-size:11px;font-weight:bold;letter-spacing:0.3em;text-transform:uppercase;color:#6b7280">{_escape(conf['tagline'])}</p>
          </td>
        </tr>
        <tr>
          <td style="background-color:#111827;padding:12px 40px;text-align:center">
            <p style="margin:0;font-family:'Manrope',sans-serif;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">
              <span style="color:#ffffff">{_escape(conf['pulse'])}:</span> &nbsp; {_escape(' · '.join(pulse_bits))}
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 40px 0;text-align:center">
            <p style="margin:0;font-family:'Manrope',sans-serif;font-size:12px;color:#6b7280;letter-spacing:0.05em">{_escape(period_str)}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:28px 40px 0">
            <p style="margin:0 0 10px;font-family:'Manrope',sans-serif;font-size:10px;font-weight:900;letter-spacing:0.18em;text-transform:uppercase;color:#b91c1c">{_escape(conf['briefing_edition'])}</p>
            <h2 style="margin:0 0 18px;font-family:'Noto Serif',Georgia,serif;font-size:28px;line-height:1.2;font-weight:900;color:#111827">{_escape(title)}</h2>
            <p style="margin:0 0 8px;font-family:'Manrope',sans-serif;font-size:10px;font-weight:900;letter-spacing:0.16em;text-transform:uppercase;color:#111827">{_escape(conf['big_picture'])}</p>
            <p style="margin:0;color:#4a4a4a;font-family:'Source Serif 4',Georgia,serif;font-size:16px;line-height:1.65">{_escape(big_picture)}</p>
          </td>
        </tr>
        {f'<tr><td style="padding:18px 40px 0"><table width="100%" cellpadding="0" cellspacing="0">{bullet_html}</table></td></tr>' if bullet_html else ''}
        <tr>
          <td style="padding:28px 40px 12px;text-align:center">
            <a href="{_escape(briefing_url)}" style="display:inline-block;padding:14px 24px;background-color:#111827;color:#ffffff;font-family:'Manrope',sans-serif;font-size:12px;font-weight:bold;text-decoration:none;text-transform:uppercase;letter-spacing:0.15em;border-radius:2px;margin:0 8px 8px 0">{_escape(conf['open_briefing'])}</a>
            <a href="{_escape(audio_url)}" style="display:inline-block;padding:14px 24px;background-color:#ffffff;color:#111827;border:1px solid #111827;font-family:'Manrope',sans-serif;font-size:12px;font-weight:bold;text-decoration:none;text-transform:uppercase;letter-spacing:0.15em;border-radius:2px;margin:0 8px 8px 0">{_escape(conf['listen_audio'])}</a>
          </td>
        </tr>
        {f'<tr><td style="padding:0 40px 24px"><table width="100%" cellpadding="0" cellspacing="0">{story_block}</table></td></tr>' if story_block else ''}
        <tr>
          <td style="padding:30px 40px;text-align:center;background-color:#f3f4f6;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-family:'Manrope',sans-serif;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">{_escape(conf['footer_tagline'])}</p>
            <p style="margin:8px 0 0;font-family:'Manrope',sans-serif;font-size:10px;color:#9ca3af;line-height:1.5">
              {_escape(conf['footer_disclaimer'])}<br>
              {_escape(conf['unsubscribe'])} <a href="{{{{UNSUBSCRIBE_URL}}}}" style="color:#6b7280;text-decoration:underline">{_escape(conf['here'])}</a>.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return html_body


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
                summary_html = f"<p class=\"text-body\" style=\"margin:8px 0 0;color:#4a4a4a;font-family:'Source Serif 4',Georgia,serif;font-size:14px;line-height:1.55;letter-spacing:-0.01em\">{clean[:220]}…</p>"

            sources_badge = ""
            if a.get("source_count", 1) > 1:
                sources_badge = f'<span style="background:#b91c1c;color:#ffffff;font-family:sans-serif;font-size:10px;font-weight:bold;padding:2px 6px;text-transform:uppercase;letter-spacing:0.05em;border-radius:2px;margin-left:8px;vertical-align:middle">{format_sources(a["source_count"], locale)}</span>'

            items += f"""
            <tr>
              <td class="border-light" style="padding:20px 0;border-bottom:1px solid #e5e7eb">
                <p class="sans" style="margin:0 0 6px;font-family:'Manrope',sans-serif;font-size:10px;font-weight:bold;color:#b91c1c;text-transform:uppercase;letter-spacing:0.1em">{a.get('source','') or 'izvor'}</p>
                <a href="{a['link']}" class="text-title" style="font-family:'Noto Serif',Georgia,serif;font-size:19px;font-weight:900;color:#111827;text-decoration:none;line-height:1.25;display:block">
                  {headline}
                </a>
                {summary_html}
                <div style="margin-top:12px">
                    <a href="{a['link']}" class="text-muted sans" style="font-family:'Manrope',sans-serif;font-size:11px;font-weight:bold;color:#6b7280;text-decoration:none;text-transform:uppercase;letter-spacing:0.05em">{conf['read_more']}</a>
                    {sources_badge}
                </div>
              </td>
            </tr>"""

        cat_blocks += f"""
        <tr>
          <td style="padding:48px 0 12px">
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td class="text-title sans" style="font-family:'Manrope',sans-serif;font-size:12px;font-weight:900;letter-spacing:0.2em;text-transform:uppercase;color:#111827;padding-bottom:8px">{cat}</td>
                </tr>
                <tr>
                    <td class="double-border" style="height:2px;background:#111827"></td>
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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@800;900&family=Noto+Serif:ital,wght@0,900;1,900&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap" rel="stylesheet">
  <style>
    body {{
      font-family: 'Source Serif 4', Georgia, serif;
    }}
    h1 {{
      font-family: 'Noto Serif', Georgia, serif;
    }}
    .sans {{
      font-family: 'Manrope', 'Helvetica Neue', Helvetica, sans-serif;
    }}
    @media (prefers-color-scheme: dark) {{
      body, .bg-main {{
        background-color: #111827 !important;
        color: #f3f4f6 !important;
      }}
      .card-bg {{
        background-color: #1f2937 !important;
        border-color: #374151 !important;
      }}
      .border-light {{
        border-color: #374151 !important;
      }}
      .double-border {{
        border-color: #f3f4f6 !important;
        background-color: #f3f4f6 !important;
      }}
      .text-title {{
        color: #ffffff !important;
      }}
      .text-body {{
        color: #d1d5db !important;
      }}
      .text-muted {{
        color: #9ca3af !important;
      }}
      .btn-primary {{
        background-color: #f3f4f6 !important;
        color: #111827 !important;
      }}
      .footer-bg {{
        background-color: #1f2937 !important;
        border-top-color: #374151 !important;
      }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:#f9fafb;-webkit-font-smoothing:antialiased">

  <table width="100%" cellpadding="0" cellspacing="0" class="bg-main" style="background-color:#f9fafb;padding:40px 20px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" class="card-bg" style="max-width:600px;width:100%;background-color:#ffffff;border:1px solid #e5e7eb;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1)">

        <!-- Masthead -->
        <tr>
          <td class="double-border" style="padding:40px 40px 30px;text-align:center;border-bottom:4px double #111827">
            <h1 class="text-title" style="margin:0;font-size:42px;font-weight:900;color:#111827;letter-spacing:-1.5px;text-transform:uppercase">
              {conf['masthead']}
            </h1>
            <p class="text-muted sans" style="margin:10px 0 0;font-size:11px;font-weight:bold;letter-spacing:0.3em;text-transform:uppercase;color:#6b7280">
              {conf['tagline']}
            </p>
          </td>
        </tr>

        <!-- Media Pulse Bar -->
        <tr>
          <td style="background-color:#111827;padding:12px 40px;text-align:center">
            <p class="sans" style="margin:0;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">
              <span style="color:#ffffff">{conf['pulse']}:</span> &nbsp; {total_stories} {conf['temi']} &nbsp; • &nbsp; {total_sources} {conf['izvori']}
            </p>
          </td>
        </tr>

        <!-- Edition Info -->
        <tr>
          <td style="padding:24px 40px 0;text-align:center">
            <p class="text-muted sans" style="margin:0;font-size:12px;color:#6b7280;letter-spacing:0.05em">
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
                <a href="{conf['url']}" class="btn-primary sans" style="display:inline-block;padding:14px 28px;background-color:#111827;color:#ffffff;font-size:12px;font-weight:bold;text-decoration:none;text-transform:uppercase;letter-spacing:0.15em;border-radius:2px">
                    {conf['cta']}
                </a>
            </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td class="footer-bg border-light" style="padding:30px 40px;text-align:center;background-color:#f3f4f6;border-top:1px solid #e5e7eb">
            <p class="text-muted sans" style="margin:0;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">
              {conf['footer_tagline']}
            </p>
            <p class="text-muted sans" style="margin:8px 0 0;font-size:10px;color:#9ca3af;line-height:1.5">
              {conf['footer_disclaimer']}<br>
              {conf['unsubscribe']} <a href="{{UNSUBSCRIBE_URL}}" class="text-muted" style="color:#6b7280;text-decoration:underline">{conf['here']}</a>.
            </p>
          </td>
        </tr>

      </table>

      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
        <tr>
            <td style="padding:20px 0;text-align:center">
                <p class="text-muted sans" style="margin:0;font-size:10px;color:#9ca3af">
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
        briefing = fetch_daily_briefing(locale=loc, days=days)
        stories = fetch_top_stories(days=days, locale=loc)
        if briefing:
            digests[loc] = {
                "html": render_morning_briefing_email(
                    briefing,
                    start,
                    now,
                    locale=loc,
                    stories_by_cat=stories,
                ),
                "subject": f"{LOCALES[loc]['subject']} ({format_date(now, loc)})",
            }
        elif stories:
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
        if port in {465, 2465}:
            with smtplib.SMTP_SSL(host, port, timeout=15, context=ctx) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, to_address, msg.as_string())
        else:
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
