import datetime
import os
import urllib.parse

from core.api_helpers import normalize_perspectives
from core.celery_app import celery_app
from core.config import NTFY_TOPIC
from core.database import db_manager as db
from tasks.utils import log
from utils import score_cluster_for_homepage

from .briefing import _briefing_cluster_editorial_bonus, _dedupe_briefing_candidates
from .core import _parse_row_datetime, _record_delivery_tracking_event, _send_ntfy_message, _tracked_delivery_url
from .subscribers import (
    _cluster_delivery_match,
    _load_active_delivery_rows,
    _load_weekly_cluster_engagement,
    _load_weekly_source_engagement,
    _load_weekly_topic_engagement,
    _normalize_synced_profile_for_delivery,
)


def _load_weekly_digest_clusters(limit=32):
    rows = db.execute(
        """SELECT cluster_id, title, description, summary, source, category, topic, created_at
        FROM articles WHERE created_at >= NOW() - INTERVAL '7 days' ORDER BY created_at DESC LIMIT 420"""
    )
    clusters = {}
    for row in rows:
        clusters.setdefault(row["cluster_id"], []).append(row)

    # Batch fetch all cluster summaries at once (fix N+1 query)
    cluster_ids = list(clusters.keys())
    if cluster_ids:
        summaries_rows = db.execute(
            """SELECT cluster_id, summary, perspectives FROM cluster_summaries WHERE cluster_id = ANY(%s)""",
            (cluster_ids,),
        )
        summaries_map = {r["cluster_id"]: r for r in summaries_rows}
    else:
        summaries_map = {}

    ranked_clusters = []
    from utils import rank_articles_in_cluster

    for cluster_id, articles in clusters.items():
        ranked = rank_articles_in_cluster(articles)
        if not ranked:
            continue
        lead = ranked[0]
        # Use pre-fetched summary instead of individual query
        synthesis_row = summaries_map.get(cluster_id)
        normalized_perspectives_data = normalize_perspectives((synthesis_row or {}).get("perspectives") or [])
        difference_point = ""
        open_point = ""
        for item in normalized_perspectives_data:
            angle = str(item.get("angle") or "").lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            if not difference_point and ("razlic" in angle or "akcenat" in angle):
                difference_point = content
            if not open_point and ("otvor" in angle or "nejas" in angle):
                open_point = content

        ranked_clusters.append(
            {
                "cluster_id": cluster_id,
                "title": lead.get("title"),
                "description": lead.get("summary") or lead.get("description") or "",
                "source": lead.get("source"),
                "category": lead.get("category"),
                "topic": lead.get("topic"),
                "created_at": lead.get("created_at"),
                "source_count": len({a.get("source") for a in ranked if a.get("source")}),
                "difference_point": difference_point,
                "open_point": open_point,
                "cluster_summary": (synthesis_row or {}).get("summary") or "",
                "score": score_cluster_for_homepage(ranked),
                "other_titles": [
                    str(item.get("title") or "").strip() for item in ranked[1:5] if str(item.get("title") or "").strip()
                ],
            }
        )

    ranked_clusters.sort(key=lambda item: item["score"], reverse=True)
    return ranked_clusters[:limit]


def _build_weekly_digest_sections(profile, clusters, topic_engagement=None, source_engagement=None):
    profile = _normalize_synced_profile_for_delivery(profile)
    followed_topics = [topic for topic in profile["followedTopics"] if topic]
    followed_sources = [source for source in profile["followedSources"] if source]
    topic_engagement = topic_engagement or {}
    source_engagement = source_engagement or {}

    lead_cluster = clusters[0] if clusters else None
    sections = []

    if lead_cluster:
        sections.append(
            {
                "title": "Sto najmnogu se pomesti",
                "subtitle": lead_cluster.get("match_reason") or "glaven nedelen razvoj",
                "clusters": [lead_cluster],
            }
        )

    topic_sections = []
    for topic in followed_topics:
        matches = [
            cluster
            for cluster in clusters
            if topic
            in {
                str(cluster.get("topic") or "").strip(),
                str(cluster.get("category") or "").strip(),
            }
        ]
        if not matches:
            continue
        performance = topic_engagement.get(topic) or {}
        topic_sections.append(
            {
                "title": f"Sledena tema: {topic}",
                "subtitle": (
                    "silen interes vo prethodnite nedelni pregledi"
                    if float(performance.get("section_score") or 0.0) >= 0.65
                    else "najvaznite linii za temata sto me sledite"
                ),
                "clusters": matches[:2],
                "score": float(performance.get("section_score") or 0.0)
                + max(float(matches[0].get("match_score") or 0.0), 0.0),
            }
        )
    topic_sections.sort(key=lambda item: item.get("score") or 0.0, reverse=True)
    sections.extend(topic_sections[:2])

    source_focus = []
    if followed_sources:
        for source in followed_sources[:3]:
            source_cluster = next(
                (cluster for cluster in clusters if str(cluster.get("source") or "").strip() == source),
                None,
            )
            if source_cluster:
                source_focus.append((source, source_cluster))
    if source_focus:
        source_focus.sort(
            key=lambda item: (
                float((source_engagement.get(item[0]) or {}).get("section_score") or 0.0),
                float(item[1].get("match_score") or 0.0),
                float(item[1].get("score") or 0.0),
            ),
            reverse=True,
        )
        source_clusters = [cluster for _, cluster in source_focus[:2]]
        strongest_source = source_focus[0][0]
        strongest_source_perf = source_engagement.get(strongest_source) or {}
        sections.append(
            {
                "title": "izvori sto im sledite",
                "subtitle": (
                    f"{strongest_source} nosi najsilen odziv medju sledenite izvori ova Nedelja"
                    if float(strongest_source_perf.get("section_score") or 0.0) >= 0.6
                    else "kade sledenite izvori me vodat ili potvrduvaat nedelata"
                ),
                "clusters": source_clusters,
                "score": float(strongest_source_perf.get("section_score") or 0.0)
                + max(float(source_clusters[0].get("match_score") or 0.0), 0.0),
            }
        )

    open_items = [cluster for cluster in clusters if cluster.get("open_point")]
    if open_items:
        sections.append(
            {
                "title": "Sta ostaje otvoreno",
                "subtitle": "linii sto vleguvaat vo slednata Nedelja bez celosna potvrda",
                "clusters": open_items[:2],
                "score": max(float(open_items[0].get("match_score") or 0.0), 0.0),
            }
        )
    static_lead = sections[:1]
    dynamic_sections = sections[1:]
    dynamic_sections.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return (static_lead + dynamic_sections)[:4]


def _select_profile_weekly_clusters(profile, limit=5, _cached_clusters=None, _cached_engagement=None):
    profile = _normalize_synced_profile_for_delivery(profile)
    engagement_map = _cached_engagement if _cached_engagement is not None else _load_weekly_cluster_engagement()
    clusters_to_score = _cached_clusters if _cached_clusters is not None else _load_weekly_digest_clusters(limit=28)
    ranked = []
    for cluster in clusters_to_score:
        match_score, reasons, _, _ = _cluster_delivery_match(cluster, profile)
        engagement = engagement_map.get(str(cluster.get("cluster_id") or "").strip()) or {}
        engagement_bonus = 0.0
        engagement_note = ""
        sends = int(engagement.get("sends") or 0)
        open_rate = float(engagement.get("open_rate") or 0.0)
        click_rate = float(engagement.get("click_rate") or 0.0)
        if sends >= 2 and click_rate >= 0.22:
            engagement_bonus = 0.85
            engagement_note = "silen odziv vo nedelnite pregledi"
        elif sends >= 2 and open_rate >= 0.55:
            engagement_bonus = 0.45
            engagement_note = "dobar odziv vo nedelnite pregledi"
        elif sends >= 3 and open_rate < 0.25 and int(engagement.get("clicks") or 0) == 0:
            engagement_bonus = -0.35
            engagement_note = "poslab odziv vo nedelnite pregledi"

        total_score = (
            match_score
            + min(1.6, float(cluster.get("score") or 0) * 0.2)
            + engagement_bonus
            + min(0.55, float(engagement.get("engagement_score") or 0.0) * 0.35)
        )
        match_reason = "; ".join(reasons[:2]) or "nedelna vaznost"
        if engagement_note:
            match_reason = f"{match_reason}; {engagement_note}"
        ranked.append(
            {
                **cluster,
                "match_score": total_score + _briefing_cluster_editorial_bonus(cluster),
                "match_reason": match_reason,
            }
        )

    personalized = [item for item in ranked if item["match_score"] >= 1.9]
    personalized.sort(key=lambda item: (item["match_score"], item.get("score") or 0), reverse=True)
    return _dedupe_briefing_candidates(personalized or ranked, limit=limit)


def _build_profile_weekly_digest_message(profile, clusters):
    profile = _normalize_synced_profile_for_delivery(profile)
    followed_topics = profile["followedTopics"][:4]
    followed_sources = profile["followedSources"][:4]
    sections = _build_weekly_digest_sections(
        profile,
        clusters,
        _load_weekly_topic_engagement(),
        _load_weekly_source_engagement(),
    )

    lines = ["Presek nedelen pregled"]
    if followed_topics:
        lines.append(f"Fokus temi: {', '.join(followed_topics)}")
    if followed_sources:
        lines.append(f"Fokus izvori: {', '.join(followed_sources)}")

    rendered_cluster_ids = set()
    for section in sections:
        section_clusters = []
        for cluster in section.get("clusters") or []:
            cluster_id = str(cluster.get("cluster_id") or "").strip()
            if not cluster_id or cluster_id in rendered_cluster_ids:
                continue
            rendered_cluster_ids.add(cluster_id)
            section_clusters.append(cluster)
        if not section_clusters:
            continue

        lines.append("")
        lines.append(f"## {section.get('title') or 'Klucen del'}")
        if section.get("subtitle"):
            lines.append(str(section["subtitle"]))

        for cluster in section_clusters[:2]:
            lines.append(f"• {cluster.get('title') or 'Kljucna prica nedeljna'}")
            lines.append(
                f"  {cluster.get('source') or 'izvor'} · {cluster.get('source_count') or 1} izvori · {cluster.get('match_reason') or 'nedeljni kontekst'}"
            )
            if cluster.get("cluster_summary"):
                lines.append(f"  {str(cluster['cluster_summary']).splitlines()[0][:220]}")
            elif cluster.get("description"):
                lines.append(f"  {str(cluster['description'])[:220]}")
            if cluster.get("difference_point"):
                lines.append(f"  glavna razlika: {str(cluster['difference_point'])[:180]}")
            elif cluster.get("open_point"):
                lines.append(f"  Sto ostana otvoreno: {str(cluster['open_point'])[:180]}")

    return "\n".join(line for line in lines if line is not None).strip()


def _build_profile_weekly_digest_html(profile, sections, unsubscribe_url, lang="sr"):
    is_mk = lang == "mk"
    
    t_masthead = "ПРЕСЕК" if is_mk else "PRESEK"
    t_tagline = "Персонализиран неделен опсерваториум" if is_mk else "Personalizovani nedeljni opservatorijum"
    t_fokus_temi = "Фокус теми" if is_mk else "Fokus teme"
    t_fokus_izvori = "Фокус извори" if is_mk else "Fokus izvori"
    t_razlika = "ГЛАВНА РАЗЛИКА ВО ИЗВЕСТУВАЊЕТО" if is_mk else "GLAVNA RAZLIKA U IZVEŠTAVANJU"
    t_otvoreno = "ОТВОРЕНО ПРАШАЊЕ" if is_mk else "OTVORENO PITANJE"
    t_footer = "Пресек е дигитален сервис за медиумска транспарентност и јавен увид." if is_mk else "Presek je digitalni servis za medijsku transparentnost i javni uvid."
    t_disclaimer = "Ја добивате оваа порака бидејќи сте претплатени на неделниот личен преглед." if is_mk else "Ovu poruku dobijate jer ste pretplaćeni na nedeljni lični pregled."
    t_unsub = "Ако сакате да се одјавите, кликнете" if is_mk else "Ako želite da se odjavite, kliknite"
    t_here = "овде" if is_mk else "ovde"
    t_rights = "Сите права се задржани" if is_mk else "Sva prava zadržana"
    t_sources = "извори" if is_mk else "izvora"

    profile = _normalize_synced_profile_for_delivery(profile)
    followed_topics = profile.get("followedTopics") or []
    followed_sources = profile.get("followedSources") or []

    meta_items = []
    if followed_topics:
        meta_items.append(f"{t_fokus_temi}: {', '.join(followed_topics[:3])}")
    if followed_sources:
        meta_items.append(f"{t_fokus_izvori}: {', '.join(followed_sources[:3])}")
    meta_text = " &nbsp; • &nbsp; ".join(meta_items) if meta_items else t_tagline

    sections_html = ""
    rendered_cluster_ids = set()
    
    for section in sections:
        section_clusters = []
        for cluster in section.get("clusters") or []:
            cluster_id = str(cluster.get("cluster_id") or "").strip()
            if not cluster_id or cluster_id in rendered_cluster_ids:
                continue
            rendered_cluster_ids.add(cluster_id)
            section_clusters.append(cluster)
        
        if not section_clusters:
            continue

        cluster_items_html = ""
        for cluster in section_clusters[:2]:
            cluster_id = cluster["cluster_id"]
            title = cluster.get("title") or "Kljucna prica"
            source = cluster.get("source") or "Izvor"
            source_count = cluster.get("source_count") or 1
            summary = cluster.get("cluster_summary") or cluster.get("description") or ""
            diff_point = cluster.get("difference_point") or ""
            open_point = cluster.get("open_point") or ""
            match_reason = cluster.get("match_reason") or ""

            angle_block = ""
            if diff_point:
                angle_block = f"""
                <div style="margin-top:12px;padding:12px;background-color:#eff6ff;border-left:4px solid #3b82f6;border-radius:2px">
                    <span style="font-family:'Manrope',sans-serif;font-size:9px;font-weight:900;letter-spacing:0.12em;color:#1d4ed8;display:block;margin-bottom:4px;text-transform:uppercase">{t_razlika}</span>
                    <p style="margin:0;font-size:12px;line-height:1.5;color:#1e3a8a">{diff_point}</p>
                </div>"""
            elif open_point:
                angle_block = f"""
                <div style="margin-top:12px;padding:12px;background-color:#fffbeb;border-left:4px solid #f59e0b;border-radius:2px">
                    <span style="font-family:'Manrope',sans-serif;font-size:9px;font-weight:900;letter-spacing:0.12em;color:#b45309;display:block;margin-bottom:4px;text-transform:uppercase">{t_otvoreno}</span>
                    <p style="margin:0;font-size:12px;line-height:1.5;color:#78350f">{open_point}</p>
                </div>"""

            cluster_items_html += f"""
            <div style="margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid #f3f4f6">
                <h3 style="margin:0 0 8px;font-family:'Source Serif 4',Georgia,serif;font-size:18px;font-weight:600;line-height:1.35">
                    <a href="{{{{CLUSTER_LINK_{cluster_id}}}}}" class="text-title" style="color:#111827;text-decoration:none;hover:text-underline">{title}</a>
                </h3>
                <div class="sans" style="font-family:'Manrope',sans-serif;font-size:10px;font-weight:bold;color:#6b7280;letter-spacing:0.05em;text-transform:uppercase;margin-bottom:10px">
                    <span style="color:#eb5e28">{source}</span> &nbsp; • &nbsp; {source_count} {t_sources} &nbsp; • &nbsp; <span style="color:#10b981">{match_reason}</span>
                </div>
                <p class="text-body" style="margin:0;font-size:14px;line-height:1.6;color:#374151">{summary[:260]}...</p>
                {angle_block}
            </div>"""

        sections_html += f"""
        <tr>
          <td style="padding:32px 0 12px">
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td class="text-title sans" style="font-family:'Manrope',sans-serif;font-size:12px;font-weight:900;letter-spacing:0.18em;text-transform:uppercase;color:#111827;padding-bottom:6px">{section.get('title')}</td>
                </tr>
                <tr>
                    <td class="double-border" style="height:2px;background:#111827"></td>
                </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 0 0">
            {cluster_items_html}
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{t_masthead} — {t_tagline}</title>
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
              {t_masthead}
            </h1>
            <p class="text-muted sans" style="margin:10px 0 0;font-size:11px;font-weight:bold;letter-spacing:0.3em;text-transform:uppercase;color:#6b7280">
              {t_tagline}
            </p>
          </td>
        </tr>

        <!-- Media Pulse Bar -->
        <tr>
          <td style="background-color:#111827;padding:12px 40px;text-align:center">
            <p class="sans" style="margin:0;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">
              {meta_text}
            </p>
          </td>
        </tr>

        <!-- Stories Content -->
        <tr>
          <td style="padding:0 40px 40px">
            <table width="100%" cellpadding="0" cellspacing="0">
              {sections_html}
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td class="footer-bg border-light" style="padding:30px 40px;text-align:center;background-color:#f3f4f6;border-top:1px solid #e5e7eb">
            <p class="text-muted sans" style="margin:0;font-size:10px;font-weight:bold;color:#9ca3af;letter-spacing:0.1em;text-transform:uppercase">
              {t_footer}
            </p>
            <p class="text-muted sans" style="margin:8px 0 0;font-size:10px;color:#9ca3af;line-height:1.5">
              {t_disclaimer}<br>
              {t_unsub} <a href="{unsubscribe_url}" class="text-muted" style="color:#6b7280;text-decoration:underline">{t_here}</a>.
            </p>
          </td>
        </tr>

      </table>

      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
        <tr>
            <td style="padding:20px 0;text-align:center">
                <p class="text-muted sans" style="margin:0;font-size:10px;color:#9ca3af">
                    © {datetime.datetime.now().year} Presek. {t_rights}.
                </p>
            </td>
        </tr>
      </table>
    </td></tr>
  </table>

</body>
</html>"""
    return html


@celery_app.task
def send_daily_digest_task():
    try:
        import core.digest as digest_module

        digest_module.send_digest()
    except Exception as e:
        log.warning(f"[tasks] Daily digest skipped: {e}")


@celery_app.task
def send_profile_weekly_digests_task():
    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0
    try:
        rows = _load_active_delivery_rows()
        all_weekly_clusters = _load_weekly_digest_clusters(limit=28)
        engagement_map = _load_weekly_cluster_engagement()

        for row in rows:
            if not row.get("weekly_digest"):
                continue

            # BUGFIX: Check last_weekly_sent_at cooldown instead of last_morning_sent_at
            last_sent = _parse_row_datetime(row.get("last_weekly_sent_at"))
            if last_sent:
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=datetime.timezone.utc)
                if (now - last_sent.astimezone(datetime.timezone.utc)).total_seconds() < 6.5 * 24 * 3600:
                    continue

            target = str(row.get("target") or NTFY_TOPIC).strip()
            profile = _normalize_synced_profile_for_delivery(row.get("profile_data") or {})
            clusters = _select_profile_weekly_clusters(
                profile, _cached_clusters=all_weekly_clusters, _cached_engagement=engagement_map
            )
            if not clusters:
                continue

            channel = str(row.get("channel") or "ntfy").strip().lower()
            lang = str(row.get("locale") or "sr").strip().lower()

            primary_cluster_id = str((clusters[0] or {}).get("cluster_id") or "").strip() or None
            
            # Record send event for analytics and dynamic tracking redirects
            send_event_id = _record_delivery_tracking_event(
                row["sync_token"],
                "send",
                "weekly",
                target=target,
                cluster_id=primary_cluster_id,
                metadata={
                    "cluster_ids": [
                        str(item.get("cluster_id") or "").strip()
                        for item in clusters[:5]
                        if str(item.get("cluster_id") or "").strip()
                    ],
                    "focus_topics": profile.get("followedTopics") or [],
                    "focus_sources": profile.get("followedSources") or []
                },
            )

            if channel == "email":
                # Build custom HTML email briefing
                _PUBLIC_SITE_URL = str(os.environ.get("PUBLIC_SITE_URL") or "https://presek.live").rstrip("/")
                from core.signed_tokens import build_newsletter_unsubscribe_url

                unsubscribe_url = build_newsletter_unsubscribe_url(_PUBLIC_SITE_URL, target, lang)
                sections = _build_weekly_digest_sections(
                    profile,
                    clusters,
                    _load_weekly_topic_engagement(),
                    _load_weekly_source_engagement(),
                )
                html_message = _build_profile_weekly_digest_html(profile, sections, unsubscribe_url, lang)
                
                # Replace links with dynamic tracking click redirection URLs
                for cluster in clusters:
                    c_id = cluster["cluster_id"]
                    c_redirect_path = f"/cluster/{c_id}" if lang == "sr" else f"/mk/cluster/{c_id}"
                    track_url = _tracked_delivery_url(send_event_id, "click", c_redirect_path) if send_event_id else f"{_PUBLIC_SITE_URL}{c_redirect_path}"
                    html_message = html_message.replace(f"{{{{CLUSTER_LINK_{c_id}}}}}", track_url)

                subject = "Пресек: Вашиот неделен извештај" if lang == "mk" else "Presek: Vaš nedeljni izveštaj"
                
                # Deliver HTML email via SMTP
                smtp_user = os.environ.get("SMTP_USER", "")
                smtp_pass = os.environ.get("SMTP_PASS", "")
                
                if smtp_user and smtp_pass:
                    from tasks.utils import send_email
                    if send_email(html_message, subject, smtp_user, smtp_pass, target):
                        db.execute(
                            "UPDATE synced_delivery_subscriptions SET last_weekly_sent_at = NOW(), updated_at = NOW() WHERE sync_token = %s",
                            (row["sync_token"],),
                            fetch=False,
                        )
                        sent += 1
                else:
                    log.warning(f"[tasks] SMTP credentials not set. Skipping weekly email delivery to {target}.")
            else:
                # Fallback: lightweight NTFY push notification
                message = _build_profile_weekly_digest_message(profile, clusters)
                if not message:
                    continue

                click_url = _tracked_delivery_url(send_event_id, "open", "/briefing") if send_event_id else None
                click_track_url = _tracked_delivery_url(send_event_id, "click", "/briefing") if send_event_id else None
                message_with_link = message if not click_track_url else f"{message}\n\nOtvori pregled: {click_track_url}"
                
                if _send_ntfy_message(
                    target,
                    "Presek · Nedelen pregled",
                    message_with_link,
                    tags="spiral_calendar,newspaper",
                    click_url=click_url,
                ):
                    db.execute(
                        "UPDATE synced_delivery_subscriptions SET last_weekly_sent_at = NOW(), updated_at = NOW() WHERE sync_token = %s",
                        (row["sync_token"],),
                        fetch=False,
                    )
                    sent += 1
    except Exception as e:
        log.warning(f"[tasks] Weekly digests failed: {e}")
    else:
        if sent:
            log.info(f"[tasks] Sent {sent} weekly profile digests.")


@celery_app.task
def send_newsletter_task():
    try:
        from core.digest import send_newsletter_to_all_subscribers

        count = send_newsletter_to_all_subscribers(days=1)
        log.info(f"[tasks] Morning briefing sent to {count} subscribers.")
    except Exception as e:
        log.warning(f"[tasks] Newsletter delivery failed: {e}")
