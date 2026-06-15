import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from utils import cached_response, set_cache

from core.audio_service import AudioService
from core.queue_status import reader_pipeline_status
from nlp import normalize_focus_entity_surface
from .common import cleanAndDecode
from .intelligence import get_top_entities
from .news import fetch_news_data
from .stats import get_stats_summary
from .system import get_trending_route

log = logging.getLogger("presek")
router = APIRouter()
_background_tasks: set[asyncio.Task] = set()
_LEAD_TIEBREAK_WINDOW = 0.10
_HOMEPAGE_FEED_START = 4
_HOMEPAGE_DEVELOPING_LIMIT = 10
_HOMEPAGE_WIRE_LIMIT = 8


def _homepage_developing_sort_key(cluster: Dict[str, Any]) -> tuple:
    source_count = int(cluster.get("source_count") or len(cluster.get("articles") or []))
    return (
        1 if cluster.get("has_synthesis") else 0,
        source_count,
        float(cluster.get("homepage_score") or 0.0),
    )


def _homepage_cluster_score(cluster: Dict[str, Any]) -> float:
    return float(cluster.get("homepage_score") or 0.0)


def _apply_synthesis_lead_tiebreak(
    clusters: List[Dict[str, Any]],
    window: float = _LEAD_TIEBREAK_WINDOW,
) -> List[Dict[str, Any]]:
    """Prefer a synthesis-backed lead when top homepage candidates score within `window`."""
    if len(clusters) < 2:
        return clusters

    lead_score = _homepage_cluster_score(clusters[0])
    threshold = lead_score * (1.0 - window) if lead_score > 0 else 0.0

    candidates = [clusters[0]]
    for cluster in clusters[1:4]:
        score = _homepage_cluster_score(cluster)
        if lead_score > 0 and score >= threshold:
            candidates.append(cluster)

    synth_pick = next((cluster for cluster in candidates if cluster.get("has_synthesis")), None)
    if not synth_pick or synth_pick.get("cluster_id") == clusters[0].get("cluster_id"):
        return clusters

    return [synth_pick] + [
        cluster for cluster in clusters if cluster.get("cluster_id") != synth_pick.get("cluster_id")
    ]


def _schedule_background_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


class HomeResponse(BaseModel):
    status: str
    lead: Optional[Any] = None
    lead_display: Optional[Dict[str, Any]] = None
    supporting: List[Any] = Field(default_factory=list)
    synthesis_picks: List[Any] = Field(default_factory=list)
    live_now: List[Any] = Field(default_factory=list)
    for_you_pool: List[Any] = Field(default_factory=list)
    developing: List[Any] = Field(default_factory=list)
    wire: List[Any] = Field(default_factory=list)
    latest_wire: List[Any] = Field(default_factory=list)
    global_: List[Any] = Field(default_factory=list, alias="global")
    trending: List[Any] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)
    focus_entities: List[Any] = Field(default_factory=list)
    excluded_cluster_ids: List[str] = Field(default_factory=list)
    message: Optional[str] = None


class StatusOnlyResponse(BaseModel):
    status: str
    message: Optional[str] = None


_SOFT_EXCLUDE_TOPICS = {"Zivot", "Zabava", "Zdravje"}
_HARD_NEWS_TOPICS = {"Politika", "Ekonomija", "Kriminal", "Sport", "Tehnologija"}
_HARD_NEWS_CATEGORIES = {
    "Srbija",
    "Makedonija",
    "Balkan",
}
_AUDIO_PRIORITY_GENERATION_LIMIT = max(0, int(os.environ.get("AUDIO_PRIORITY_GENERATION_LIMIT", "2")))


async def _ensure_cluster_audio(cluster: Dict[str, Any], generate: bool = False) -> Dict[str, Any]:
    """
    Check if cluster has synthesis and ensure audio is generated.
    Adds audio_url to cluster if available.
    """
    if not cluster or not cluster.get('cluster_id'):
        return cluster
        
    cluster_id = cluster['cluster_id']
    lang = cluster.get('lang', 'sr')
    
    # Check if cluster already has audio info
    if cluster.get('audio_url'):
        return cluster
    
    try:
        filepath, urlpath = AudioService.get_cluster_audio_path_and_url(cluster_id, lang)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            cluster['audio_url'] = urlpath
            cluster['has_audio'] = True
            log.info(f"[home] Audio already exists for cluster {cluster_id}: {urlpath}")
            return cluster

        if not generate:
            return cluster

        # Check if cluster has generated synthesis content
        if cluster.get('generated_article') or cluster.get('synthesis'):
            content = cluster.get('generated_article') or cluster.get('synthesis') or ""
            if content and len(content.strip()) > 50:  # Only generate for substantial content
                log.info(f"[home] Cluster {cluster_id} has synthesis, ensuring audio generation")
                
                # Generate audio in background (non-blocking)
                _schedule_background_task(_generate_cluster_audio_background(cluster_id, content, lang))
                log.info(f"[home] Audio will be generated for cluster {cluster_id} in background")
    except Exception as e:
        log.error(f"[home] Error checking cluster audio for {cluster_id}: {e}")
    
    return cluster


async def _generate_cluster_audio_background(cluster_id: str, content: str, lang: str):
    """Background task to generate cluster audio without blocking the main request."""
    try:
        log.info(f"[home] Background audio generation started for cluster {cluster_id} ({lang})")
        audio_url = AudioService.generate_cluster_audio(cluster_id, content, lang)
        if audio_url:
            log.info(f"[home] Successfully generated audio for cluster {cluster_id}: {audio_url}")
        else:
            log.warning(f"[home] Audio generation failed for cluster {cluster_id}")
    except Exception as e:
        log.error(f"[home] Background audio generation failed for cluster {cluster_id}: {e}")


_HARD_NEWS_CATEGORIES = {
    "Evropa",
    "Germanija",
    "Amerika",
    "Svet",
}
_FEATURE_PATTERNS = [
    re.compile(r"izdanie na", re.IGNORECASE),
    re.compile(r"intervju so", re.IGNORECASE),
    re.compile(r"intervju\b", re.IGNORECASE),
    re.compile(r"proverete dali", re.IGNORECASE),
    re.compile(r"pred da ", re.IGNORECASE),
    re.compile(r"postojano ste umorni", re.IGNORECASE),
    re.compile(r"ovoj mineral", re.IGNORECASE),
    re.compile(r"horoskop", re.IGNORECASE),
    re.compile(r"recept", re.IGNORECASE),
    re.compile(r"foto\b", re.IGNORECASE),
    re.compile(r"video\b", re.IGNORECASE),
    re.compile(r"galerija", re.IGNORECASE),
]

_FOCUS_ENTITY_STOPWORDS = {
    "predsednik",
    "predsednica",
    "ministar",
    "ministarka",
    "policija",
    "sporazum",
    "saradnja",
    "saradnj",
    "evra",
    "zbog",
    "onda",
    "претседател",
    "претседателка",
    "министер",
    "министерка",
    "полиција",
    "договор",
    "соработка",
    "oglasio",
    "oglasila",
    "oglasili",
    "oglasio se",
    "oglasila se",
    "kompanija",
    "kompanije",
    "kompanij",
    "kompaniju",
    "kompanijama",
    "компанија",
    "компаније",
    "компанију",
    "automobil",
    "automobili",
    "automobila",
    "automobilu",
    "аутомобил",
    "аутомобили",
}


def _primary_article(cluster):
    articles = (cluster or {}).get("articles", [{}])
    return articles[0] if articles else {}


def _title_looks_like_feature(title):
    clean = cleanAndDecode(title)
    if not clean:
        return True
    if len(clean) > 180:
        return True
    if "?" in clean:
        return True
    return any(pattern.search(clean) for pattern in _FEATURE_PATTERNS)


def _extract_preview_summary(article):
    from nlp.utils import extract_clean_summary_text

    text = str((article or {}).get("summary") or (article or {}).get("description") or "")
    return extract_clean_summary_text(text)


def _parse_time(value):
    try:
        from utils import _coerce_datetime

        dt = _coerce_datetime(value)
        return dt.timestamp() if dt else 0
    except Exception:
        return 0


def _article_freshness_time(article):
    article = article or {}
    return article.get("ingested_at") or article.get("created_at")


def _is_live_now_candidate(cluster):
    if "live_now_fit" in (cluster or {}):
        return bool(cluster.get("live_now_fit"))
    article = _primary_article(cluster)
    title = cleanAndDecode(article.get("title") or "")
    topic = cleanAndDecode(article.get("topic") or "")
    category = cleanAndDecode(article.get("category") or "")

    if not title:
        return False
    if cluster.get("is_breaking"):
        return True
    if _title_looks_like_feature(title):
        return False
    if topic in _SOFT_EXCLUDE_TOPICS:
        return False
    if topic in _HARD_NEWS_TOPICS:
        return True
    if category and category not in _HARD_NEWS_CATEGORIES:
        return False
    return len(cluster.get("articles") or []) >= 2


def _clusters_sorted_by_recency(clusters):
    return sorted(
        clusters or [],
        key=lambda cluster: _parse_time(_article_freshness_time(_primary_article(cluster))),
        reverse=True,
    )


def _rank_live_now_clusters(items, exclude_cluster_ids=None, limit=4):
    exclude = set(exclude_cluster_ids or [])
    source_count = {}

    def sort_key(cluster):
        article = _primary_article(cluster)
        if cluster.get("live_now_score") is not None:
            return (
                float(cluster.get("live_now_score") or 0.0),
                float(cluster.get("importance_score") or 0.0),
                _parse_time(_article_freshness_time(article)),
            )
        return (
            1 if cluster.get("is_breaking") else 0,
            1 if cleanAndDecode(article.get("topic") or "") in _HARD_NEWS_TOPICS else 0,
            _parse_time(_article_freshness_time(article)),
        )

    ranked = sorted(
        [
            cluster
            for cluster in (items or [])
            if cluster and cluster.get("cluster_id") not in exclude and _is_live_now_candidate(cluster)
        ],
        key=sort_key,
        reverse=True,
    )
    selected = []
    for cluster in ranked:
        src = str(_primary_article(cluster).get("source") or "unknown")
        source_count[src] = source_count.get(src, 0) + 1
        if source_count[src] > 1:
            continue
        selected.append(cluster)
        if len(selected) >= limit:
            break
    return selected


def _is_latest_wire_article_candidate(article):
    title = cleanAndDecode((article or {}).get("title") or "")
    topic = cleanAndDecode((article or {}).get("topic") or "")
    category = cleanAndDecode((article or {}).get("category") or "")
    if not title or _title_looks_like_feature(title):
        return False
    if topic in _SOFT_EXCLUDE_TOPICS:
        return False
    if topic in _HARD_NEWS_TOPICS:
        return True
    return category in _HARD_NEWS_CATEGORIES


def _rank_latest_wire_articles(items, limit=15):
    seen_titles = set()
    source_count = {}
    candidates = []
    for article in items or []:
        if not _is_latest_wire_article_candidate(article):
            continue
        title = cleanAndDecode(article.get("title") or "").casefold()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        candidates.append(article)

    candidates.sort(
        key=lambda article: (
            -1 if cleanAndDecode(article.get("topic") or "") in _HARD_NEWS_TOPICS else 0,  # Negative for reverse sort
            -_parse_time(_article_freshness_time(article)),  # Negative for reverse sort
        ),
    )

    selected = []
    for article in candidates:
        src = str(article.get("source") or "unknown")
        source_count[src] = source_count.get(src, 0) + 1
        if source_count[src] > 2:
            continue
        selected.append(article)
        if len(selected) >= limit:
            break
    return selected


def _build_lead_display(cluster, lang: Optional[str] = "sr"):
    article = _primary_article(cluster)
    if not article:
        return {}
    source_count = len((cluster or {}).get("articles") or [])
    is_mk = str(lang or "sr").lower().startswith("mk")
    if cluster.get("is_breaking"):
        signal = "Најбрз развој денес" if is_mk else "Najbrži razvoj dana"
    elif source_count >= 6:
        signal = "Приказна што ја движи домашната агенда" if is_mk else "Priča koja pokreće domaću agendu"
    elif source_count >= 4:
        signal = "Тема што брзо се шири низ редакциите" if is_mk else "Tema koja se brzo širi kroz redakcije"
    else:
        signal = "развој што вреди да се следи" if is_mk else "razvoj koji vredi pratiti"

    # Prefer the synthetic standfirst if it exists, otherwise fall back to article summary
    summary = cluster.get("synthetic_standfirst") or _extract_preview_summary(article)
    
    return {
        "title": cluster.get("synthetic_headline") or cleanAndDecode(article.get("title") or ""),
        "summary": summary,
        "signal": signal,
    }


def _decorate_article_display(article):
    if not isinstance(article, dict):
        return article
    decorated = dict(article)
    decorated["display_title"] = cleanAndDecode(article.get("title") or "")
    decorated["display_summary"] = _extract_preview_summary(article)
    return decorated


def _decorate_cluster_display(cluster):
    if not isinstance(cluster, dict):
        return cluster
    decorated = dict(cluster)
    decorated["articles"] = [_decorate_article_display(article) for article in (cluster.get("articles") or [])]
    # Inject synthesized fields if they exist in the cluster data
    if "synthetic_headline" in cluster:
        decorated["synthetic_headline"] = cluster["synthetic_headline"]
    if "synthetic_standfirst" in cluster:
        decorated["synthetic_standfirst"] = cluster["synthetic_standfirst"]
    return decorated


def _decorate_articles_display(articles):
    return [_decorate_article_display(article) for article in (articles or [])]


def _decorate_clusters_display(clusters):
    return [_decorate_cluster_display(cluster) for cluster in (clusters or [])]


def _compact_home_cluster(cluster, max_articles=4):
    if not isinstance(cluster, dict):
        return cluster
    compact = dict(cluster)
    articles = list(cluster.get("articles") or [])
    compact["source_count"] = int(cluster.get("source_count") or len(articles))
    compact["sources_count"] = int(cluster.get("sources_count") or compact["source_count"])
    compact["articles"] = articles[:max_articles]
    return compact


def _compact_home_clusters(clusters, max_articles=4):
    return [_compact_home_cluster(cluster, max_articles=max_articles) for cluster in (clusters or [])]


def _normalize_focus_entity_name(name):
    return normalize_focus_entity_surface(name)


def _is_usable_focus_entity(name):
    clean = str(name or "").strip()
    if len(clean) < 4:
        return False
    folded = clean.casefold()
    if folded in _FOCUS_ENTITY_STOPWORDS:
        return False
    if clean.endswith("nj") or clean.endswith("нј"):
        return False
    return True


async def fetch_synthesis_picks(lang: str = "sr") -> List[Dict[str, Any]]:
    """Fetches the latest clusters that have a generated synthesis for the given language."""
    from collections import defaultdict
    from core.database import db_manager as db
    from utils import score_cluster, score_cluster_for_homepage, is_balanced, annotate_cluster_articles
    from routes.news import _compute_editorial_signals, _public_article_payload, _as_list, _parse_maybe_json
    from core.language import transliterate_cyr_to_lat, transliterate_lat_to_cyr

    # Get latest cluster IDs with synthesis for this language
    sql = """
        SELECT DISTINCT s.cluster_id, s.created_at
        FROM cluster_summaries s
        WHERE s.lang = %s
          AND COALESCE(s.synthetic_headline, '') != ''
          AND COALESCE(s.generated_article, '') != ''
          AND EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = s.cluster_id)
        ORDER BY s.created_at DESC
        LIMIT 4
    """
    rows = await db.async_execute(sql, (lang,), read_only=True)
    cids = [r["cluster_id"] for r in rows]
    if not cids:
        return []

    # Fetch articles in these clusters
    art_rows = await db.async_execute(
        "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
        (cids,),
        read_only=True,
    )

    clusters_grouped = defaultdict(list)
    for art in art_rows:
        cid = art["cluster_id"]
        clusters_grouped[cid].append(art)

    meta_rows = await db.async_execute(
        "SELECT cluster_id, representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = ANY(%s)",
        (cids,),
        read_only=True,
    )
    meta_map = {r["cluster_id"]: r for r in meta_rows}

    summary_rows = await db.async_execute(
        """
        SELECT cluster_id, synthetic_headline, synthetic_standfirst, key_facts,
               analyst_entities, pulse_score, pluralism_score, narrative_diversity,
               generated_article, quote
        FROM cluster_summaries
        WHERE cluster_id = ANY(%s) AND lang = %s
        """,
        (cids, lang),
        read_only=True,
    )
    summary_map = {r["cluster_id"]: r for r in summary_rows}

    formatted_clusters = []
    for cid in cids:
        arts = clusters_grouped.get(cid)
        if not arts:
            continue

        # Annotate articles in cluster
        arts = annotate_cluster_articles(arts)

        main = arts[0]
        s = score_cluster(arts)
        homepage_score = score_cluster_for_homepage(arts)
        editorial = _compute_editorial_signals(arts, s, homepage_score)
        meta = meta_map.get(cid, {})
        summary = summary_map.get(cid, {})

        fc = {
            "cluster_id": cid,
            "articles": [_public_article_payload(article, lang=lang) for article in arts],
            "representative_image": meta.get("representative_image"),
            "dominant_color": meta.get("dominant_color"),
            "synthetic_headline": summary.get("synthetic_headline"),
            "synthetic_standfirst": summary.get("synthetic_standfirst"),
            "generated_article": summary.get("generated_article"),
            "quote": summary.get("quote"),
            "key_facts": _as_list(summary.get("key_facts")),
            "analyst_entities": _as_list(summary.get("analyst_entities")),
            "pulse_score": summary.get("pulse_score"),
            "pluralism_score": summary.get("pluralism_score"),
            "narrative_diversity": _parse_maybe_json(summary.get("narrative_diversity")),
            "reading_time": main.get("reading_time", 1),
            "score": round(s, 3),
            "homepage_score": round(homepage_score, 3),
            "is_breaking": s >= 1.5,
            "has_synthesis": True,
            "has_fact_check": any(a.get("is_fact_check") for a in arts),
            "has_balanced": is_balanced(arts),
            "entities": [transliterate_cyr_to_lat(e) for e in main.get("entity_names", [])] if lang == "sr" else ([transliterate_lat_to_cyr(e) for e in main.get("entity_names", [])] if lang == "mk" else main.get("entity_names", [])),
            **editorial,
        }
        formatted_clusters.append(fc)

    return formatted_clusters


@router.get("/home", response_model=HomeResponse)
async def get_home(request: Request = None, lang: Optional[str] = "sr"):
    # Support legacy tests passing lang as a positional argument
    if isinstance(request, str):
        lang = request
        request = None

    from routes.common import _extract_sync_token
    sync_token = _extract_sync_token(request) if request else ""
    
    if sync_token:
        cache_key = f"api:home:v6:{lang}:personalized:{sync_token}"
    else:
        cache_key = f"api:home:v6:{lang}"
        
    cached = cached_response(cache_key, ttl=300)
    if cached:
        return cached

    try:
        # Fetch all dependencies in parallel
        results = await asyncio.gather(
            fetch_news_data(sort="score", page_size=72, lang=lang),
            get_trending_route(lang=lang),
            get_top_entities(limit=12, lang=lang),
            get_stats_summary(lang=lang),
            fetch_synthesis_picks(lang=lang),
            return_exceptions=True,
        )

        news_result, trending, top_entities, stats, synthesis_picks = results

        # Basic error check (ensure news_result is a dict)
        if isinstance(news_result, Exception):
            log.error(f"Home Route dependency error (news): {news_result}")
            raise news_result
        if not isinstance(news_result, dict):
            raise RuntimeError("Homepage news payload unavailable")

        # Unpack other results, handling exceptions
        if isinstance(trending, Exception):
            trending = []
        if isinstance(top_entities, Exception):
            top_entities = []
        if isinstance(stats, Exception):
            stats = {}
        if isinstance(synthesis_picks, Exception):
            log.error(f"Failed to fetch synthesis picks: {synthesis_picks}")
            synthesis_picks = []

        if hasattr(stats, "body") and hasattr(stats, "status_code"):
            import json
            try:
                stats = json.loads(stats.body.decode())
            except Exception as e:
                log.error(f"Failed to decode stats JSONResponse: {e}")
                stats = {}

        clusters = news_result.get("clusters") or []
        global_clusters = news_result.get("global_clusters") or []

        synthesis_pick_ids = {c["cluster_id"] for c in synthesis_picks}
        clusters = [c for c in clusters if c["cluster_id"] not in synthesis_pick_ids]
        clusters = _apply_synthesis_lead_tiebreak(clusters)

        lead = clusters[0] if clusters else None
        supporting = clusters[1:4]
        priority_audio_ids = set()
        priority_audio_budget = _AUDIO_PRIORITY_GENERATION_LIMIT

        def should_generate_priority_audio(cluster: Dict[str, Any]) -> bool:
            nonlocal priority_audio_budget
            if priority_audio_budget <= 0 or not cluster or not cluster.get("cluster_id"):
                return False
            filepath, _ = AudioService.get_cluster_audio_path_and_url(
                cluster["cluster_id"],
                cluster.get("lang", "sr"),
            )
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                return False
            priority_audio_budget -= 1
            return True

        if lead:
            lead = await _ensure_cluster_audio(lead, generate=should_generate_priority_audio(lead))
            priority_audio_ids.add(lead.get("cluster_id"))
            clusters[0] = lead

        for idx, cluster in enumerate(supporting, start=1):
            supporting[idx - 1] = await _ensure_cluster_audio(
                cluster,
                generate=should_generate_priority_audio(cluster),
            )
            priority_audio_ids.add(cluster.get("cluster_id"))
            clusters[idx] = supporting[idx - 1]

        for idx, cluster in enumerate(global_clusters[:2]):
            global_clusters[idx] = await _ensure_cluster_audio(
                cluster,
                generate=should_generate_priority_audio(cluster),
            )
            priority_audio_ids.add(cluster.get("cluster_id"))

        # Personalization Engine
        for_you_pool = []
        if sync_token:
            try:
                from routes.profile import get_personalized_news_by_profile, _normalize_synced_profile
                from core.database import db_manager as db
                row = await db.async_execute_one(
                    "SELECT profile_data FROM synced_reader_profiles WHERE sync_token = %s",
                    (sync_token,),
                )
                if row:
                    profile = _normalize_synced_profile(row.get("profile_data") or {})
                    for_you_pool = await get_personalized_news_by_profile(profile, limit=6, lang=lang)
            except Exception as pe:
                log.error(f"Failed to fetch personalized news for homepage (token {sync_token}): {pe}")
                for_you_pool = []

        if not for_you_pool:
            for_you_pool = [c for c in clusters[_HOMEPAGE_FEED_START : _HOMEPAGE_FEED_START + 6] if _is_live_now_candidate(c)]
            for_you_pool = [await _ensure_cluster_audio(c, generate=False) for c in for_you_pool]

        feed_clusters = list(clusters[_HOMEPAGE_FEED_START:])
        developing = [
            cluster
            for cluster in feed_clusters
            if (
                (
                    str(cluster.get("story_state") or "") in {"breaking", "developing", "confirmed"}
                    and int(cluster.get("source_count") or len(cluster.get("articles") or [])) >= 2
                )
                or len(cluster.get("articles") or []) >= 2
            )
        ]
        developing.sort(key=_homepage_developing_sort_key, reverse=True)
        developing = developing[:_HOMEPAGE_DEVELOPING_LIMIT]
        developing_ids = {c.get("cluster_id") for c in developing if c.get("cluster_id")}
        if not sync_token:
            for_you_pool = [c for c in for_you_pool if c.get("cluster_id") not in developing_ids]

        wire = [
            cluster
            for cluster in feed_clusters
            if cluster.get("cluster_id") not in developing_ids
            and (
                cluster.get("latest_wire_fit")
                or str(cluster.get("story_state") or "") == "singleton"
                or len(cluster.get("articles") or []) < 2
            )
        ][: _HOMEPAGE_WIRE_LIMIT]

        excluded_cluster_ids = [
            cluster_id
            for cluster_id in [
                lead.get("cluster_id") if lead else None,
                *[c.get("cluster_id") for c in supporting],
                *[c.get("cluster_id") for c in (synthesis_picks or [])],
            ]
            if cluster_id
        ]
        recent_clusters = _clusters_sorted_by_recency(clusters)
        live_now = _rank_live_now_clusters(recent_clusters, exclude_cluster_ids=excluded_cluster_ids, limit=4)
        for idx, cluster in enumerate(live_now):
            should_generate = (
                cluster.get("cluster_id") not in priority_audio_ids
                and should_generate_priority_audio(cluster)
            )
            live_now[idx] = await _ensure_cluster_audio(cluster, generate=should_generate)
            priority_audio_ids.add(cluster.get("cluster_id"))

        raw_wire_articles = []
        recent_clusters = [await _ensure_cluster_audio(c, generate=False) for c in (recent_clusters or [])]

        seen_links = set()
        for cluster in recent_clusters or []:
            for article in cluster.get("articles") or []:
                link = article.get("link")
                if link and link in seen_links:
                    continue
                if link:
                    seen_links.add(link)
                raw_wire_articles.append(article)
        latest_wire = _rank_latest_wire_articles(raw_wire_articles, limit=15)

        focus_entities = []
        seen_focus_entities = set()
        for entity in top_entities if isinstance(top_entities, list) else []:
            normalized = dict(entity)
            raw_name = str(entity.get("name") or "").strip()
            display_name = _normalize_focus_entity_name(raw_name)
            key = display_name.casefold()
            normalized["name"] = display_name
            normalized["display_name"] = display_name
            if _is_usable_focus_entity(display_name) and key not in seen_focus_entities:
                seen_focus_entities.add(key)
                focus_entities.append(normalized)

        response = {
            "status": "success",
            "pipeline": reader_pipeline_status(),
            "lead": _compact_home_cluster(_decorate_cluster_display(lead), max_articles=4),
            "lead_display": _build_lead_display(lead, lang=lang),
            "supporting": _compact_home_clusters(_decorate_clusters_display(supporting), max_articles=4),
            "synthesis_picks": _compact_home_clusters(_decorate_clusters_display(synthesis_picks), max_articles=4),
            "live_now": _compact_home_clusters(_decorate_clusters_display(live_now), max_articles=4),
            "for_you_pool": _compact_home_clusters(_decorate_clusters_display(for_you_pool), max_articles=3),
            "developing": _compact_home_clusters(_decorate_clusters_display(developing), max_articles=4),
            "wire": _compact_home_clusters(_decorate_clusters_display(wire), max_articles=2),
            "latest_wire": _decorate_articles_display(latest_wire),
            "global": _compact_home_clusters(_decorate_clusters_display(global_clusters), max_articles=4),
            "stats": stats,
            "trending": trending if isinstance(trending, list) else [],
            "focus_entities": focus_entities[:10],
            "excluded_cluster_ids": excluded_cluster_ids,
        }
        set_cache(cache_key, response, ttl=300)
        return response
    except Exception as exc:
        log.error(f"Home Route Error: {exc}", exc_info=True)
        return {"status": "error", "message": "Failed to load homepage"}


@router.get("/home/live-now")
async def get_home_live_now(exclude: str = "", lang: Optional[str] = "sr"):
    cache_key = f"api:home:live-now:v3:{exclude}:{lang}"
    cached = cached_response(cache_key, ttl=60)
    if cached:
        return cached
    try:
        recent_result = await fetch_news_data(sort="recent", page_size=24, lang=lang)
        exclude_cluster_ids = [
            token.strip() for token in str(exclude or "").split(",") if token.strip() and len(token.strip()) <= 80
        ]
        recent_clusters = recent_result.get("clusters") if isinstance(recent_result, dict) else []
        response = {
            "status": "success",
            "clusters": _rank_live_now_clusters(recent_clusters, exclude_cluster_ids=exclude_cluster_ids, limit=4),
        }
        set_cache(cache_key, response, ttl=60)
        return response
    except Exception as exc:
        log.error(f"Home Live Route Error: {exc}", exc_info=True)
        return {"status": "error", "clusters": []}


@router.get("/home/latest-wire")
async def get_home_latest_wire(limit: int = 15, lang: Optional[str] = "sr"):
    bounded_limit = max(1, min(int(limit or 15), 30))
    cache_key = f"api:home:latest-wire:v3:{bounded_limit}:{lang}"
    cached = cached_response(cache_key, ttl=120)
    if cached:
        return cached
    try:
        recent_result = await fetch_news_data(sort="recent", page_size=24, lang=lang)
        recent_clusters = recent_result.get("clusters") if isinstance(recent_result, dict) else []
        raw_wire_articles = []
        seen_links = set()
        for cluster in recent_clusters or []:
            for article in cluster.get("articles") or []:
                link = article.get("link")
                if link and link in seen_links:
                    continue
                if link:
                    seen_links.add(link)
                raw_wire_articles.append(article)
        response = {
            "status": "success",
            "articles": _rank_latest_wire_articles(raw_wire_articles, limit=bounded_limit),
        }
        set_cache(cache_key, response, ttl=120)
        return response
    except Exception as exc:
        log.error(f"Home Latest Wire Route Error: {exc}", exc_info=True)
        return {"status": "error", "articles": []}
