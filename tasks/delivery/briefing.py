import datetime
import json
import math

from core.ai_engine import sync_call_ai as _call_ai
from core.api_helpers import normalize_perspectives
from core.celery_app import celery_app
from core.config import NTFY_TOPIC
from core.database import db_manager as db
from core.editorial_quality import normalize_serbian_editorial_text
from core.prompts import DAILY_BRIEF_SYSTEM_PROMPT, DAILY_BRIEF_SYSTEM_PROMPT_MK
from nlp import generate_daily_brief_fallback
from nlp.keywords import _extract_capitalized_phrases
from tasks.utils import acquire_task_lock, delete_cache, get_celery_queue_depth, log, redis_client, release_task_lock
from utils import rank_articles_in_cluster, score_cluster_for_homepage

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
    _site_url_for_locale,
    _tracked_delivery_url,
)
from .subscribers import _cluster_delivery_match, _load_active_delivery_rows, _normalize_synced_profile_for_delivery

from .briefing_alerts import (
    _alert_throttled,
    _batch_load_cluster_alert_materials,
    _classify_alert_candidate,
    _load_cluster_alert_material,
    _load_recent_breaking_clusters,
    _select_breaking_cluster_for_profile,
)
from .briefing_quality import (
    _allow_partisan_briefing_cluster,
    _briefing_title_penalty,
    _has_public_interest_signal,
    _has_valid_daily_brief_structure,
    _is_grounded_daily_brief,
    _is_high_quality_briefing,
    _is_low_signal_briefing_cluster,
    _is_party_press_release_title,
    _is_routine_sports_cluster,
    _is_routine_weather_cluster,
)

_BRIEFING_SCHEDULE_HOUR_UTC = 6


def _resolve_briefing_date(briefing_date=None):
    if briefing_date:
        if isinstance(briefing_date, datetime.date):
            return briefing_date
        return datetime.date.fromisoformat(str(briefing_date))
    return datetime.date.today()


def _briefing_window_for_date(target_date):
    """Match the 06:00 UTC daily run: articles from the prior 24 hours."""
    window_end = datetime.datetime.combine(
        target_date,
        datetime.time(_BRIEFING_SCHEDULE_HOUR_UTC, 0),
        tzinfo=datetime.timezone.utc,
    )
    window_start = window_end - datetime.timedelta(hours=24)
    return window_start, window_end


def _load_daily_brief_clusters(limit=5, lang="sr", briefing_date=None):
    target_date = _resolve_briefing_date(briefing_date)
    window_start, window_end = _briefing_window_for_date(target_date)
    # Fetch articles in one query
    country_filter = "RS" if lang == "sr" else "MK"
    rows = db.execute(
        """SELECT cluster_id, title, description, summary, source, category, topic, created_at FROM articles
        WHERE created_at >= %s AND created_at < %s AND country = %s ORDER BY created_at DESC LIMIT 180""",
        (window_start, window_end, country_filter),
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
        sports_context = " ".join(
            f"{article.get('title') or ''} {article.get('source') or ''}" for article in ranked[:6]
        )
        is_routine_sports = _is_routine_sports_cluster(
            lead.get("title"),
            description,
            cluster_summary,
            lead.get("category"),
            lead.get("topic"),
            extra_context=sports_context,
        )
        has_public_interest = _has_public_interest_signal(lead.get("title"), description, cluster_summary)
        has_editorial_depth = bool(difference_point or open_point or cluster_summary)

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
        briefing_score -= _briefing_title_penalty(
            lead.get("title"),
            source_count=source_count,
            has_editorial_depth=has_editorial_depth,
        )
        if is_low_signal:
            briefing_score -= 2.5
        if is_routine_weather:
            briefing_score -= 3.0
        if is_routine_sports:
            briefing_score -= 4.5

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
                "is_routine_sports": is_routine_sports,
                "is_low_signal": is_low_signal,
                "has_public_interest": has_public_interest,
            }
        )

    ranked_clusters.sort(key=lambda item: item["score"], reverse=True)

    # Selection with Entity-Based Diversity Enforcement
    selected = []
    seen_entities = set()
    sports_selected = 0
    substantive_candidates = [
        cluster
        for cluster in ranked_clusters
        if not cluster["is_routine_weather"] and not cluster["is_routine_sports"] and not cluster["is_low_signal"]
    ]
    max_routine_sports = 1 if limit >= 4 else 0

    for cluster in ranked_clusters:
        if len(selected) >= limit:
            break
        if cluster["is_routine_weather"] and substantive_candidates:
            continue
        if cluster["is_routine_sports"] and substantive_candidates:
            if len(selected) == 0:
                continue
            if sports_selected >= max_routine_sports:
                continue
        if cluster["is_low_signal"] and substantive_candidates and len(selected) == 0:
            continue

        # Stronger Diversity Gate: If cluster shares too many entities with already selected top stories, skip it
        if len(selected) < 3:
            overlap = cluster["entities"] & seen_entities
            if len(overlap) >= 2:  # High actor overlap
                continue

        selected.append(cluster)
        if cluster["is_routine_sports"]:
            sports_selected += 1
        seen_entities.update(cluster["entities"])

    return selected


def _build_daily_brief_context(clusters, lang="sr"):
    blocks = []
    labels = (
        {
            "cluster": "klaster",
            "id": "ID",
            "title": "Naslov",
            "category": "Kategorija",
            "lead_source": "Vodeći izvor",
            "source_count": "Broj izvora",
            "editorial_weight": "Urednička težina",
            "context": "Kratak kontekst",
            "synthesis": "Sinteza",
            "other_titles": "Kako drugi izvori naslovljavaju",
            "difference": "Razlike u akcentu",
            "open": "Šta ostaje otvoreno",
        }
        if lang == "sr"
        else {
            "cluster": "кластер",
            "id": "ID",
            "title": "Наслов",
            "category": "Категорија",
            "lead_source": "Водечки извор",
            "source_count": "Број извори",
            "editorial_weight": "Уредничка тежина",
            "context": "Краток контекст",
            "synthesis": "Синтеза",
            "other_titles": "Како насловуваат други извори",
            "difference": "Разлики во акцент",
            "open": "Што останува отворено",
        }
    )
    for index, cluster in enumerate(clusters[:6], start=1):
        source_count = cluster.get("source_count") or 1
        editorial_weight = "high" if source_count >= 5 else "medium" if source_count >= 2 else "single-source"
        blocks.append(
            "\n".join(
                [
                    f"### {labels['cluster']} {index}",
                    f"{labels['id']}: {cluster.get('cluster_id') or ''}",
                    f"{labels['title']}: {cluster.get('title') or ''}",
                    f"{labels['category']}: {cluster.get('category') or cluster.get('topic') or 'vesti'}",
                    f"{labels['lead_source']}: {cluster.get('source') or 'izvor'}",
                    f"{labels['source_count']}: {source_count}",
                    f"{labels['editorial_weight']}: {editorial_weight}",
                    f"{labels['context']}: {cluster.get('description') or ''}",
                    f"{labels['synthesis']}: {cluster.get('cluster_summary') or ''}",
                    f"{labels['other_titles']}: {' | '.join(cluster.get('other_titles') or [])}",
                    f"{labels['difference']}: {cluster.get('difference_point') or ''}",
                    f"{labels['open']}: {cluster.get('open_point') or ''}",
                ]
            )
        )
    return "\n\n".join(blocks)


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




@celery_app.task
def generate_daily_brief_task(
    retry_attempt=0,
    lang="sr",
    briefing_date=None,
    provider_override=None,
):
    target_date = _resolve_briefing_date(briefing_date)
    now = datetime.datetime.now()
    lock_key = f"lock:daily_brief:{lang}:{target_date.isoformat()}"
    try:
        if not redis_client.set(lock_key, "1", nx=True, ex=7200):
            log.info(f"Daily brief ({lang}) generation already in progress or completed for {target_date}.")
            return
    except Exception as e:
        log.warning(f"Redis lock check failed for daily brief: {e}")
    try:
        from tasks.utils import record_task_event

        country_filter = "RS" if lang == "sr" else "MK"
        window_start, window_end = _briefing_window_for_date(target_date)
        total_24h = (
            db.execute_one(
                "SELECT COUNT(*) FROM articles WHERE created_at >= %s AND created_at < %s AND country = %s",
                (window_start, window_end, country_filter),
            )["count"]
            or 1
        )
        intl_24h = (
            db.execute_one(
                "SELECT COUNT(*) FROM articles WHERE created_at >= %s AND created_at < %s AND is_global = TRUE AND country = %s",
                (window_start, window_end, country_filter),
            )["count"]
            or 0
        )
        intl_pct = round((intl_24h / total_24h) * 100) if total_24h > 0 else 0
        balance_stats = db.execute_one(
            """WITH cluster_tiers AS (SELECT cluster_id, COUNT(DISTINCT CASE WHEN s.category IN ('Agencijski', 'Javni servis', 'glavni') THEN 'M' WHEN s.category IN ('Nezavisni', 'Istraživački') THEN 'I' ELSE 'R' END) as group_count FROM articles a JOIN sources s ON a.source = s.name WHERE a.created_at >= %s AND a.created_at < %s AND a.country = %s GROUP BY cluster_id) SELECT COUNT(*) FILTER (WHERE group_count >= 2) as diverse FROM cluster_tiers""",
            (window_start, window_end, country_filter),
        )
        diverse_pct = round((balance_stats["diverse"] / total_24h) * 100) if total_24h > 0 else 0
        subjects_rows = db.execute(
            "SELECT topic, COUNT(*) as c FROM articles WHERE created_at >= %s AND created_at < %s AND country = %s AND topic IS NOT NULL GROUP BY topic ORDER BY c DESC LIMIT 3",
            (window_start, window_end, country_filter),
        )
        top_subjects = ", ".join([r["topic"] for r in subjects_rows])
        top_locations = "Balkan"

        # Consistent daily naming
        dispatch_name = "Dnevni brifing" if lang == "sr" else "Дневен брифинг"

        clusters = _load_daily_brief_clusters(limit=10, lang=lang, briefing_date=target_date)
        content_context = _build_daily_brief_context(clusters, lang=lang)
        system_insight = f"\n\n[SISTEMSKA ANALIZA ZA POSLEDNJIH 24 SATA]\n- Obradjeni clanci: {total_24h}\n- Udeo svetskih vest: {intl_pct}%\n- Indeks pluralizma (raznovrsni izvori): {diverse_pct}%\n- Najzastupljeni akteri: {top_subjects or 'Nema'}\n- U focusu lokacije: {top_locations or 'Nema'}\n- Naziv izvestaja: {dispatch_name}"
        
        # Chronological RAG context loop
        history_context = ""
        try:
            prev_brief = db.execute_one(
                "SELECT content FROM daily_briefings WHERE lang = %s AND date >= %s::date - INTERVAL '2 days' AND date < %s::date ORDER BY date DESC LIMIT 1",
                (lang, target_date.isoformat(), target_date.isoformat()),
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
        provider_exclusions = None
        if provider_override:
            provider_exclusions = [
                candidate
                for candidate in ("mistral_small", "mistral_large", "nvidia", "local")
                if candidate != provider_override
            ]
        brief, brief_provider = _call_ai(
            full_context,
            prompt,
            task_type="daily_brief",
            max_tokens=4000,
            lang=lang,
            provider_override=provider_override,
            exclude_providers=provider_exclusions,
        )
        if brief and (
            not _has_valid_daily_brief_structure(brief, lang=lang)
            or not _is_grounded_daily_brief(brief, full_context)
            or not _is_high_quality_briefing(brief)
        ):
            rejection_reasons = []
            if not _has_valid_daily_brief_structure(brief, lang=lang):
                rejection_reasons.append("structure")
            if not _is_grounded_daily_brief(brief, full_context):
                rejection_reasons.append("grounding")
            if not _is_high_quality_briefing(brief):
                rejection_reasons.append("quality")
            log.warning(
                f"[tasks] Daily brief ({lang}) rejected ({', '.join(rejection_reasons)}); using local fallback."
            )
            brief = ""
            brief_provider = None
        final_brief = brief or generate_daily_brief_fallback(clusters, lang=lang)
        if lang == "sr":
            final_brief = normalize_serbian_editorial_text(final_brief)
        if final_brief:
            if brief and not final_brief.startswith("#"):
                final_brief = f"# {dispatch_name}\n\n" + final_brief

            # Phase 1: Extract structured metadata for Intelligence Report 2.0
            metadata = {
                "model": brief_provider or "local_fallback",
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
                    f"<briefing>\n{final_brief}\n</briefing>",
                    narrative_prompt,
                    task_type="extraction",
                    max_tokens=1000,
                    lang=lang,
                    provider_override=provider_override,
                    exclude_providers=provider_exclusions,
                )

                if nar_raw:
                    # Clean potential markdown
                    nar_clean = nar_raw.strip().replace("```json", "").replace("```", "")
                    metadata["key_narratives"] = json.loads(nar_clean)
            except Exception as e:
                log.warning(f"[tasks] Narrative extraction failed: {e}")

            db.execute(
                "INSERT INTO daily_briefings (date, content, lang, metadata) VALUES (%s::date, %s, %s, %s) "
                "ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content, metadata = EXCLUDED.metadata",
                (target_date.isoformat(), final_brief, lang, json.dumps(metadata)),
                fetch=False,
            )
            delete_cache(f"daily_brief:latest:{lang}")
            record_task_event("daily_brief", "ok" if brief else "fallback", f"lang:{lang},date:{target_date.isoformat()}")
            if target_date == datetime.date.today():
                notify_daily_briefing_ready_task.apply_async(kwargs={"lang": lang}, countdown=20)

            # Automatically pre-generate the briefing audio in the background
            try:
                from core.audio_service import AudioService
                target_date_str = target_date.isoformat()
                log.info(f"[tasks] Auto-generating OmniVoice briefing audio in background for {target_date_str} ({lang})...")
                AudioService.generate_briefing_audio(target_date_str, final_brief, lang)
            except Exception as audio_err:
                log.error(f"[tasks] Failed to auto-generate briefing audio for {target_date.isoformat()} ({lang}): {audio_err}")
            if not brief and retry_attempt < 2 and target_date == datetime.date.today():
                generate_daily_brief_task.apply_async(
                    kwargs={"retry_attempt": retry_attempt + 1, "lang": lang, "briefing_date": target_date.isoformat()},
                    countdown=1800,
                )
    except Exception as e:
        clusters = _load_daily_brief_clusters(limit=6, lang=lang, briefing_date=target_date)
        fallback = generate_daily_brief_fallback(clusters, lang=lang)
        if fallback:
            db.execute(
                "INSERT INTO daily_briefings (date, content, lang, metadata) VALUES (%s::date, %s, %s, %s) "
                "ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content, metadata = EXCLUDED.metadata",
                (target_date.isoformat(), fallback, lang, json.dumps({"is_fallback": True})),
                fetch=False,
            )
            if target_date == datetime.date.today():
                notify_daily_briefing_ready_task.apply_async(kwargs={"lang": lang}, countdown=20)

            # Automatically pre-generate the briefing audio (fallback) in the background
            try:
                from core.audio_service import AudioService
                target_date_str = target_date.isoformat()
                log.info(f"[tasks] Auto-generating OmniVoice briefing audio in background (fallback) for {target_date_str} ({lang})...")
                AudioService.generate_briefing_audio(target_date_str, fallback, lang)
            except Exception as audio_err:
                log.error(f"[tasks] Failed to auto-generate briefing audio for {target_date.isoformat()} ({lang}): {audio_err}")
            if retry_attempt < 2 and target_date == datetime.date.today():
                generate_daily_brief_task.apply_async(
                    kwargs={"retry_attempt": retry_attempt + 1, "lang": lang, "briefing_date": target_date.isoformat()},
                    countdown=1800,
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
def notify_daily_briefing_ready_task(lang="sr"):
    """Broadcast that today's editorial briefing is ready."""
    conf = _LOCALIZED_DELIVERY.get(lang, _LOCALIZED_DELIVERY["sr"])
    notify_key = f"presek:briefing_ready_notify:{lang}:{datetime.date.today().isoformat()}"
    try:
        if not redis_client.set(notify_key, "1", nx=True, ex=86400):
            return
    except Exception as exc:
        log.warning(f"[tasks] briefing ready notify dedupe failed: {exc}")

    click_url = f"{_site_url_for_locale(lang)}/briefing?mode=quick"
    title = conf["briefing_ready_title"]
    message = conf["briefing_ready_message"]
    sent = 0

    try:
        for row in _load_active_delivery_rows():
            if not row.get("morning_briefing"):
                continue
            row_locale = str(row.get("locale") or "sr").strip().lower()
            if row_locale != lang:
                continue
            target = str(row.get("target") or "").strip()
            if not target:
                continue
            channel = str(row.get("channel") or "ntfy").strip().lower()
            if channel == "webpush":
                ok = _send_web_push_message(target, title, message, click_url=click_url)
            else:
                ok = _send_ntfy_message(target, title, message, tags="newspaper,sunrise", click_url=click_url)
            if ok:
                sent += 1
    except Exception as exc:
        log.warning(f"[tasks] Daily briefing ready notify failed ({lang}): {exc}")
    else:
        if sent:
            log.info(f"[tasks] Sent {sent} daily briefing ready notifications ({lang}).")


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
