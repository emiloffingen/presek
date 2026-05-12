import logging
import re
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from utils import cached_response, set_cache
from .common import cleanAndDecode
from .intelligence import get_top_entities
from .news import get_news
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
    "Balkan",
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


def _primary_article(cluster):
    return (cluster or {}).get("articles", [{}])[0] or {}


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
    text = str(
        (article or {}).get("summary") or (article or {}).get("description") or ""
    )
    trimmed = text.strip()
    if (
        trimmed.startswith("{")
        or trimmed.startswith("&lt;%")
        or "&quot;summary&quot;" in trimmed
    ):
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
            if cluster
            and cluster.get("cluster_id") not in exclude
            and _is_live_now_candidate(cluster)
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
            1 if cleanAndDecode(article.get("topic") or "") in _HARD_NEWS_TOPICS else 0,
            _parse_time(_article_freshness_time(article)),
        ),
        reverse=True,
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


def _build_lead_display(cluster):
    article = _primary_article(cluster)
    if not article:
        return {}
    source_count = len((cluster or {}).get("articles") or [])
    if cluster.get("is_breaking"):
        signal = "Najbrz razvoj vo denot"
    elif source_count >= 6:
        signal = "prica sto me dvizi domasnata agenda"
    elif source_count >= 4:
        signal = "Tema sto brzo se siri niz redakciite"
    else:
        signal = "razvoj sto vredi da se sledi"
    return {
        "title": cleanAndDecode(article.get("title") or ""),
        "summary": _extract_preview_summary(article),
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
    decorated["articles"] = [
        _decorate_article_display(article)
        for article in (cluster.get("articles") or [])
    ]
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


def _display_entity_name(name):
    clean = str(name or "").strip()
    if not clean:
        return ""
    return f"{clean[0].upper()}{clean[1:]}"


@router.get("/home", response_model=HomeResponse)
async def get_home(lang: Optional[str] = None):
    cache_key = f"api:home:v3:{lang}"
    cached = cached_response(cache_key, ttl=3600)
    if cached:
        return cached

    try:
        # Fetch all dependencies in parallel
        results = await asyncio.gather(
            get_news(page_size=48, lang=lang),
            get_news(sort="recent", page_size=24, lang=lang),
            get_trending_route(),
            get_top_entities(limit=12),
            get_stats_summary(),
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

        clusters = news_result.get("clusters") or []
        global_clusters = news_result.get("global_clusters") or []

        lead = clusters[0] if clusters else None
        supporting = clusters[1:5]
        for_you_pool = clusters[5:11]
        feed_clusters = clusters[11:]
        developing = [
            cluster
            for cluster in feed_clusters
            if (
                (
                    str(cluster.get("story_state") or "")
                    in {"breaking", "developing", "confirmed"}
                    and int(
                        cluster.get("source_count")
                        or len(cluster.get("articles") or [])
                    )
                    >= 2
                )
                or len(cluster.get("articles") or []) >= 2
            )
        ]
        wire = [
            cluster
            for cluster in feed_clusters
            if cluster.get("latest_wire_fit")
            or str(cluster.get("story_state") or "") == "singleton"
            or len(cluster.get("articles") or []) < 2
        ][:12]

        excluded_cluster_ids = [
            cluster_id
            for cluster_id in [
                lead.get("cluster_id") if lead else None,
                *[c.get("cluster_id") for c in supporting],
            ]
            if cluster_id
        ]
        recent_clusters = (
            recent_result.get("clusters") if isinstance(recent_result, dict) else []
        )
        live_now = _rank_live_now_clusters(
            recent_clusters, exclude_cluster_ids=excluded_cluster_ids, limit=4
        )

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
        latest_wire = _rank_latest_wire_articles(raw_wire_articles, limit=15)

        focus_entities = []
        for entity in top_entities if isinstance(top_entities, list) else []:
            normalized = dict(entity)
            raw_name = str(entity.get("name") or "").strip()
            normalized["name"] = raw_name
            normalized["display_name"] = _display_entity_name(raw_name)
            if raw_name and len(raw_name) >= 3:
                focus_entities.append(normalized)

        response = {
            "status": "success",
            "lead": _decorate_cluster_display(lead),
            "lead_display": _build_lead_display(lead),
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
        set_cache(cache_key, response, ttl=3600)
        return response
    except Exception as exc:
        log.error(f"Home Route Error: {exc}", exc_info=True)
        return {"status": "error", "message": "Failed to load homepage"}


@router.get("/home/live-now")
async def get_home_live_now(exclude: str = ""):
    cache_key = f"api:home:live-now:v1:{exclude}"
    cached = cached_response(cache_key, ttl=60)
    if cached:
        return cached
    try:
        recent_result = await get_news(sort="recent", page_size=24)
        exclude_cluster_ids = [
            token.strip()
            for token in str(exclude or "").split(",")
            if token.strip() and len(token.strip()) <= 80
        ]
        recent_clusters = (
            recent_result.get("clusters") if isinstance(recent_result, dict) else []
        )
        response = {
            "status": "success",
            "clusters": _rank_live_now_clusters(
                recent_clusters, exclude_cluster_ids=exclude_cluster_ids, limit=4
            ),
        }
        set_cache(cache_key, response, ttl=60)
        return response
    except Exception as exc:
        log.error(f"Home Live Route Error: {exc}", exc_info=True)
        return {"status": "error", "clusters": []}


@router.get("/home/latest-wire")
async def get_home_latest_wire(limit: int = 15):
    bounded_limit = max(1, min(int(limit or 15), 30))
    cache_key = f"api:home:latest-wire:v1:{bounded_limit}"
    cached = cached_response(cache_key, ttl=120)
    if cached:
        return cached
    try:
        recent_result = await get_news(sort="recent", page_size=24)
        recent_clusters = (
            recent_result.get("clusters") if isinstance(recent_result, dict) else []
        )
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
            "articles": _rank_latest_wire_articles(
                raw_wire_articles, limit=bounded_limit
            ),
        }
        set_cache(cache_key, response, ttl=120)
        return response
    except Exception as exc:
        log.error(f"Home Latest Wire Route Error: {exc}", exc_info=True)
        return {"status": "error", "articles": []}
