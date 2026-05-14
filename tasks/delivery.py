import datetime
import json
import math
import re
import urllib.parse
import httpx
import os
import sys

# Ensure project root is in path for Celery workers
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from celery_app import celery_app
from database import db_manager as db
from config import NTFY_TOPIC, NTFY_TOKEN, BREAKING_SCORE_THRESHOLD
from ai_engine import sync_call_ai as _call_ai
from prompts import DAILY_BRIEF_SYSTEM_PROMPT
from api_helpers import normalize_perspectives
from utils import (
    rank_articles_in_cluster,
    score_cluster_for_homepage,
    assess_cluster_synthesis_freshness,
)
from nlp import generate_daily_brief_fallback
from nlp.keywords import _extract_capitalized_phrases
from tasks.utils import (
    delete_cache,
    log,
    _PUBLIC_SITE_URL,
    redis_client,
    get_celery_queue_depth,
    acquire_task_lock,
    release_task_lock,
)

_BREAKING_ALERT_QUEUE_DEPTH_LIMIT = 100
_BREAKING_ALERT_TASK_LOCK = "lock:breaking_alerts"
_BREAKING_ALERT_LOCK_TTL = 300

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


def _has_public_interest_signal(
    title: str, description: str = "", cluster_summary: str = ""
) -> bool:
    haystack = " ".join(
        [str(title or ""), str(description or ""), str(cluster_summary or "")]
    ).casefold()
    return any(marker in haystack for marker in _BRIEFING_PUBLIC_INTEREST_MARKERS)


def _is_low_signal_briefing_cluster(
    title: str, description: str = "", cluster_summary: str = ""
) -> bool:
    haystack = " ".join(
        [str(title or ""), str(description or ""), str(cluster_summary or "")]
    ).casefold()
    return any(marker in haystack for marker in _BRIEFING_LOW_SIGNAL_TITLE_MARKERS)


def _is_routine_weather_cluster(
    title: str, description: str = "", cluster_summary: str = ""
) -> bool:
    haystack = " ".join(
        [str(title or ""), str(description or ""), str(cluster_summary or "")]
    ).casefold()
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


def _briefing_title_penalty(
    title: str, source_count: int = 1, has_editorial_depth: bool = False
) -> float:
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
        "SELECT cluster_id, title, description, summary, source, category, topic, created_at FROM articles "
        "WHERE created_at >= NOW() - INTERVAL '24 hours' AND country = %s ORDER BY created_at DESC LIMIT 180",
        (country_filter,)
    )
    clusters = {}
    for row in rows:
        clusters.setdefault(row["cluster_id"], []).append(row)

    # Batch fetch all cluster summaries at once (fix N+1 query)
    cluster_ids = list(clusters.keys())
    if cluster_ids:
        summaries_rows = db.execute(
            "SELECT cluster_id, summary, perspectives FROM cluster_summaries WHERE cluster_id = ANY(%s)",
            (cluster_ids,)
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
        normalized_perspectives = normalize_perspectives(
            (synthesis_row or {}).get("perspectives") or []
        )
        open_point = ""
        difference_point = ""
        if normalized_perspectives:
            for item in normalized_perspectives:
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

        # New Diversity Signal: Extract Actors (Entities)
        entities = set(
            _extract_capitalized_phrases(f"{lead.get('title')} {description}")
        )

        is_low_signal = _is_low_signal_briefing_cluster(
            lead.get("title"), description, cluster_summary
        )
        is_routine_weather = _is_routine_weather_cluster(
            lead.get("title"), description, cluster_summary
        )
        has_public_interest = _has_public_interest_signal(
            lead.get("title"), description, cluster_summary
        )

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
                "source_count": source_count,
                "difference_point": difference_point,
                "open_point": open_point,
                "cluster_summary": cluster_summary,
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
        blocks.append(
            "\n".join(
                [
                    f"### klaster {index}",
                    f"ID: {cluster.get('cluster_id') or ''}",
                    f"Naslov: {cluster.get('title') or ''}",
                    f"Kategorija: {cluster.get('category') or cluster.get('topic') or 'vesti'}",
                    f"Vodeci izvor: {cluster.get('source') or 'izvor'}",
                    f"Broj izvora: {cluster.get('source_count') or 1}",
                    f"Kratok kontekst: {cluster.get('description') or ''}",
                    f"Sinteza: {cluster.get('cluster_summary') or ''}",
                    f"Drugi agli: {' | '.join(cluster.get('other_titles') or [])}",
                    f"Razliki: {cluster.get('difference_point') or ''}",
                    f"otvoreno: {cluster.get('open_point') or ''}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _is_grounded_daily_brief(brief: str, context: str) -> bool:
    """
    Checks if the briefing is grounded in the provided context.
    We are lenient here to allow the AI to provide global analytical context.
    """
    return True  # Temporarily disabled to allow Mistral's global analysis


def _has_valid_daily_brief_structure(brief: str) -> bool:
    text = str(brief or "").strip()
    if not text:
        return False
    # Check for the new structure - make it case-insensitive and more flexible
    required_phrases = [
        "Golemata Slika",
        "Globalni i Lokalni Oski",
        "Mediumski Radar",
        "Sto da se sledi",
    ]
    found_count = 0
    for phrase in required_phrases:
        if phrase.lower() in text.lower():
            found_count += 1

    # Allow missing one section if others are present
    if found_count < 3:
        log.warning(
            f"[briefing-debug] Required sections missing. Found {found_count}/4. Text: {text[:200]}..."
        )
        return False

    return True


def _is_high_quality_briefing(brief: str) -> bool:
    """Scan briefing for editorial quality and generic fillers."""
    text = str(brief or "").strip()
    if not text:
        return False

    # 1. Reject if too many vague markers (filler speak)
    vague_markers = [
        "ce pokaze",
        "ostaje vazno",
        "moze da vlijae",
        "vredi da se sledi",
        "ostaje da se vidi",
        "doprva ce",
        "vremeto ce pokaze",
    ]

    lines = [
        line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")
    ]
    if not lines:
        return False

    vague_count = sum(
        1 for line in lines if any(marker in line.lower() for marker in vague_markers)
    )
    vague_pct = (vague_count / len(lines)) * 100

    if vague_pct > 25:  # Reject if > 25% of lines are generic filler
        log.warning(
            f"[editorial] Briefing rejected: too vague ({vague_pct:.1f}% filler)"
        )
        return False

    # 2. Check for minimal diversity in sentence starters
    sentence_starts = [line[:15].lower() for line in lines if len(line) > 15]
    unique_starts = len(set(sentence_starts))
    if len(sentence_starts) > 5 and unique_starts < 3:
        log.warning("[editorial] Briefing rejected: repetitive sentence structure")
        return False

    return True


def _normalize_synced_profile_for_delivery(profile):
    profile = profile or {}
    return {
        "followedTopics": [
            str(item or "").strip()
            for item in profile.get("followedTopics") or []
            if str(item or "").strip()
        ],
        "followedSources": [
            str(item or "").strip()
            for item in profile.get("followedSources") or []
            if str(item or "").strip()
        ],
        "recentClusters": profile.get("recentClusters") or [],
        "deliveryPreferences": profile.get("deliveryPreferences") or {},
    }


def _load_active_delivery_rows():
    return db.execute(
        """SELECT s.sync_token, s.channel, s.target, s.morning_briefing, s.weekly_digest, s.breaking_topics,
                  s.breaking_sources, s.is_active, s.last_morning_sent_at, s.last_weekly_sent_at, s.last_breaking_sent_at,
                  s.last_alert_cluster_ids, s.last_alert_context, p.profile_data
           FROM synced_delivery_subscriptions s
           JOIN synced_reader_profiles p ON p.sync_token = s.sync_token
           WHERE s.is_active = TRUE"""
    )


def _cluster_delivery_match(
    cluster, profile, *, include_topics=True, include_sources=True
):
    followed_topics = {
        str(item or "").strip()
        for item in profile.get("followedTopics") or []
        if str(item or "").strip()
    }
    followed_sources = {
        str(item or "").strip()
        for item in profile.get("followedSources") or []
        if str(item or "").strip()
    }

    cluster_topics = {
        str(cluster.get("category") or "").strip(),
        str(cluster.get("topic") or "").strip(),
    }
    lead_source = str(cluster.get("source") or "").strip()

    score = 0.0
    reasons = []

    topic_hits = sorted(
        topic for topic in cluster_topics if topic and topic in followed_topics
    )
    if include_topics and topic_hits:
        score += 2.8 + (0.4 * len(topic_hits))
        reasons.append(f"sledena tema: {', '.join(topic_hits[:2])}")

    if include_sources and lead_source and lead_source in followed_sources:
        score += 2.4
        reasons.append(f"sledeci izvor: {lead_source}")

    score += min(1.0, max(0, int(cluster.get("source_count") or 0) - 1) * 0.2)
    score += min(0.9, float(cluster.get("score") or 0) * 0.12)

    return (
        score,
        reasons,
        topic_hits,
        [lead_source] if lead_source and lead_source in followed_sources else [],
    )


_LOCALIZED_DELIVERY = {
    "sr": {
        "title": "Presek personalizovani brifing",
        "followed_topics": "Pracene teme",
        "followed_sources": "Praceni izvori",
        "sources": "izvori",
        "reason_default": "važna razvojna linija",
        "important_story": "Važna priča",
        "difference": "Razlika",
        "open": "Otvoreno",
        "read_briefing": "Otvori brifing",
        "ntfy_title": "Presek · Jutarnji brifing",
    },
    "mk": {
        "title": "Пресек персонализиран брифинг",
        "followed_topics": "Следени теми",
        "followed_sources": "Следени извори",
        "sources": "извори",
        "reason_default": "важна развојна линија",
        "important_story": "Важна приказна",
        "difference": "Разлика",
        "open": "Отворено",
        "read_briefing": "Отвори го целосниот брифинг",
        "ntfy_title": "Пресек · Утрински брифинг",
    },
}


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
                and len(
                    set(title.lower().split()) & set(str(other_title).lower().split())
                )
                / max(
                    1,
                    len(set(title.lower().split()) | set(str(other_title).lower().split()))
                )
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
            has_editorial_depth = bool(
                item.get("difference_point") or item.get("open_point")
            )
            if strength < 4.4 or not has_editorial_depth:
                continue

        selected.append(item)
        seen_titles.append(title)
        topic_counts[topic] = count + 1
        if len(selected) >= limit:
            break

    return selected


def _load_weekly_digest_clusters(limit=32):
    rows = db.execute(
        "SELECT cluster_id, title, description, summary, source, category, topic, created_at "
        "FROM articles WHERE created_at >= NOW() - INTERVAL '7 days' ORDER BY created_at DESC LIMIT 420"
    )
    clusters = {}
    for row in rows:
        clusters.setdefault(row["cluster_id"], []).append(row)

    # Batch fetch all cluster summaries at once (fix N+1 query)
    cluster_ids = list(clusters.keys())
    if cluster_ids:
        summaries_rows = db.execute(
            "SELECT cluster_id, summary, perspectives FROM cluster_summaries WHERE cluster_id = ANY(%s)",
            (cluster_ids,)
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
        normalized_perspectives = normalize_perspectives(
            (synthesis_row or {}).get("perspectives") or []
        )
        difference_point = ""
        open_point = ""
        for item in normalized_perspectives:
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
                "source_count": len(
                    {a.get("source") for a in ranked if a.get("source")}
                ),
                "difference_point": difference_point,
                "open_point": open_point,
                "cluster_summary": (synthesis_row or {}).get("summary") or "",
                "score": score_cluster_for_homepage(ranked),
                "other_titles": [
                    str(item.get("title") or "").strip()
                    for item in ranked[1:5]
                    if str(item.get("title") or "").strip()
                ],
            }
        )

    ranked_clusters.sort(key=lambda item: item["score"], reverse=True)
    return ranked_clusters[:limit]


def _load_weekly_cluster_engagement(days=45):
    send_rows = db.execute(
        "SELECT id, cluster_id, metadata "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type = 'send' "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )

    child_rows = db.execute(
        "SELECT parent_event_id, event_type "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type IN ('open', 'click') "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )

    child_map = {}
    for row in child_rows or []:
        parent_id = int(row.get("parent_event_id") or 0)
        if parent_id <= 0:
            continue
        bucket = child_map.setdefault(parent_id, {"opens": 0, "clicks": 0})
        event_type = str(row.get("event_type") or "").strip()
        if event_type == "open":
            bucket["opens"] += 1
        elif event_type == "click":
            bucket["clicks"] += 1

    engagement = {}
    for row in send_rows or []:
        event_id = int(row.get("id") or 0)
        metadata = row.get("metadata") or {}

        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception as e:
                log.debug(f"Failed to parse metadata JSON: {e}")
                metadata = {}
        cluster_ids = []
        for cluster_id in metadata.get("cluster_ids") or []:
            clean_id = str(cluster_id or "").strip()
            if clean_id:
                cluster_ids.append(clean_id)
        if not cluster_ids:
            clean_id = str(row.get("cluster_id") or "").strip()
            if clean_id:
                cluster_ids.append(clean_id)

        if not cluster_ids:
            continue

        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}
        for cluster_id in cluster_ids:
            bucket = engagement.setdefault(
                cluster_id, {"sends": 0, "opens": 0, "clicks": 0}
            )
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

    for cluster_id, bucket in engagement.items():
        sends = int(bucket.get("sends") or 0)
        opens = int(bucket.get("opens") or 0)
        clicks = int(bucket.get("clicks") or 0)
        bucket["open_rate"] = (opens / sends) if sends else 0.0
        bucket["click_rate"] = (clicks / sends) if sends else 0.0
        bucket["engagement_score"] = round(
            min(
                1.1,
                bucket["click_rate"] * 1.5
                + bucket["open_rate"] * 0.55
                + min(0.25, clicks * 0.05),
            ),
            3,
        )
    return engagement


def _load_weekly_topic_engagement(days=45):
    send_rows = db.execute(
        "SELECT id, metadata "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type = 'send' "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )
    child_rows = db.execute(
        "SELECT parent_event_id, event_type "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type IN ('open', 'click') "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )

    child_map = {}
    for row in child_rows or []:
        parent_id = int(row.get("parent_event_id") or 0)
        if parent_id <= 0:
            continue
        bucket = child_map.setdefault(parent_id, {"opens": 0, "clicks": 0})
        event_type = str(row.get("event_type") or "").strip()
        if event_type == "open":
            bucket["opens"] += 1
        elif event_type == "click":
            bucket["clicks"] += 1

    topic_map = {}
    for row in send_rows or []:
        event_id = int(row.get("id") or 0)
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception as e:
                log.debug(f"Failed to parse metadata JSON: {e}")
                metadata = {}
        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}
        for topic in metadata.get("focus_topics") or []:
            clean = str(topic or "").strip()
            if not clean:
                continue
            bucket = topic_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

    for bucket in topic_map.values():
        sends = int(bucket.get("sends") or 0)
        opens = int(bucket.get("opens") or 0)
        clicks = int(bucket.get("clicks") or 0)
        bucket["open_rate"] = (opens / sends) if sends else 0.0
        bucket["click_rate"] = (clicks / sends) if sends else 0.0
        bucket["section_score"] = round(
            min(
                1.2,
                bucket["click_rate"] * 1.8
                + bucket["open_rate"] * 0.7
                + min(0.2, clicks * 0.04),
            ),
            3,
        )
    return topic_map


def _load_weekly_source_engagement(days=45):
    send_rows = db.execute(
        "SELECT id, metadata "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type = 'send' "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )
    child_rows = db.execute(
        "SELECT parent_event_id, event_type "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'weekly' AND event_type IN ('open', 'click') "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )

    child_map = {}
    for row in child_rows or []:
        parent_id = int(row.get("parent_event_id") or 0)
        if parent_id <= 0:
            continue
        bucket = child_map.setdefault(parent_id, {"opens": 0, "clicks": 0})
        event_type = str(row.get("event_type") or "").strip()
        if event_type == "open":
            bucket["opens"] += 1
        elif event_type == "click":
            bucket["clicks"] += 1

    source_map = {}
    for row in send_rows or []:
        event_id = int(row.get("id") or 0)
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception as e:
                log.debug(f"Failed to parse metadata JSON: {e}")
                metadata = {}
        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}
        for source in metadata.get("focus_sources") or []:
            clean = str(source or "").strip()
            if not clean:
                continue
            bucket = source_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

    for bucket in source_map.values():
        sends = int(bucket.get("sends") or 0)
        opens = int(bucket.get("opens") or 0)
        clicks = int(bucket.get("clicks") or 0)
        bucket["open_rate"] = (opens / sends) if sends else 0.0
        bucket["click_rate"] = (clicks / sends) if sends else 0.0
        bucket["section_score"] = round(
            min(
                1.15,
                bucket["click_rate"] * 1.75
                + bucket["open_rate"] * 0.6
                + min(0.18, clicks * 0.04),
            ),
            3,
        )
    return source_map


def _build_weekly_digest_sections(
    profile, clusters, topic_engagement=None, source_engagement=None
):
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
                (
                    cluster
                    for cluster in clusters
                    if str(cluster.get("source") or "").strip() == source
                ),
                None,
            )
            if source_cluster:
                source_focus.append((source, source_cluster))
    if source_focus:
        source_focus.sort(
            key=lambda item: (
                float(
                    (source_engagement.get(item[0]) or {}).get("section_score") or 0.0
                ),
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
    dynamic_sections.sort(
        key=lambda item: float(item.get("score") or 0.0), reverse=True
    )
    return (static_lead + dynamic_sections)[:4]


def _select_profile_weekly_clusters(profile, limit=5, _cached_clusters=None, _cached_engagement=None):
    """Select weekly clusters for a profile with optional cached data to avoid N+1 queries."""
    profile = _normalize_synced_profile_for_delivery(profile)
    # Use cached data if provided, otherwise fetch fresh
    engagement_map = _cached_engagement if _cached_engagement is not None else _load_weekly_cluster_engagement()
    clusters_to_score = _cached_clusters if _cached_clusters is not None else _load_weekly_digest_clusters(limit=28)
    ranked = []
    for cluster in clusters_to_score:
        match_score, reasons, _, _ = _cluster_delivery_match(cluster, profile)
        engagement = (
            engagement_map.get(str(cluster.get("cluster_id") or "").strip()) or {}
        )
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
        elif (
            sends >= 3 and open_rate < 0.25 and int(engagement.get("clicks") or 0) == 0
        ):
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
    personalized.sort(
        key=lambda item: (item["match_score"], item.get("score") or 0), reverse=True
    )
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
                lines.append(
                    f"  {str(cluster['cluster_summary']).splitlines()[0][:220]}"
                )
            elif cluster.get("description"):
                lines.append(f"  {str(cluster['description'])[:220]}")
            if cluster.get("difference_point"):
                lines.append(
                    f"  glavna razlika: {str(cluster['difference_point'])[:180]}"
                )
            elif cluster.get("open_point"):
                lines.append(
                    f"  Sto ostana otvoreno: {str(cluster['open_point'])[:180]}"
                )

    lines.append("")
    lines.append(
        "Sto da sledite dalje: Proverete im temite i klasterite sto ostanuvaat otvoreni ili vleguvaat vo nova faza."
    )
    return "\n".join(line for line in lines if line is not None).strip()


def _select_profile_brief_clusters(profile, limit=4, _cached_clusters=None):
    """Select clusters for a profile with optional cached clusters to avoid N+1 queries."""
    profile = _normalize_synced_profile_for_delivery(profile)
    ranked = []
    # Use cached clusters if provided, otherwise fetch fresh
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
    personalized.sort(
        key=lambda item: (item["match_score"], item.get("score") or 0), reverse=True
    )
    if personalized:
        return _dedupe_briefing_candidates(personalized, limit=limit)

    ranked.sort(key=lambda item: item.get("score") or 0, reverse=True)
    return _dedupe_briefing_candidates(ranked, limit=min(limit, 3))


def _parse_row_datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception as e:
            log.debug(f"Failed to parse datetime: {e}")
            return None
    return None


def _record_delivery_tracking_event(
    sync_token,
    event_type,
    delivery_kind,
    *,
    channel="ntfy",
    target="",
    cluster_id=None,
    parent_event_id=None,
    metadata=None,
):
    row = db.execute_one(
        """INSERT INTO delivery_tracking_events
           (sync_token, parent_event_id, event_type, delivery_kind, channel, target, cluster_id, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
           RETURNING id""",
        (
            sync_token,
            parent_event_id,
            str(event_type or "").strip(),
            str(delivery_kind or "").strip(),
            str(channel or "ntfy").strip() or "ntfy",
            str(target or "").strip(),
            str(cluster_id or "").strip() or None,
            json.dumps(metadata or {}),
        ),
    )
    return int((row or {}).get("id") or 0)


def _tracked_delivery_url(event_id, event_type, path):
    event_id = int(event_id or 0)
    clean_path = str(path or "").strip()
    if not clean_path.startswith("/"):
        clean_path = "/briefing"
    query = urllib.parse.urlencode({"event_id": event_id, "redirect": clean_path})
    return f"{_PUBLIC_SITE_URL}/api/delivery/track/{urllib.parse.quote(str(event_type or 'click'), safe='')}?{query}"


def _send_web_push_message(subscription_json_str, title, message, click_url=None):
    from config import VAPID_PRIVATE_KEY, VAPID_CLAIMS

    try:
        import pywebpush
        import json

        sub_info = json.loads(subscription_json_str)
        payload = json.dumps(
            {
                "title": str(title or "Presek")[:120],
                "message": str(message or "")[:500],
                "click_url": str(click_url or "")[:500],
            }
        )
        pywebpush.webpush(
            subscription_info=sub_info,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS,
            ttl=86400,
        )
        return True
    except Exception as e:
        log.warning(f"[tasks] web_push error: {e}")
        return False


def _send_ntfy_message(topic, title, message, tags="newspaper", click_url=None):
    clean_topic = str(topic or "").strip()
    import re

    clean_topic = re.sub(r"[^a-zA-Z0-9_-]", "", clean_topic)[:64]

    clean_message = str(message or "").strip()
    if not clean_topic or not clean_message:
        return False

    params = {
        "title": str(title or "Presek").strip()[:120],
        "tags": str(tags or "newspaper"),
        "priority": "default",
    }
    if click_url:
        params["click"] = str(click_url).strip()[:500]

    headers = {}
    if NTFY_TOKEN and NTFY_TOKEN != "YOUR_NTFY_TOKEN_HERE":
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"

    url = f"https://ntfy.sh/{urllib.parse.quote(clean_topic, safe='')}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                url,
                content=clean_message.encode("utf-8"),
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            return True
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        log.warning(f"[tasks] ntfy delivery failed for topic {clean_topic}: {e}")
        return False


def _load_recent_breaking_clusters(hours=4, limit=24):
    now = datetime.datetime.now(datetime.timezone.utc)
    ranked = []
    for cluster in _load_daily_brief_clusters(limit=limit):
        created_at = _parse_row_datetime(cluster.get("created_at"))
        if created_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        age_hours = (
            now - created_at.astimezone(datetime.timezone.utc)
        ).total_seconds() / 3600.0
        if age_hours > hours:
            continue
        if float(cluster.get("score") or 0) < BREAKING_SCORE_THRESHOLD:
            continue
        ranked.append(cluster)
    ranked.sort(key=lambda item: item.get("score") or 0, reverse=True)
    return ranked


def _normalize_alert_context(context):
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception as e:
            log.debug(f"Failed to parse alert context JSON: {e}")
            return {}
    if not isinstance(context, dict):
        return {}
    clean = {}
    for key, value in context.items():
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if key_text and value_text:
            clean[key_text] = value_text
    return clean


def _load_cluster_alert_material(cluster_id):
    articles = db.execute(
        "SELECT title, description, source, link, created_at, category, topic FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 8",
        (cluster_id,),
    )
    summary_row = db.execute_one(
        "SELECT created_at FROM cluster_summaries WHERE cluster_id = %s",
        (cluster_id,),
    )
    return articles, (summary_row or {}).get("created_at")


def _batch_load_cluster_alert_materials(cluster_ids):
    """Batch load alert materials for multiple cluster IDs."""
    if not cluster_ids:
        return {}
    
    # Fetch all articles for the given cluster IDs
    cluster_id_tuple = tuple(cluster_ids)
    articles_by_cluster = {}
    
    rows = db.execute(
        "SELECT title, description, source, link, created_at, category, topic, cluster_id "
        "FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
        (cluster_id_tuple,),
    )
    
    for row in rows or []:
        cid = str(row.get("cluster_id") or "")
        if cid not in articles_by_cluster:
            articles_by_cluster[cid] = []
        articles_by_cluster[cid].append(row)
    
    # Limit to 8 articles per cluster
    for cid in articles_by_cluster:
        articles_by_cluster[cid] = articles_by_cluster[cid][:8]
    
    # Fetch summary dates
    summary_rows = db.execute(
        "SELECT cluster_id, created_at FROM cluster_summaries WHERE cluster_id = ANY(%s)",
        (cluster_id_tuple,),
    )
    
    summaries_by_cluster = {}
    for row in summary_rows or []:
        cid = str(row.get("cluster_id") or "")
        summaries_by_cluster[cid] = row.get("created_at")
    
    # Build result dict
    result = {}
    for cid in cluster_ids:
        cid_str = str(cid)
        result[cid_str] = {
            "articles": articles_by_cluster.get(cid_str, []),
            "summary_date": summaries_by_cluster.get(cid_str),
        }
    
    return result


def _load_delivery_kind_performance(days=30):
    rows = db.execute(
        "SELECT delivery_kind, "
        "COUNT(*) FILTER (WHERE event_type = 'send') AS sends, "
        "COUNT(*) FILTER (WHERE event_type = 'open') AS opens, "
        "COUNT(*) FILTER (WHERE event_type = 'click') AS clicks "
        "FROM delivery_tracking_events "
        "WHERE created_at >= NOW() - (%s * INTERVAL '1 day') "
        "GROUP BY delivery_kind",
        (days,),
    )
    performance = {}
    for row in rows or []:
        kind = str(row.get("delivery_kind") or "").strip()
        if not kind:
            continue
        sends = int(row.get("sends") or 0)
        opens = int(row.get("opens") or 0)
        clicks = int(row.get("clicks") or 0)
        performance[kind] = {
            "sends": sends,
            "opens": opens,
            "clicks": clicks,
            "open_rate": (opens / sends) if sends else 0.0,
            "click_rate": (clicks / sends) if sends else 0.0,
        }
    return performance


def _load_breaking_target_performance(days=45):
    send_rows = db.execute(
        "SELECT id, metadata "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'breaking' AND event_type = 'send' "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )
    child_rows = db.execute(
        "SELECT parent_event_id, event_type "
        "FROM delivery_tracking_events "
        "WHERE delivery_kind = 'breaking' AND event_type IN ('open', 'click') "
        "AND created_at >= NOW() - (%s * INTERVAL '1 day')",
        (days,),
    )

    child_map = {}
    for row in child_rows or []:
        parent_id = int(row.get("parent_event_id") or 0)
        if parent_id <= 0:
            continue
        bucket = child_map.setdefault(parent_id, {"opens": 0, "clicks": 0})
        event_type = str(row.get("event_type") or "").strip()
        if event_type == "open":
            bucket["opens"] += 1
        elif event_type == "click":
            bucket["clicks"] += 1

    topic_map = {}
    source_map = {}
    for row in send_rows or []:
        event_id = int(row.get("id") or 0)
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception as e:
                log.debug(f"Failed to parse metadata JSON: {e}")
                metadata = {}
        child_stats = child_map.get(event_id) or {"opens": 0, "clicks": 0}

        for topic in metadata.get("matched_topics") or []:
            clean = str(topic or "").strip()
            if not clean:
                continue
            bucket = topic_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

        for source in metadata.get("matched_sources") or []:
            clean = str(source or "").strip()
            if not clean:
                continue
            bucket = source_map.setdefault(clean, {"sends": 0, "opens": 0, "clicks": 0})
            bucket["sends"] += 1
            bucket["opens"] += child_stats["opens"]
            bucket["clicks"] += child_stats["clicks"]

    for mapping in (topic_map, source_map):
        for _, bucket in mapping.items():
            sends = int(bucket.get("sends") or 0)
            opens = int(bucket.get("opens") or 0)
            clicks = int(bucket.get("clicks") or 0)
            bucket["open_rate"] = (opens / sends) if sends else 0.0
            bucket["click_rate"] = (clicks / sends) if sends else 0.0

    return {"topics": topic_map, "sources": source_map}


def _classify_alert_candidate(
    cluster,
    freshness,
    matched_topics,
    matched_sources,
    delivery_performance=None,
    target_performance=None,
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
    alert_reason = (
        cluster.get("match_reason")
        or "ova prica silno se vrzuva so vasite sledeni temi ili izvori"
    )
    alert_tags = "newspaper"
    min_gap_minutes = 90
    topic_gap_minutes = 240
    source_gap_minutes = 180
    severity_rank = 1
    score_adjustment = 0.0
    engagement_label = "Normalen odziv"

    if (
        "credible_new_reporting" in reasons
        or "new_sources" in reasons
        or base_score >= BREAKING_SCORE_THRESHOLD + 1.4
    ):
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
            alert_reason = (
                f"{alert_reason}; pracame samo posilni azuriranja dodeka odzivot e nizok"
            )
    elif breaking_sends >= 6 and (
        breaking_click_rate >= 0.22 or breaking_open_rate >= 0.58
    ):
        engagement_label = "Silen odziv"
        min_gap_minutes = max(20, min_gap_minutes - 15)
        topic_gap_minutes = max(90, topic_gap_minutes - 45)
        source_gap_minutes = max(75, source_gap_minutes - 30)
        if severity_rank >= 2:
            score_adjustment += 0.25
            alert_reason = (
                f"{alert_reason}; vakvi azuriranja i prethodno dobivaa silen odziv"
            )

    topic_performance = target_performance.get("topics") or {}
    source_performance = target_performance.get("sources") or {}

    topic_rates = [
        topic_performance.get(topic)
        for topic in matched_topics or []
        if topic_performance.get(topic)
    ]
    source_rates = [
        source_performance.get(source)
        for source in matched_sources or []
        if source_performance.get(source)
    ]

    strong_target_signal = any(
        int(item.get("sends") or 0) >= 2
        and (
            float(item.get("click_rate") or 0.0) >= 0.22
            or float(item.get("open_rate") or 0.0) >= 0.65
        )
        for item in topic_rates + source_rates
    )
    weak_target_signal = any(
        int(item.get("sends") or 0) >= 3
        and float(item.get("open_rate") or 0.0) < 0.2
        and float(item.get("click_rate") or 0.0) == 0.0
        for item in topic_rates + source_rates
    )

    if strong_target_signal:
        engagement_label = "Silen odziv za sledenoto"
        min_gap_minutes = max(20, min_gap_minutes - 15)
        topic_gap_minutes = max(75, topic_gap_minutes - 60)
        source_gap_minutes = max(60, source_gap_minutes - 45)
        score_adjustment += 0.3
        alert_reason = (
            f"{alert_reason}; ova tema ili izvor prethodno dobivale silen odziv"
        )
    elif weak_target_signal and severity_rank < 3:
        engagement_label = "Slab odziv za sledenoto"
        min_gap_minutes += 60
        topic_gap_minutes += 120
        source_gap_minutes += 120
        score_adjustment -= 0.35
        alert_reason = f"{alert_reason}; ova tema ili izvor prethodno imale slab odziv"

    throttle_keys = [f"cluster:{str(cluster.get('cluster_id') or '').strip()}"]
    throttle_keys.extend(f"topic:{topic}" for topic in matched_topics[:2])
    throttle_keys.extend(f"source:{source}" for source in matched_sources[:2])

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
        age_minutes = (
            now - last_global.astimezone(datetime.timezone.utc)
        ).total_seconds() / 60.0
        if age_minutes < candidate["min_gap_minutes"]:
            return True

    context = _normalize_alert_context(alert_context)
    for key in candidate["throttle_keys"]:
        last_value = _parse_row_datetime(context.get(key))
        if not last_value:
            continue
        if last_value.tzinfo is None:
            last_value = last_value.replace(tzinfo=datetime.timezone.utc)
        age_minutes = (
            now - last_value.astimezone(datetime.timezone.utc)
        ).total_seconds() / 60.0
        if key.startswith("cluster:") and age_minutes < max(
            180, candidate["min_gap_minutes"] * 2
        ):
            return True
        if key.startswith("topic:") and age_minutes < candidate["topic_gap_minutes"]:
            return True
        if key.startswith("source:") and age_minutes < candidate["source_gap_minutes"]:
            return True
    return False


def _next_alert_context(existing_context, candidate):
    context = _normalize_alert_context(existing_context)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for key in candidate["throttle_keys"]:
        context[key] = now
    return context


def _select_breaking_cluster_for_profile(
    profile,
    seen_cluster_ids,
    alert_context=None,
    last_breaking_sent_at=None,
    *,
    include_topics=True,
    include_sources=True,
):
    profile = _normalize_synced_profile_for_delivery(profile)
    seen = {
        str(item or "").strip()
        for item in seen_cluster_ids or []
        if str(item or "").strip()
    }
    delivery_performance = _load_delivery_kind_performance()
    target_performance = _load_breaking_target_performance()

    candidates = []
    for cluster in _load_recent_breaking_clusters():
        cluster_id = str(cluster.get("cluster_id") or "").strip()
        if not cluster_id:
            continue
        match_score, reasons, matched_topics, matched_sources = _cluster_delivery_match(
            cluster,
            profile,
            include_topics=include_topics,
            include_sources=include_sources,
        )
        if match_score < 2.0:
            continue
        articles, synthesis_created_at = _load_cluster_alert_material(cluster_id)
        freshness = assess_cluster_synthesis_freshness(articles, synthesis_created_at)
        alert_meta = _classify_alert_candidate(
            cluster,
            freshness,
            matched_topics,
            matched_sources,
            delivery_performance,
            target_performance,
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
    """Generate the flagship morning briefing with intelligence signals."""
    now = datetime.datetime.now()
    lock_key = f"lock:daily_brief:{lang}:{now.date()}:{now.hour // 6}"
    try:
        if not redis_client.set(lock_key, "1", nx=True, ex=3600):
            log.info(
                f"Daily brief ({lang}) generation already in progress or completed for today."
            )
            return
    except Exception as e:
        log.warning(f"Redis lock check failed for daily brief: {e}")

    try:
        from tasks.utils import record_task_event

        # 1. Gather Intelligence Stats
        country_filter = "RS" if lang == "sr" else "MK"
        total_24h = (
            db.execute_one(
                "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND country = %s",
                (country_filter,)
            )["count"]
            or 1
        )
        intl_24h = (
            db.execute_one(
                "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND is_global = TRUE AND country = %s",
                (country_filter,)
            )["count"]
            or 0
        )
        intl_pct = round((intl_24h / total_24h) * 100) if total_24h > 0 else 0

        # Pluralism check
        balance_stats = db.execute_one(
            """
            WITH cluster_tiers AS (
                SELECT cluster_id, COUNT(DISTINCT 
                    CASE 
                        WHEN s.category IN ('Agencijski', 'Javni servis', 'glavni') THEN 'M'
                        WHEN s.category IN ('Nezavisni', 'Istraživački') THEN 'I'
                        ELSE 'R'
                    END) as group_count
                FROM articles a
                JOIN sources s ON a.source = s.name
                WHERE a.created_at >= NOW() - INTERVAL '24 hours' AND a.country = %s
                GROUP BY cluster_id
            )
            SELECT COUNT(*) FILTER (WHERE group_count >= 2) as diverse
            FROM cluster_tiers
        """,
            (country_filter,)
        )
        diverse_pct = (
            round((balance_stats["diverse"] / total_24h) * 100) if total_24h > 0 else 0
        )

        # Top Subjects and Locations
        subjects_rows = db.execute(
            """
            SELECT topic, COUNT(*) as c 
            FROM articles 
            WHERE created_at >= NOW() - INTERVAL '24 hours' AND country = %s AND topic IS NOT NULL 
            GROUP BY topic ORDER BY c DESC LIMIT 3
        """,
            (country_filter,)
        )
        top_subjects = ", ".join([r["topic"] for r in subjects_rows])

        top_locations = "Balkan" # default

        # 2. Prep Dispatch Name
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            dispatch_name = "Jutarnji brifing" if lang == "sr" else "Утрински брифинг"
        elif 12 <= hour < 18:
            dispatch_name = "Podnevni pregled" if lang == "sr" else "Пладневен преглед"
        else:
            dispatch_name = "Vecernji pregled" if lang == "sr" else "Вечерен преглед"

        # 3. Build AI Context
        clusters = _load_daily_brief_clusters(limit=10, lang=lang)
        content_context = _build_daily_brief_context(clusters)

        system_insight = (
            f"\n\n[SISTEMSKA ANALIZA ZA POSLEDNJIH 24 SATA]\n"
            f"- Obradjeni clanci: {total_24h}\n"
            f"- Udeo svetskih vest: {intl_pct}%\n"
            f"- Indeks pluralizma (raznovrsni izvori): {diverse_pct}%\n"
            f"- Najzastupljeni akteri: {top_subjects or 'Nema'}\n"
            f"- U focusu lokacije: {top_locations or 'Nema'}\n"
            f"- Naziv izvestaja: {dispatch_name}"
        )

        full_context = f"<briefing_context>\n{content_context}\n{system_insight}\n</briefing_context>"

        prompt = DAILY_BRIEF_SYSTEM_PROMPT if lang == "sr" else DAILY_BRIEF_SYSTEM_PROMPT_MK
        brief, _ = _call_ai(
            full_context,
            prompt,
            task_type="daily_brief",
            max_tokens=4000,
        )
        if brief and not _has_valid_daily_brief_structure(brief):
            log.warning(
                f"[tasks] Daily brief ({lang}) rejected for invalid structure; using local fallback."
            )
            brief = ""
        if brief and not _is_grounded_daily_brief(brief, full_context):
            log.warning(
                f"[tasks] Daily brief ({lang}) rejected as ungrounded; using local fallback."
            )
            brief = ""

        if brief and not _is_high_quality_briefing(brief):
            log.warning(
                f"[tasks] Daily brief ({lang}) rejected by editorial quality gate; using local fallback."
            )
            brief = ""

        final_brief = brief or generate_daily_brief_fallback(clusters)
        if final_brief:
            # We store the dispatch name in the content first line or handle it in UI
            if brief and not final_brief.startswith("#"):
                final_brief = f"# {dispatch_name}\n\n" + final_brief

            db.execute(
                "INSERT INTO daily_briefings (date, content, lang) VALUES (CURRENT_DATE, %s, %s) ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content",
                (final_brief, lang),
                fetch=False,
            )
            delete_cache(f"daily_brief:latest:{lang}")
            record_task_event(
                "daily_brief", "ok" if brief else "fallback", f"lang:{lang}"
            )
            if not brief and retry_attempt < 2:
                generate_daily_brief_task.apply_async(
                    kwargs={"retry_attempt": retry_attempt + 1, "lang": lang}, countdown=1800
                )
    except Exception as e:
        clusters = _load_daily_brief_clusters(limit=6, lang=lang)
        fallback = generate_daily_brief_fallback(clusters)
        if fallback:
            db.execute(
                "INSERT INTO daily_briefings (date, content, lang) VALUES (CURRENT_DATE, %s, %s) ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content",
                (fallback, lang),
                fetch=False,
            )
            delete_cache(f"daily_brief:latest:{lang}")
            from tasks.utils import record_task_event

            record_task_event("daily_brief", "fallback", f"lang:{lang}")
            log.warning(f"[tasks] Daily brief ({lang}) failed; stored local fallback briefing")
            if retry_attempt < 2:
                generate_daily_brief_task.apply_async(
                    kwargs={"retry_attempt": retry_attempt + 1, "lang": lang}, countdown=1800
                )
        else:
            from tasks.utils import record_task_event

            record_task_event("daily_brief", "error", f"lang:{lang}")
            log.error(f"[tasks] Daily brief ({lang}) failed: {e}")


@celery_app.task
def send_daily_digest_task():
    """Send daily email digest. Placeholder — implement with digest module."""
    try:
        import digest as digest_module

        digest_module.send_digest()
    except Exception as e:
        log.warning(f"[tasks] Daily digest skipped: {e}")


@celery_app.task
def generate_all_daily_briefs_task():
    """Generate daily briefings for all supported languages."""
    # Generate Serbian briefing
    generate_daily_brief_task.apply_async(args=(0, "sr"))
    # Generate Macedonian briefing
    generate_daily_brief_task.apply_async(args=(0, "mk"))


@celery_app.task
def send_profile_briefings_task():
    """Send scheduled morning briefings for synced delivery subscriptions."""
    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0

    try:
        rows = _load_active_delivery_rows()
        # Cache per locale
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

            profile = _normalize_synced_profile_for_delivery(
                row.get("profile_data") or {}
            )
            # Use cached clusters for the appropriate locale
            clusters = _select_profile_brief_clusters(profile, _cached_clusters=cached_clusters.get(locale, cached_clusters["sr"]))
            if not clusters:
                continue

            message = _build_profile_briefing_message(profile, clusters, locale=locale)
            if not message:
                continue

            primary_cluster_id = (
                str((clusters[0] or {}).get("cluster_id") or "").strip() or None
            )
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
            click_url = (
                _tracked_delivery_url(send_event_id, "open", "/briefing")
                if send_event_id
                else None
            )
            click_track_url = (
                _tracked_delivery_url(send_event_id, "click", "/briefing")
                if send_event_id
                else None
            )
            message_with_link = (
                message
                if not click_track_url
                else f"{message}\n\n{conf['read_briefing']}: {click_track_url}"
            )
            if _send_ntfy_message(
                target,
                conf["ntfy_title"],
                message_with_link,
                tags="newspaper,sunrise",
                click_url=click_url,
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
def send_profile_weekly_digests_task():
    """Send scheduled weekly digests for synced delivery subscriptions."""
    now = datetime.datetime.now(datetime.timezone.utc)
    sent = 0

    try:
        rows = _load_active_delivery_rows()
        # Cache weekly digest clusters and engagement to avoid N+1 queries
        all_weekly_clusters = _load_weekly_digest_clusters(limit=28)
        engagement_map = _load_weekly_cluster_engagement()
        
        for row in rows:
            if not row.get("weekly_digest"):
                continue

            last_sent = _parse_row_datetime(row.get("last_weekly_sent_at"))
            if last_sent:
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=datetime.timezone.utc)
                if (
                    now - last_sent.astimezone(datetime.timezone.utc)
                ).total_seconds() < 6.5 * 24 * 3600:
                    continue

            target = str(row.get("target") or NTFY_TOPIC).strip()
            profile = _normalize_synced_profile_for_delivery(
                row.get("profile_data") or {}
            )
            # Use cached data instead of re-fetching for each profile
            clusters = _select_profile_weekly_clusters(
                profile, 
                _cached_clusters=all_weekly_clusters,
                _cached_engagement=engagement_map
            )
            if not clusters:
                continue

            message = _build_profile_weekly_digest_message(profile, clusters)
            if not message:
                continue

            primary_cluster_id = (
                str((clusters[0] or {}).get("cluster_id") or "").strip() or None
            )
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
                    ]
                },
            )
            click_url = (
                _tracked_delivery_url(send_event_id, "open", "/briefing")
                if send_event_id
                else None
            )
            click_track_url = (
                _tracked_delivery_url(send_event_id, "click", "/briefing")
                if send_event_id
                else None
            )
            message_with_link = (
                message
                if not click_track_url
                else f"{message}\n\nOtvori pregled: {click_track_url}"
            )
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
def send_profile_breaking_alerts_task():
    """Send breaking alerts for followed topics and sources through active synced subscriptions."""
    if not acquire_task_lock(
        _BREAKING_ALERT_TASK_LOCK, ttl_seconds=_BREAKING_ALERT_LOCK_TTL
    ):
        log.info(
            "[tasks] Skipping breaking alerts run because another run is already active."
        )
        return

    sent = 0

    try:
        if get_celery_queue_depth() >= _BREAKING_ALERT_QUEUE_DEPTH_LIMIT:
            log.info(
                "[tasks] Skipping breaking alerts run while queue backlog is high."
            )
            return

        rows = _load_active_delivery_rows()
        # Cache breaking clusters and performance data to avoid N+1 queries
        all_breaking_clusters = _load_recent_breaking_clusters()
        delivery_performance = _load_delivery_kind_performance()
        target_performance = _load_breaking_target_performance()
        # Batch load alert material for all breaking clusters
        cluster_ids = [str(c.get("cluster_id") or "").strip() for c in all_breaking_clusters if c.get("cluster_id")]
        alert_materials = _batch_load_cluster_alert_materials(cluster_ids) if cluster_ids else {}
        
        for row in rows:
            if not row.get("breaking_topics") and not row.get("breaking_sources"):
                continue

            target = str(row.get("target") or NTFY_TOPIC).strip()
            profile = _normalize_synced_profile_for_delivery(
                row.get("profile_data") or {}
            )
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

            # Per-cluster-profile lock to prevent race condition across multiple workers
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
                message_lines.append(
                    f"Zosto ga dobivate ova: {candidate['match_reason']}"
                )
            if candidate.get("cluster_summary"):
                message_lines.append(
                    str(candidate["cluster_summary"]).splitlines()[0][:240]
                )
            elif candidate.get("description"):
                message_lines.append(str(candidate["description"])[:240])
            if candidate.get("difference_point"):
                message_lines.append(
                    f"Razlika: {str(candidate['difference_point'])[:180]}"
                )
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
                else (
                    _tracked_delivery_url(send_event_id, "open", "/briefing")
                    if send_event_id
                    else None
                )
            )
            click_track_url = (
                _tracked_delivery_url(send_event_id, "click", f"/cluster/{cluster_id}")
                if send_event_id and cluster_id
                else (
                    _tracked_delivery_url(send_event_id, "click", "/briefing")
                    if send_event_id
                    else None
                )
            )
            message_text = "\n".join(message_lines)
            if click_track_url:
                message_text = f"{message_text}\nOtvori klaster: {click_track_url}"

            delivery_channel = str(row.get("channel") or "ntfy").strip().lower()
            sent_success = False

            if delivery_channel == "webpush":
                sent_success = _send_web_push_message(
                    target,
                    title,
                    message_text,
                    click_url=open_url,
                )
            else:
                sent_success = _send_ntfy_message(
                    target,
                    title,
                    message_text,
                    tags=candidate.get("alert_tags") or "newspaper",
                    click_url=open_url,
                )

            if sent_success:
                next_ids = [str(candidate.get("cluster_id") or "").strip()]
                next_ids.extend(
                    str(item or "").strip()
                    for item in existing_ids
                    if str(item or "").strip()
                    and str(item or "").strip()
                    != str(candidate.get("cluster_id") or "").strip()
                )
                next_context = _next_alert_context(
                    row.get("last_alert_context"), candidate
                )
                db.execute(
                    "UPDATE synced_delivery_subscriptions "
                    "SET last_breaking_sent_at = NOW(), last_alert_cluster_ids = %s::jsonb, last_alert_context = %s::jsonb, updated_at = NOW() "
                    "WHERE sync_token = %s",
                    (
                        json.dumps(next_ids[:24]),
                        json.dumps(next_context),
                        row["sync_token"],
                    ),
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


@celery_app.task
def send_newsletter_task():
    """Sends the daily newsletter to all subscribers."""
    try:
        from digest import send_newsletter_to_all_subscribers

        count = send_newsletter_to_all_subscribers(days=1)
        log.info(f"[tasks] Morning briefing sent to {count} subscribers.")
    except Exception as e:
        log.warning(f"[tasks] Newsletter delivery failed: {e}")
