import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from utils import cached_response, set_cache

from core.audio_service import AudioService
from .common import cleanAndDecode
from .intelligence import get_top_entities
from .news import fetch_news_data
from .stats import get_stats_summary
from .system import get_trending_route

log = logging.getLogger("presek")
router = APIRouter()


class HomeResponse(BaseModel):
    status: str
    lead: Optional[Any] = None
    lead_display: Optional[Dict[str, Any]] = None
    supporting: List[Any] = Field(default_factory=list)
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


async def _ensure_cluster_audio(cluster: Dict[str, Any]) -> Dict[str, Any]:
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
        # Check if cluster has generated synthesis content
        if cluster.get('generated_article') or cluster.get('synthesis'):
            content = cluster.get('generated_article') or cluster.get('synthesis') or ""
            if content and len(content.strip()) > 50:  # Only generate for substantial content
                log.info(f"[home] Cluster {cluster_id} has synthesis, ensuring audio generation")
                
                # Generate audio in background (non-blocking)
                asyncio.create_task(_generate_cluster_audio_background(cluster_id, content, lang))
                
                # Check if audio already exists
                filepath, urlpath = AudioService.get_cluster_audio_path_and_url(cluster_id, lang)
                if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                    cluster['audio_url'] = urlpath
                    cluster['has_audio'] = True
                    log.info(f"[home] Audio already exists for cluster {cluster_id}: {urlpath}")
                else:
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

_FOCUS_ENTITY_NORMALIZATIONS = {
    "srbije": "Srbija",
    "srbiji": "Srbija",
    "srbijom": "Srbija",
    "srbiju": "Srbija",
    "србије": "Србија",
    "србији": "Србија",
    "србијом": "Србија",
    "србију": "Србија",
    "beogradu": "Beograd",
    "beograda": "Beograd",
    "београду": "Београд",
    "београда": "Београд",
    "kine": "Kina",
    "kini": "Kina",
    "kinom": "Kina",
    "кине": "Кина",
    "кини": "Кина",
    "кином": "Кина",
    "rusije": "Rusija",
    "rusiji": "Rusija",
    "rusijom": "Rusija",
    "русије": "Русија",
    "русији": "Русија",
    "русијом": "Русија",
    "ukrajine": "Ukrajina",
    "ukrajini": "Ukrajina",
    "ukrajinom": "Ukrajina",
    "ukrajinu": "Ukrajina",
    "украјине": "Украјина",
    "украјини": "Украјина",
    "украјином": "Украјина",
    "украјину": "Украјина",
    "partizana": "Partizan",
    "partizanu": "Partizan",
    "партизана": "Партизан",
    "партизану": "Партизан",
    "zvezde": "Crvena zvezda",
    "zvezdi": "Crvena zvezda",
    "zvezda": "Crvena zvezda",
}
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
    text = str((article or {}).get("summary") or (article or {}).get("description") or "")
    trimmed = text.strip()
    if trimmed.startswith("{") or trimmed.startswith("&lt;%") or "&quot;summary&quot;" in trimmed:
        try:
            decoded = cleanAndDecode(trimmed) if "&quot;" in trimmed else trimmed
            if decoded.startswith("{"):
                import json

                parsed = json.loads(decoded)
                text = str(parsed.get("summary") or parsed.get("text") or text)
        except Exception:
            pass
    return cleanAndDecode(text)


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


def _normalize_focus_entity_name(name):
    clean = str(name or "").strip()
    if not clean:
        return ""
    clean = re.sub(r"\s+", " ", clean)
    normalized = _FOCUS_ENTITY_NORMALIZATIONS.get(clean.casefold(), clean)
    return f"{normalized[0].upper()}{normalized[1:]}"


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
            fetch_news_data(sort="score", page_size=80, lang=lang),
            fetch_news_data(sort="recent", page_size=24, lang=lang),
            get_trending_route(lang=lang),
            get_top_entities(limit=12, lang=lang),
            get_stats_summary(lang=lang),
            return_exceptions=True,
        )

        news_result, recent_result, trending, top_entities, stats = results

        # Basic error check (ensure news_result is a dict)
        if isinstance(news_result, Exception):
            log.error(f"Home Route dependency error (news): {news_result}")
            raise news_result
        if not isinstance(news_result, dict):
            raise RuntimeError("Homepage news payload unavailable")

        # Unpack other results, handling exceptions
        if isinstance(recent_result, Exception):
            recent_result = {}
        if isinstance(trending, Exception):
            trending = []
        if isinstance(top_entities, Exception):
            top_entities = []
        if isinstance(stats, Exception):
            stats = {}

        if hasattr(stats, "body") and hasattr(stats, "status_code"):
            import json
            try:
                stats = json.loads(stats.body.decode())
            except Exception as e:
                log.error(f"Failed to decode stats JSONResponse: {e}")
                stats = {}

        clusters = news_result.get("clusters") or []
        global_clusters = news_result.get("global_clusters") or []

        # Ensure audio generation for clusters with syntheses
        clusters = [await _ensure_cluster_audio(cluster) for cluster in clusters]
        global_clusters = [await _ensure_cluster_audio(cluster) for cluster in global_clusters]

        lead = clusters[0] if clusters else None
        supporting = clusters[1:5]

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
            for_you_pool = [c for c in clusters[5:11] if _is_live_now_candidate(c)]
            # Ensure audio for personalized clusters too
            for_you_pool = [await _ensure_cluster_audio(c) for c in for_you_pool]

        feed_clusters = list(clusters[5:])
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
        ][:12]

        excluded_cluster_ids = [
            cluster_id
            for cluster_id in [
                lead.get("cluster_id") if lead else None,
                *[c.get("cluster_id") for c in supporting],
            ]
            if cluster_id
        ]
        recent_clusters = recent_result.get("clusters") if isinstance(recent_result, dict) else []
        live_now = _rank_live_now_clusters(recent_clusters, exclude_cluster_ids=excluded_cluster_ids, limit=4)

        raw_wire_articles = []
        # Ensure audio for recent clusters
        recent_clusters = [await _ensure_cluster_audio(c) for c in (recent_clusters or [])]

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
            "lead": _decorate_cluster_display(lead),
            "lead_display": _build_lead_display(lead, lang=lang),
            "supporting": _decorate_clusters_display(supporting),
            "live_now": _decorate_clusters_display(live_now),
            "for_you_pool": _decorate_clusters_display(for_you_pool),
            "developing": _decorate_clusters_display(developing),
            "wire": _decorate_clusters_display(wire),
            "latest_wire": _decorate_articles_display(latest_wire),
            "global": _decorate_clusters_display(global_clusters),
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
