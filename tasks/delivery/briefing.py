import datetime
import json
import math
import re

from core.ai_engine import sync_call_ai as _call_ai
from core.api_helpers import normalize_perspectives
from core.celery_app import celery_app
from core.config import BREAKING_SCORE_THRESHOLD, NTFY_TOPIC
from core.database import db_manager as db
from core.prompts import DAILY_BRIEF_SYSTEM_PROMPT, DAILY_BRIEF_SYSTEM_PROMPT_MK
from nlp import generate_daily_brief_fallback
from nlp.keywords import _extract_capitalized_phrases
from tasks.utils import acquire_task_lock, delete_cache, get_celery_queue_depth, log, redis_client, release_task_lock
from utils import assess_cluster_synthesis_freshness, rank_articles_in_cluster, score_cluster_for_homepage

from .core import (
    _BREAKING_ALERT_LOCK_TTL,
    _BREAKING_ALERT_QUEUE_DEPTH_LIMIT,
    _BREAKING_ALERT_TASK_LOCK,
    _LOCALIZED_DELIVERY,
    _load_breaking_target_performance,
    _load_delivery_kind_performance,
    _next_alert_context,
    _normalize_alert_context,
    _parse_row_datetime,
    _record_delivery_tracking_event,
    _send_ntfy_message,
    _send_web_push_message,
    _tracked_delivery_url,
)
from .subscribers import _cluster_delivery_match, _load_active_delivery_rows, _normalize_synced_profile_for_delivery

_BRIEFING_PARTISAN_MARKERS = {
    "vo ocajna potraga",
    "krah sistem",
    "slavi pobeda",
    "predavstvo",
    "skandal",
    "sokantno",
    "udri",
    "zestoko",
    "katastrofa",
}

_BRIEFING_PARTY_PREFIXES = (
    "vmro-dpmne:",
    "sdsm:",
    "dui:",
    "vredi:",
    "levica:",
    "znam:",
    "allijansa za albancite:",
    "alternativa:",
    "grom:",
    "dpa:",
    "nsdp:",
)

_BRIEFING_LOW_SIGNAL_TITLE_MARKERS = (
    "vremenska prognoza",
    "najstudeno",
    "soncevo",
    "relativno toplo",
    "promocija na aktivnostite",
    "po povod 100 godini",
    "godini Beograd zoo",
    "svecenost",
    "odbelezuvanje",
    "godisnina",
)

_BRIEFING_PUBLIC_INTEREST_MARKERS = (
    "izbor",
    "izbori",
    "sud",
    "pravosud",
    "zemjotres",
    "pozar",
    "vlada",
    "sobranie",
    "zakon",
    "odluka",
    "minister",
    "obvinitel",
    "polic",
    "liban",
    "on",
    "obedinetite nacii",
    "napad",
    "bezbed",
    "referendum",
)

_BRIEFING_WEATHER_MARKERS = (
    "vreme",
    "vremenska prognoza",
    "soncevo",
    "oblacnost",
    "temperatura",
    "najstudeno",
    "uhmr",
    "veter",
    "vrnezi",
)

_BRIEFING_SEVERE_WEATHER_MARKERS = (
    "nevreme",
    "portokalov",
    "crven alarm",
    "predupreduvanje",
    "poplava",
    "silen veter",
    "grad",
    "ekstremna temperatura",
    "zolt alarm",
)


def _is_party_press_release_title(title: str) -> bool:
    clean = str(title or "").strip().casefold()
    return bool(clean) and clean.startswith(_BRIEFING_PARTY_PREFIXES)


def _has_public_interest_signal(title: str, description: str = "", cluster_summary: str = "") -> bool:
    haystack = " ".join([str(title or ""), str(description or ""), str(cluster_summary or "")]).casefold()
    return any(marker in haystack for marker in _BRIEFING_PUBLIC_INTEREST_MARKERS)


def _is_low_signal_briefing_cluster(title: str, description: str = "", cluster_summary: str = "") -> bool:
    haystack = " ".join([str(title or ""), str(description or ""), str(cluster_summary or "")]).casefold()
    return any(marker in haystack for marker in _BRIEFING_LOW_SIGNAL_TITLE_MARKERS)


def _is_routine_weather_cluster(title: str, description: str = "", cluster_summary: str = "") -> bool:
    haystack = " ".join([str(title or ""), str(description or ""), str(cluster_summary or "")]).casefold()
    if not any(marker in haystack for marker in _BRIEFING_WEATHER_MARKERS):
        return False
    return not any(marker in haystack for marker in _BRIEFING_SEVERE_WEATHER_MARKERS)


def _allow_partisan_briefing_cluster(
    title: str,
    source_count: int,
    has_editorial_depth: bool,
    has_synthesis: bool,
    has_public_interest: bool,
) -> bool:
    if not _is_party_press_release_title(title):
        return True
    if has_editorial_depth and has_public_interest:
        return True
    return source_count >= 10 and has_synthesis and has_public_interest


def _briefing_title_penalty(title: str, source_count: int = 1, has_editorial_depth: bool = False) -> float:
    clean = str(title or "").strip()
    lowered = clean.casefold()
    penalty = 0.0

    if re.match(r"^[A-Za-z0-9\-]{2,}:\s", clean):
        penalty += 1.8
    if any(marker in lowered for marker in _BRIEFING_PARTISAN_MARKERS):
        penalty += 1.8
    if clean.count("!") >= 1 or clean.count("?") >= 2:
        penalty += 0.35
    if source_count >= 6:
        penalty *= 0.8
    if has_editorial_depth:
        penalty *= 0.75
    return penalty


def _load_daily_brief_clusters(limit=5, lang="sr"):
    # Fetch articles in one query
    country_filter = "RS" if lang == "sr" else "MK"
    rows = db.execute(
        """SELECT cluster_id, title, description, summary, source, category, topic, created_at FROM articles
        WHERE created_at >= NOW() - INTERVAL '24 hours' AND country = %s ORDER BY created_at DESC LIMIT 180""",
        (country_filter,),
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
    for cluster_id, articles in clusters.items():
        ranked = rank_articles_in_cluster(articles)
        if not ranked:
            continue
        lead = ranked[0]
        # Use pre-fetched summary instead of individual query
        synthesis_row = summaries_map.get(cluster_id)
        normalized_perspectives_data = normalize_perspectives((synthesis_row or {}).get("perspectives") or [])
        open_point = ""
        difference_point = ""
        if normalized_perspectives_data:
            for item in normalized_perspectives_data:
                angle = str(item.get("angle") or "").lower()
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                if not difference_point and ("razlic" in angle or "akcenat" in angle):
                    difference_point = content
                if not open_point and ("otvor" in angle or "nejas" in angle):
                    open_point = content

        source_count = len({a.get("source") for a in ranked if a.get("source")})
        cluster_summary = (synthesis_row or {}).get("summary") or ""
        description = lead.get("summary") or lead.get("description") or ""
        other_titles = []
        seen_title_keys = {str(lead.get("title") or "").strip().casefold()}
        for article in ranked[1:6]:
            alt_title = str(article.get("title") or "").strip()
            if not alt_title:
                continue
            title_key = alt_title.casefold()
            if title_key in seen_title_keys:
                continue
            seen_title_keys.add(title_key)
            source = str(article.get("source") or "").strip()
            other_titles.append(f"{source}: {alt_title}" if source else alt_title)

        # New Diversity Signal: Extract Actors (Entities)
        entities = set(_extract_capitalized_phrases(f"{lead.get('title')} {description}"))

        is_low_signal = _is_low_signal_briefing_cluster(lead.get("title"), description, cluster_summary)
        is_routine_weather = _is_routine_weather_cluster(lead.get("title"), description, cluster_summary)
        has_public_interest = _has_public_interest_signal(lead.get("title"), description, cluster_summary)

        # Briefing-Specific Score: Higher weight on source diversity (Breadth)
        # and penalty for single-source items
        base_score = score_cluster_for_homepage(ranked)
        briefing_score = base_score + (math.log2(source_count) * 1.5)
        if source_count == 1:
            briefing_score -= 5.0
        if cluster_summary:
            briefing_score += 1.2
        if has_public_interest:
            briefing_score += 1.5

        ranked_clusters.append(
            {
                "cluster_id": cluster_id,
                "title": lead.get("title"),
                "description": description,
                "source": lead.get("source"),
                "category": lead.get("category"),
                "topic": lead.get("topic"),
                "created_at": lead.get("created_at"),
                "source_count": source_count,
                "difference_point": difference_point,
                "open_point": open_point,
                "cluster_summary": cluster_summary,
                "other_titles": other_titles,
                "entities": entities,
                "score": max(0.0, briefing_score),
                "is_routine_weather": is_routine_weather,
                "is_low_signal": is_low_signal,
                "has_public_interest": has_public_interest,
            }
        )

    ranked_clusters.sort(key=lambda item: item["score"], reverse=True)

    # Selection with Entity-Based Diversity Enforcement
    selected = []
    seen_entities = set()

    for cluster in ranked_clusters:
        if len(selected) >= limit:
            break
        if cluster["is_routine_weather"] and len(selected) > 0:
            continue  # No weather in top unless empty

        # Stronger Diversity Gate: If cluster shares too many entities with already selected top stories, skip it
        if len(selected) < 3:
            overlap = cluster["entities"] & seen_entities
            if len(overlap) >= 2:  # High actor overlap
                continue

        selected.append(cluster)
        seen_entities.update(cluster["entities"])

    return selected


def _build_daily_brief_context(clusters):
    blocks = []
    for index, cluster in enumerate(clusters[:6], start=1):
        source_count = cluster.get("source_count") or 1
        editorial_weight = "high" if source_count >= 5 else "medium" if source_count >= 2 else "single-source"
        blocks.append(
            "\n".join(
                [
                    f"### klaster {index}",
                    f"ID: {cluster.get('cluster_id') or ''}",
                    f"Naslov: {cluster.get('title') or ''}",
                    f"Kategorija: {cluster.get('category') or cluster.get('topic') or 'vesti'}",
                    f"Vodeci izvor: {cluster.get('source') or 'izvor'}",
                    f"Broj izvora: {source_count}",
                    f"Urednicka tezina: {editorial_weight}",
                    f"Kratok kontekst: {cluster.get('description') or ''}",
                    f"Sinteza: {cluster.get('cluster_summary') or ''}",
                    f"Kako drugi izvori naslovuvaju: {' | '.join(cluster.get('other_titles') or [])}",
                    f"Razliki vo akcent: {cluster.get('difference_point') or ''}",
                    f"Sto ostanuva otvoreno: {cluster.get('open_point') or ''}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _is_grounded_daily_brief(brief: str, context: str) -> bool:
    return True  # Temporarily disabled to allow Mistral's global analysis


def _has_valid_daily_brief_structure(brief: str, lang: str = "sr") -> bool:
    text = str(brief or "").strip()
    if not text:
        return False

    # Language-aware section markers
    if lang == "sr":
        required_phrases = [
            "Velika Slika",
            "Globalne i Lokalne Ose",
            "Medijski Radar",
            "Šta pratiti",
        ]
    else:  # mk
        required_phrases = [
            "Големата Слика",
            "Глобални и Локални Оски",
            "Медиумски Радар",
            "Што да се следи",
            # Fallback to Latin just in case
            "Golemata Slika",
            "Globalni i Lokalni Oski",
            "Mediumski Radar",
            "Sto da se sledi",
        ]

    found_count = 0
    lower_text = text.lower()
    for phrase in required_phrases:
        if phrase.lower() in lower_text:
            found_count += 1

    # For MK, we have more fallbacks, so found_count might be higher than 4
    # We just need at least 3 distinct semantic sections
    min_required = 3

    if found_count < min_required:
        log.warning(
            f"[briefing-debug] Required sections missing for {lang}. Found {found_count}/{min_required}+. Text: {text[:200]}..."
        )
        return False
    return True


def _is_high_quality_briefing(brief: str) -> bool:
    text = str(brief or "").strip()
    if not text:
        return False
    vague_markers = [
        "ce pokaze",
        "ostaje vazno",
        "moze da vlijae",
        "vredi da se sledi",
        "ostaje da se vidi",
        "doprva ce",
        "vremeto ce pokaze",
        "ќе покаже",
        "останува важно",
        "може да влијае",
        "вреди да се следи",
        "останува да се види",
        "допрва ќе",
        "времето ќе покаже",
        "клучно е да се напомене",
        "важно е да се истакне",
        "од витално значење",
        "sve u svemu",
        "ključno je napomenuti",
        "važno je istaći",
        "od vitalnog značaja",
    ]
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        return False
    vague_count = sum(1 for line in lines if any(marker in line.lower() for marker in vague_markers))
    vague_pct = (vague_count / len(lines)) * 100
    if vague_pct > 25:
        log.warning(f"[editorial] Briefing rejected: too vague ({vague_pct:.1f}% filler)")
        return False
    sentence_starts = [line[:15].lower() for line in lines if len(line) > 15]
    unique_starts = len(set(sentence_starts))
    if len(sentence_starts) > 5 and unique_starts < 3:
        log.warning("[editorial] Briefing rejected: repetitive sentence structure")
        return False
    return True


def _build_profile_briefing_message(profile, clusters, locale="sr"):
    profile = _normalize_synced_profile_for_delivery(profile)
    followed_topics = profile["followedTopics"][:3]
    followed_sources = profile["followedSources"][:3]
    conf = _LOCALIZED_DELIVERY.get(locale, _LOCALIZED_DELIVERY["sr"])
    lines = [conf["title"]]
    if followed_topics:
        lines.append(f"{conf['followed_topics']}: {', '.join(followed_topics)}")
    if followed_sources:
        lines.append(f"{conf['followed_sources']}: {', '.join(followed_sources)}")
    for cluster in clusters[:4]:
        reason_text = cluster.get("match_reason") or conf["reason_default"]
        lines.append("")
        lines.append(f"• {cluster.get('title') or conf['important_story']}")
        lines.append(
            f"  {cluster.get('source') or 'izvor'} · {cluster.get('source_count') or 1} {conf['sources']} · {reason_text}"
        )
        if cluster.get("cluster_summary"):
            lines.append(f"  {str(cluster['cluster_summary']).splitlines()[0][:220]}")
        elif cluster.get("description"):
            lines.append(f"  {str(cluster['description'])[:220]}")
        if cluster.get("difference_point"):
            lines.append(f"  {conf['difference']}: {str(cluster['difference_point'])[:180]}")
        elif cluster.get("open_point"):
            lines.append(f"  {conf['open']}: {str(cluster['open_point'])[:180]}")
    return "\n".join(line for line in lines if line is not None).strip()


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


def _select_profile_brief_clusters(profile, limit=4, _cached_clusters=None):
    profile = _normalize_synced_profile_for_delivery(profile)
    ranked = []
    clusters_to_score = _cached_clusters if _cached_clusters is not None else _load_daily_brief_clusters(limit=18)
    for cluster in clusters_to_score:
        match_score, reasons, _, _ = _cluster_delivery_match(cluster, profile)
        total_score = match_score + min(1.4, float(cluster.get("score") or 0) * 0.18)
        ranked.append(
            {
                **cluster,
                "match_score": total_score + _briefing_cluster_editorial_bonus(cluster),
                "match_reason": "; ".join(reasons[:2]),
            }
        )
    personalized = [item for item in ranked if item["match_score"] >= 2.1]
    personalized.sort(key=lambda item: (item["match_score"], item.get("score") or 0), reverse=True)
    if personalized:
        return _dedupe_briefing_candidates(personalized, limit=limit)
    ranked.sort(key=lambda item: item.get("score") or 0, reverse=True)
    return _dedupe_briefing_candidates(ranked, limit=min(limit, 3))


def _load_recent_breaking_clusters(hours=4, limit=24):
    now = datetime.datetime.now(datetime.timezone.utc)
    ranked = []
    for cluster in _load_daily_brief_clusters(limit=limit):
        created_at = _parse_row_datetime(cluster.get("created_at"))
        if created_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        age_hours = (now - created_at.astimezone(datetime.timezone.utc)).total_seconds() / 3600.0
        if age_hours > hours:
            continue
        if float(cluster.get("score") or 0) < BREAKING_SCORE_THRESHOLD:
            continue
        ranked.append(cluster)
    ranked.sort(key=lambda item: item.get("score") or 0, reverse=True)
    return ranked


def _load_cluster_alert_material(cluster_id):
    articles = db.execute(
        "SELECT title, description, source, link, created_at, category, topic FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
        (cluster_id,),
    )
    summary_row = db.execute_one("SELECT created_at FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,))
    return articles, (summary_row or {}).get("created_at")


def _batch_load_cluster_alert_materials(cluster_ids):
    if not cluster_ids:
        return {}
    cluster_id_tuple = tuple(cluster_ids)
    articles_by_cluster = {}
    rows = db.execute(
        "SELECT title, description, source, link, created_at, category, topic, cluster_id FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
        (cluster_id_tuple,),
    )
    for row in rows or []:
        cid = str(row.get("cluster_id") or "")
        if cid not in articles_by_cluster:
            articles_by_cluster[cid] = []
        articles_by_cluster[cid].append(row)
    for cid in articles_by_cluster:
        articles_by_cluster[cid] = articles_by_cluster[cid][:8]
    summary_rows = db.execute(
        "SELECT cluster_id, created_at FROM cluster_summaries WHERE cluster_id = ANY(%s)", (cluster_id_tuple,)
    )
    summaries_by_cluster = {str(row.get("cluster_id") or ""): row.get("created_at") for row in summary_rows or []}
    return {
        str(cid): {
            "articles": articles_by_cluster.get(str(cid), []),
            "summary_date": summaries_by_cluster.get(str(cid)),
        }
        for cid in cluster_ids
    }


def _classify_alert_candidate(
    cluster, freshness, matched_topics, matched_sources, delivery_performance=None, target_performance=None
):
    reasons = freshness.get("reasons") or []
    freshness_score = float(freshness.get("freshness_score") or 0.0)
    base_score = float(cluster.get("score") or 0.0)
    delivery_performance = delivery_performance or {}
    target_performance = target_performance or {}
    breaking_perf = delivery_performance.get("breaking") or {}
    breaking_sends = int(breaking_perf.get("sends") or 0)
    breaking_open_rate = float(breaking_perf.get("open_rate") or 0.0)
    breaking_click_rate = float(breaking_perf.get("click_rate") or 0.0)
    alert_label = "Vazno azuriranje"
    alert_reason = cluster.get("match_reason") or "ova prica silno se vrzuva so vasite sledeni temi ili izvori"
    alert_tags = "newspaper"
    min_gap_minutes = 90
    topic_gap_minutes = 240
    source_gap_minutes = 180
    severity_rank = 1
    score_adjustment = 0.0
    engagement_label = "Normalen odziv"
    if "credible_new_reporting" in reasons or "new_sources" in reasons or base_score >= BREAKING_SCORE_THRESHOLD + 1.4:
        alert_label = "Itno azuriranje"
        alert_reason = "se pojavi nov doverliv izvor ili znacaen razvoj"
        alert_tags = "rotating_light,newspaper"
        min_gap_minutes = 30
        topic_gap_minutes = 120
        source_gap_minutes = 90
        severity_rank = 3
    elif "new_numbers" in reasons or "new_angle" in reasons or freshness_score >= 1.8:
        alert_label = "nova vazna promena"
        alert_reason = "ima nov ugao, brojki ili pojasna promena vo izvestaj"
        alert_tags = "newspaper,warning"
        min_gap_minutes = 60
        topic_gap_minutes = 180
        source_gap_minutes = 150
        severity_rank = 2
    elif "multiple_new_reports" in reasons:
        alert_label = "Sleden razvoj"
        alert_reason = "se natrupuvaat povece novi izvestai okolu istata prica"
        alert_tags = "newspaper"
        min_gap_minutes = 120
        topic_gap_minutes = 360
        source_gap_minutes = 240
    if breaking_sends >= 8 and breaking_click_rate < 0.12 and breaking_open_rate < 0.35:
        engagement_label = "Slab odziv"
        min_gap_minutes += 75
        topic_gap_minutes += 180
        source_gap_minutes += 120
        if severity_rank < 3:
            score_adjustment -= 0.45
            alert_reason = f"{alert_reason}; pracame samo posilni azuriranja dodeka odzivot e nizok"
    elif breaking_sends >= 6 and (breaking_click_rate >= 0.22 or breaking_open_rate >= 0.58):
        engagement_label = "Silen odziv"
        min_gap_minutes = max(20, min_gap_minutes - 15)
        topic_gap_minutes = max(90, topic_gap_minutes - 45)
        source_gap_minutes = max(75, source_gap_minutes - 30)
        if severity_rank >= 2:
            score_adjustment += 0.25
            alert_reason = f"{alert_reason}; vakvi azuriranja i prethodno dobivaa silen odziv"
    topic_perf = target_performance.get("topics") or {}
    source_perf = target_performance.get("sources") or {}
    topic_rates = [topic_perf.get(t) for t in matched_topics or [] if topic_perf.get(t)]
    source_rates = [source_perf.get(s) for s in matched_sources or [] if source_perf.get(s)]
    if any(
        int(i.get("sends") or 0) >= 2
        and (float(i.get("click_rate") or 0.0) >= 0.22 or float(i.get("open_rate") or 0.0) >= 0.65)
        for i in topic_rates + source_rates
    ):
        engagement_label = "Silen odziv za sledenoto"
        min_gap_minutes = max(20, min_gap_minutes - 15)
        topic_gap_minutes = max(75, topic_gap_minutes - 60)
        source_gap_minutes = max(60, source_gap_minutes - 45)
        score_adjustment += 0.3
        alert_reason = f"{alert_reason}; ova tema ili izvor prethodno dobivale silen odziv"
    elif (
        any(
            int(i.get("sends") or 0) >= 3
            and float(i.get("open_rate") or 0.0) < 0.2
            and float(i.get("click_rate") or 0.0) == 0.0
            for i in topic_rates + source_rates
        )
        and severity_rank < 3
    ):
        engagement_label = "Slab odziv za sledenoto"
        min_gap_minutes += 60
        topic_gap_minutes += 120
        source_gap_minutes += 120
        score_adjustment -= 0.35
        alert_reason = f"{alert_reason}; ova tema ili izvor prethodno imale slab odziv"
    throttle_keys = [f"cluster:{str(cluster.get('cluster_id') or '').strip()}"]
    throttle_keys.extend(f"topic:{t}" for t in matched_topics[:2])
    throttle_keys.extend(f"source:{s}" for s in matched_sources[:2])
    return {
        "alert_label": alert_label,
        "alert_reason": alert_reason,
        "alert_tags": alert_tags,
        "min_gap_minutes": min_gap_minutes,
        "topic_gap_minutes": topic_gap_minutes,
        "source_gap_minutes": source_gap_minutes,
        "throttle_keys": throttle_keys,
        "engagement_label": engagement_label,
        "score_adjustment": score_adjustment,
    }


def _alert_throttled(last_breaking_sent_at, alert_context, candidate):
    last_global = _parse_row_datetime(last_breaking_sent_at)
    now = datetime.datetime.now(datetime.timezone.utc)
    if last_global:
        if last_global.tzinfo is None:
            last_global = last_global.replace(tzinfo=datetime.timezone.utc)
        if (now - last_global.astimezone(datetime.timezone.utc)).total_seconds() / 60.0 < candidate["min_gap_minutes"]:
            return True
    context = _normalize_alert_context(alert_context)
    for key in candidate["throttle_keys"]:
        last_value = _parse_row_datetime(context.get(key))
        if not last_value:
            continue
        if last_value.tzinfo is None:
            last_value = last_value.replace(tzinfo=datetime.timezone.utc)
        age_minutes = (now - last_value.astimezone(datetime.timezone.utc)).total_seconds() / 60.0
        if key.startswith("cluster:") and age_minutes < max(180, candidate["min_gap_minutes"] * 2):
            return True
        if key.startswith("topic:") and age_minutes < candidate["topic_gap_minutes"]:
            return True
        if key.startswith("source:") and age_minutes < candidate["source_gap_minutes"]:
            return True
    return False


def _select_breaking_cluster_for_profile(
    profile,
    seen_cluster_ids,
    alert_context=None,
    last_breaking_sent_at=None,
    *,
    include_topics=True,
    include_sources=True,
    _cached_clusters=None,
    _cached_materials=None,
    _cached_delivery_perf=None,
    _cached_target_perf=None,
):
    profile = _normalize_synced_profile_for_delivery(profile)
    seen = {str(item or "").strip() for item in seen_cluster_ids or [] if str(item or "").strip()}
    delivery_perf = _cached_delivery_perf if _cached_delivery_perf is not None else _load_delivery_kind_performance()
    target_perf = _cached_target_perf if _cached_target_perf is not None else _load_breaking_target_performance()
    candidates = []
    clusters = _cached_clusters if _cached_clusters is not None else _load_recent_breaking_clusters()
    for cluster in clusters:
        cluster_id = str(cluster.get("cluster_id") or "").strip()
        if not cluster_id:
            continue
        match_score, reasons, matched_topics, matched_sources = _cluster_delivery_match(
            cluster, profile, include_topics=include_topics, include_sources=include_sources
        )
        if match_score < 2.0:
            continue
        if _cached_materials and cluster_id in _cached_materials:
            articles = _cached_materials[cluster_id]["articles"]
            synthesis_created_at = _cached_materials[cluster_id]["summary_date"]
        else:
            articles, synthesis_created_at = _load_cluster_alert_material(cluster_id)
        freshness = assess_cluster_synthesis_freshness(articles, synthesis_created_at)
        alert_meta = _classify_alert_candidate(
            cluster, freshness, matched_topics, matched_sources, delivery_perf, target_perf
        )
        if cluster_id in seen and not freshness.get("refresh_needed"):
            continue
        candidates.append(
            {
                **cluster,
                "match_score": (
                    match_score
                    + min(1.5, float(cluster.get("score") or 0) * 0.15)
                    + min(1.2, float(freshness.get("freshness_score") or 0.0) * 0.4)
                    + float(alert_meta.get("score_adjustment") or 0.0)
                ),
                "match_reason": "; ".join(reasons[:2]),
                "matched_topics": matched_topics[:2],
                "matched_sources": matched_sources[:2],
                "freshness": freshness,
                **alert_meta,
            }
        )
    candidates.sort(key=lambda item: item["match_score"], reverse=True)
    for candidate in candidates:
        if not _alert_throttled(last_breaking_sent_at, alert_context, candidate):
            return candidate
    return None


@celery_app.task
def generate_daily_brief_task(retry_attempt=0, lang="sr"):
    now = datetime.datetime.now()
    lock_key = f"lock:daily_brief:{lang}:{now.date()}"
    try:
        if not redis_client.set(lock_key, "1", nx=True, ex=7200):
            log.info(f"Daily brief ({lang}) generation already in progress or completed for today.")
            return
    except Exception as e:
        log.warning(f"Redis lock check failed for daily brief: {e}")
    try:
        from tasks.utils import record_task_event

        country_filter = "RS" if lang == "sr" else "MK"
        total_24h = (
            db.execute_one(
                "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND country = %s",
                (country_filter,),
            )["count"]
            or 1
        )
        intl_24h = (
            db.execute_one(
                "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND is_global = TRUE AND country = %s",
                (country_filter,),
            )["count"]
            or 0
        )
        intl_pct = round((intl_24h / total_24h) * 100) if total_24h > 0 else 0
        balance_stats = db.execute_one(
            """WITH cluster_tiers AS (SELECT cluster_id, COUNT(DISTINCT CASE WHEN s.category IN ('Agencijski', 'Javni servis', 'glavni') THEN 'M' WHEN s.category IN ('Nezavisni', 'Istraživački') THEN 'I' ELSE 'R' END) as group_count FROM articles a JOIN sources s ON a.source = s.name WHERE a.created_at >= NOW() - INTERVAL '24 hours' AND a.country = %s GROUP BY cluster_id) SELECT COUNT(*) FILTER (WHERE group_count >= 2) as diverse FROM cluster_tiers""",
            (country_filter,),
        )
        diverse_pct = round((balance_stats["diverse"] / total_24h) * 100) if total_24h > 0 else 0
        subjects_rows = db.execute(
            "SELECT topic, COUNT(*) as c FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND country = %s AND topic IS NOT NULL GROUP BY topic ORDER BY c DESC LIMIT 3",
            (country_filter,),
        )
        top_subjects = ", ".join([r["topic"] for r in subjects_rows])
        top_locations = "Balkan"

        # Consistent daily naming
        dispatch_name = "Dnevni brifing" if lang == "sr" else "Дневен брифинг"

        clusters = _load_daily_brief_clusters(limit=10, lang=lang)
        content_context = _build_daily_brief_context(clusters)
        system_insight = f"\n\n[SISTEMSKA ANALIZA ZA POSLEDNJIH 24 SATA]\n- Obradjeni clanci: {total_24h}\n- Udeo svetskih vest: {intl_pct}%\n- Indeks pluralizma (raznovrsni izvori): {diverse_pct}%\n- Najzastupljeni akteri: {top_subjects or 'Nema'}\n- U focusu lokacije: {top_locations or 'Nema'}\n- Naziv izvestaja: {dispatch_name}"
        
        # Chronological RAG context loop
        history_context = ""
        try:
            prev_brief = db.execute_one(
                "SELECT content FROM daily_briefings WHERE lang = %s AND date >= CURRENT_DATE - INTERVAL '48 hours' AND date < CURRENT_DATE ORDER BY date DESC LIMIT 1",
                (lang,),
            )
            if prev_brief and prev_brief.get("content"):
                if lang == "sr":
                    history_context = (
                        "\n\n[ISTORIJSKI KONTEKST - BRITING OD PRETHODNOG DANA]\n"
                        "Iskoristi ovaj prethodni brifing kao kontekst da bi stvorio hronološki povezan narativ. "
                        "Poveži današnje vesti sa jučerašnjim tamo gde je to relevantno (npr. 'Nastavljajući se na jučerašnji razvoj...', 'Kao što je juče najavljeno...'):\n"
                        f"<previous_briefing>\n{prev_brief['content'][:2500]}\n</previous_briefing>\n"
                    )
                else:
                    history_context = (
                        "\n\n[ИСТОРИСКИ КОНТЕКСТ - БРИФИНГ ОД ПРЕТХОДНИОТ ДЕН]\n"
                        "Искористи го овој претходен брифинг како контекст за да создадеш хронолошки поврзан наратив. "
                        "Поврзи ги денешните вести со вчерашните таму каде што е тоа релевантно (на пр. 'Надоврзувајќи се на вчерашниот развој...', 'Како што вчера беше најавено...'):\n"
                        f"<previous_briefing>\n{prev_brief['content'][:2500]}\n</previous_briefing>\n"
                    )
        except Exception as e:
            log.warning(f"Failed to fetch historical briefing context: {e}")

        full_context = f"<briefing_context>\n{content_context}\n{system_insight}\n{history_context}\n</briefing_context>"
        prompt = DAILY_BRIEF_SYSTEM_PROMPT if lang == "sr" else DAILY_BRIEF_SYSTEM_PROMPT_MK
        brief, _ = _call_ai(full_context, prompt, task_type="daily_brief", max_tokens=4000)
        if brief and (
            not _has_valid_daily_brief_structure(brief, lang=lang)
            or not _is_grounded_daily_brief(brief, full_context)
            or not _is_high_quality_briefing(brief)
        ):
            log.warning(f"[tasks] Daily brief ({lang}) rejected; using local fallback.")
            brief = ""
        final_brief = brief or generate_daily_brief_fallback(clusters)
        if final_brief:
            if brief and not final_brief.startswith("#"):
                final_brief = f"# {dispatch_name}\n\n" + final_brief

            # Phase 1: Extract structured metadata for Intelligence Report 2.0
            metadata = {
                "model": "Gemma 2 / Mistral-Nemo",
                "stats": {"total_articles": total_24h, "intl_share": intl_pct, "pluralism_score": diverse_pct},
                "key_narratives": [],
            }

            # Use AI to extract 3 key narratives from the final brief
            try:
                narrative_prompt = (
                    (
                        "Izvuci 3 najvaznija narativa iz ovog brifinga. "
                        "Za svaki narativ napisi kratku recenicu i dodeli sentiment (POZITIVAN, NEUTRALAN, KRITIČAN). "
                        "Vrati ISKLJUČIVO validan JSON niz objekata:\n"
                        '[{"text": "...", "sentiment": "POZITIVAN"}, ...]'
                    )
                    if lang == "sr"
                    else (
                        "Извлечи 3 најважни наративи од овој брифинг. "
                        "За секој наратив напиши кратка реченица и додели сентимент (ПОЗИТИВЕН, НЕУТРАЛЕН, КРИТИЧЕН). "
                        "Врати ИСКЛУЧИВО валидна JSON низа од објекти:\n"
                        '[{"text": "...", "sentiment": "ПОЗИТИВЕН"}, ...]'
                    )
                )

                nar_raw, _ = _call_ai(
                    f"<briefing>\n{final_brief}\n</briefing>", narrative_prompt, task_type="extraction", max_tokens=1000
                )

                if nar_raw:
                    # Clean potential markdown
                    nar_clean = nar_raw.strip().replace("```json", "").replace("```", "")
                    metadata["key_narratives"] = json.loads(nar_clean)
            except Exception as e:
                log.warning(f"[tasks] Narrative extraction failed: {e}")

            db.execute(
                "INSERT INTO daily_briefings (date, content, lang, metadata) VALUES (CURRENT_DATE, %s, %s, %s) "
                "ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content, metadata = EXCLUDED.metadata",
                (final_brief, lang, json.dumps(metadata)),
                fetch=False,
            )
            delete_cache(f"daily_brief:latest:{lang}")
            record_task_event("daily_brief", "ok" if brief else "fallback", f"lang:{lang}")

            # Automatically pre-generate the briefing audio in the background
            try:
                from core.audio_service import AudioService
                target_date = datetime.date.today().isoformat()
                log.info(f"[tasks] Auto-generating OmniVoice briefing audio in background for {target_date} ({lang})...")
                AudioService.generate_briefing_audio(target_date, final_brief, lang)
            except Exception as audio_err:
                log.error(f"[tasks] Failed to auto-generate briefing audio for {target_date} ({lang}): {audio_err}")
            if not brief and retry_attempt < 2:
                generate_daily_brief_task.apply_async(
                    kwargs={"retry_attempt": retry_attempt + 1, "lang": lang}, countdown=1800
                )
    except Exception as e:
        clusters = _load_daily_brief_clusters(limit=6, lang="sr")
        fallback = generate_daily_brief_fallback(clusters)
        if fallback:
            db.execute(
                "INSERT INTO daily_briefings (date, content, lang, metadata) VALUES (CURRENT_DATE, %s, %s, %s) "
                "ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content, metadata = EXCLUDED.metadata",
                (fallback, lang, json.dumps({"is_fallback": True})),
                fetch=False,
            )

            # Automatically pre-generate the briefing audio (fallback) in the background
            try:
                from core.audio_service import AudioService
                target_date = datetime.date.today().isoformat()
                log.info(f"[tasks] Auto-generating OmniVoice briefing audio in background (fallback) for {target_date} ({lang})...")
                AudioService.generate_briefing_audio(target_date, fallback, lang)
            except Exception as audio_err:
                log.error(f"[tasks] Failed to auto-generate briefing audio for {target_date} ({lang}): {audio_err}")
            if retry_attempt < 2:
                generate_daily_brief_task.apply_async(
                    kwargs={"retry_attempt": retry_attempt + 1, "lang": lang}, countdown=1800
                )
        else:
            from tasks.utils import record_task_event

            record_task_event("daily_brief", "error", f"lang:{lang}")
            log.error(f"[tasks] Daily brief ({lang}) failed: {e}")


@celery_app.task
def generate_all_daily_briefs_task():
    generate_daily_brief_task.apply_async(args=(0, "sr"))
    generate_daily_brief_task.apply_async(args=(0, "mk"))


@celery_app.task
def send_profile_briefings_task():
    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0
    try:
        rows = _load_active_delivery_rows()
        cached_clusters = {
            "sr": _load_daily_brief_clusters(limit=18, lang="sr"),
            "mk": _load_daily_brief_clusters(limit=18, lang="mk"),
        }
        for row in rows:
            if not row.get("morning_briefing"):
                continue
            last_sent = _parse_row_datetime(row.get("last_morning_sent_at"))
            if last_sent and last_sent.date() == now.date():
                continue
            target = str(row.get("target") or NTFY_TOPIC).strip()
            locale = row.get("locale") or "sr"
            conf = _LOCALIZED_DELIVERY.get(locale, _LOCALIZED_DELIVERY["sr"])
            profile = _normalize_synced_profile_for_delivery(row.get("profile_data") or {})
            clusters = _select_profile_brief_clusters(
                profile, _cached_clusters=cached_clusters.get(locale, cached_clusters["sr"])
            )
            if not clusters:
                continue
            message = _build_profile_briefing_message(profile, clusters, locale=locale)
            if not message:
                continue
            primary_cluster_id = str((clusters[0] or {}).get("cluster_id") or "").strip() or None
            send_event_id = _record_delivery_tracking_event(
                row["sync_token"],
                "send",
                "morning",
                target=target,
                cluster_id=primary_cluster_id,
                metadata={
                    "cluster_ids": [
                        str(item.get("cluster_id") or "").strip()
                        for item in clusters[:4]
                        if str(item.get("cluster_id") or "").strip()
                    ]
                },
            )
            click_url = _tracked_delivery_url(send_event_id, "open", "/briefing") if send_event_id else None
            click_track_url = _tracked_delivery_url(send_event_id, "click", "/briefing") if send_event_id else None
            message_with_link = (
                message if not click_track_url else f"{message}\n\n{conf['read_briefing']}: {click_track_url}"
            )
            if _send_ntfy_message(
                target, conf["ntfy_title"], message_with_link, tags="newspaper,sunrise", click_url=click_url
            ):
                db.execute(
                    "UPDATE synced_delivery_subscriptions SET last_morning_sent_at = NOW(), updated_at = NOW() WHERE sync_token = %s",
                    (row["sync_token"],),
                    fetch=False,
                )
                sent += 1
    except Exception as e:
        log.warning(f"[tasks] Profile briefings failed: {e}")
    else:
        if sent:
            log.info(f"[tasks] Sent {sent} scheduled profile briefings.")


@celery_app.task
def send_profile_breaking_alerts_task():
    if not acquire_task_lock(_BREAKING_ALERT_TASK_LOCK, ttl_seconds=_BREAKING_ALERT_LOCK_TTL):
        log.info("[tasks] Skipping breaking alerts run because another run is already active.")
        return
    sent = 0
    try:
        if get_celery_queue_depth() >= _BREAKING_ALERT_QUEUE_DEPTH_LIMIT:
            log.info("[tasks] Skipping breaking alerts run while queue backlog is high.")
            return
        rows = _load_active_delivery_rows()
        all_breaking_clusters = _load_recent_breaking_clusters()
        delivery_performance = _load_delivery_kind_performance()
        target_performance = _load_breaking_target_performance()
        cluster_ids = [str(c.get("cluster_id") or "").strip() for c in all_breaking_clusters if c.get("cluster_id")]
        alert_materials = _batch_load_cluster_alert_materials(cluster_ids) if cluster_ids else {}
        for row in rows:
            if not row.get("breaking_topics") and not row.get("breaking_sources"):
                continue
            target = str(row.get("target") or NTFY_TOPIC).strip()
            profile = _normalize_synced_profile_for_delivery(row.get("profile_data") or {})
            existing_ids = row.get("last_alert_cluster_ids") or []
            candidate = _select_breaking_cluster_for_profile(
                profile,
                existing_ids,
                alert_context=row.get("last_alert_context"),
                last_breaking_sent_at=row.get("last_breaking_sent_at"),
                include_topics=bool(row.get("breaking_topics")),
                include_sources=bool(row.get("breaking_sources")),
                _cached_clusters=all_breaking_clusters,
                _cached_materials=alert_materials,
                _cached_delivery_perf=delivery_performance,
                _cached_target_perf=target_performance,
            )
            if not candidate:
                continue
            alert_lock_key = f"lock:alert:{row['sync_token']}:{candidate['cluster_id']}"
            if not redis_client.set(alert_lock_key, "1", nx=True, ex=3600):
                continue
            title = f"Presek · {candidate.get('alert_label') or 'Vazno azuriranje'}"
            message_lines = [
                candidate.get("title") or "nova vazna razvojna linija",
                f"{candidate.get('source') or 'izvor'} · {candidate.get('source_count') or 1} izvori",
            ]
            why_now = candidate.get("alert_reason") or candidate.get("match_reason")
            if why_now:
                message_lines.append(f"Zosto sega: {why_now}")
            if candidate.get("match_reason"):
                message_lines.append(f"Zosto ga dobivate ova: {candidate['match_reason']}")
            if candidate.get("cluster_summary"):
                message_lines.append(str(candidate["cluster_summary"]).splitlines()[0][:240])
            elif candidate.get("description"):
                message_lines.append(str(candidate["description"])[:240])
            if candidate.get("difference_point"):
                message_lines.append(f"Razlika: {str(candidate['difference_point'])[:180]}")
            elif candidate.get("open_point"):
                message_lines.append(f"otvoreno: {str(candidate['open_point'])[:180]}")
            cluster_id = str(candidate.get("cluster_id") or "").strip() or None
            send_event_id = _record_delivery_tracking_event(
                row["sync_token"],
                "send",
                "breaking",
                target=target,
                cluster_id=cluster_id,
                metadata={
                    "matched_topics": candidate.get("matched_topics") or [],
                    "matched_sources": candidate.get("matched_sources") or [],
                    "label": candidate.get("alert_label") or "",
                },
            )
            open_url = (
                _tracked_delivery_url(send_event_id, "open", f"/cluster/{cluster_id}")
                if send_event_id and cluster_id
                else (_tracked_delivery_url(send_event_id, "open", "/briefing") if send_event_id else None)
            )
            click_track_url = (
                _tracked_delivery_url(send_event_id, "click", f"/cluster/{cluster_id}")
                if send_event_id and cluster_id
                else (_tracked_delivery_url(send_event_id, "click", "/briefing") if send_event_id else None)
            )
            message_text = "\n".join(message_lines)
            if click_track_url:
                message_text = f"{message_text}\nOtvori klaster: {click_track_url}"
            delivery_channel = str(row.get("channel") or "ntfy").strip().lower()
            sent_success = False
            if delivery_channel == "webpush":
                sent_success = _send_web_push_message(target, title, message_text, click_url=open_url)
            else:
                sent_success = _send_ntfy_message(
                    target, title, message_text, tags=candidate.get("alert_tags") or "newspaper", click_url=open_url
                )
            if sent_success:
                next_ids = [str(candidate.get("cluster_id") or "").strip()]
                next_ids.extend(
                    str(item or "").strip()
                    for item in existing_ids
                    if str(item or "").strip()
                    and str(item or "").strip() != str(candidate.get("cluster_id") or "").strip()
                )
                next_context = _next_alert_context(row.get("last_alert_context"), candidate)
                db.execute(
                    "UPDATE synced_delivery_subscriptions SET last_breaking_sent_at = NOW(), last_alert_cluster_ids = %s::jsonb, last_alert_context = %s::jsonb, updated_at = NOW() WHERE sync_token = %s",
                    (json.dumps(next_ids[:24]), json.dumps(next_context), row["sync_token"]),
                    fetch=False,
                )
                sent += 1
    except Exception as e:
        log.warning(f"[tasks] Profile breaking alerts failed: {e}")
    else:
        if sent:
            log.info(f"[tasks] Sent {sent} profile breaking alerts.")
    finally:
        release_task_lock(_BREAKING_ALERT_TASK_LOCK)
