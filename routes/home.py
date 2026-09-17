import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.api_errors import soft_error
from core.queue_status import reader_pipeline_status
from utils import cached_response, set_cache

from .common import cleanAndDecode
from .news import fetch_news_data
from .stats import get_stats_summary
from .system import get_trending_route

log = logging.getLogger("presek")
router = APIRouter()
_background_tasks: set[asyncio.Task] = set()
_LEAD_TIEBREAK_WINDOW = 0.10
_HOMEPAGE_HERO_COUNT = 4
_HOMEPAGE_HERO_CANDIDATE_POOL = 20
_HOMEPAGE_FEED_START = 5
_HOMEPAGE_DEVELOPING_LIMIT = 10
_HOMEPAGE_WIRE_LIMIT = 11
_HOMEPAGE_DEVELOPING_BACKFILL_MIN = 4
_HOMEPAGE_LIVE_NOW_BACKFILL_MIN = 2


def _cluster_source_count(cluster: Dict[str, Any]) -> int:
    declared = cluster.get("source_count")
    if declared is not None:
        try:
            return max(0, int(declared))
        except (TypeError, ValueError):
            pass
    articles = cluster.get("articles") or []
    return len({a.get("source") for a in articles if a.get("source")})


def _is_primary_developing_cluster(cluster: Dict[str, Any]) -> bool:
    source_count = _cluster_source_count(cluster)
    story_state = str(cluster.get("story_state") or "")
    articles = cluster.get("articles") or []
    return (story_state in {"breaking", "developing", "confirmed"} and source_count >= 2) or len(articles) >= 2


def _fill_developing_clusters(
    feed_clusters: List[Dict[str, Any]],
    *,
    exclude_ids: set[str],
    limit: int,
    backfill_min: int = _HOMEPAGE_DEVELOPING_BACKFILL_MIN,
) -> List[Dict[str, Any]]:
    developing = [
        cluster
        for cluster in feed_clusters
        if cluster.get("cluster_id") not in exclude_ids and _is_primary_developing_cluster(cluster)
    ]
    developing.sort(key=_homepage_developing_sort_key, reverse=True)

    if len(developing) >= backfill_min:
        return developing[:limit]

    seen = {cluster.get("cluster_id") for cluster in developing if cluster.get("cluster_id")}
    seen |= set(exclude_ids)

    relaxed = [
        cluster
        for cluster in feed_clusters
        if cluster.get("cluster_id")
        and cluster.get("cluster_id") not in seen
        and _cluster_source_count(cluster) >= 2
    ]
    relaxed.sort(key=_homepage_developing_sort_key, reverse=True)
    for cluster in relaxed:
        if len(developing) >= backfill_min:
            break
        developing.append(cluster)
        seen.add(cluster.get("cluster_id"))

    if len(developing) < backfill_min:
        fallback = [
            cluster for cluster in feed_clusters if cluster.get("cluster_id") and cluster.get("cluster_id") not in seen
        ]
        fallback.sort(key=_homepage_developing_sort_key, reverse=True)
        for cluster in fallback:
            if len(developing) >= backfill_min:
                break
            developing.append(cluster)
            seen.add(cluster.get("cluster_id"))

    return developing[:limit]


def _homepage_developing_sort_key(cluster: Dict[str, Any]) -> tuple:
    source_count = int(cluster.get("source_count") or len(cluster.get("articles") or []))
    return (
        source_count,
        float(cluster.get("homepage_score") or 0.0),
    )


def _homepage_cluster_score(cluster: Dict[str, Any]) -> float:
    return float(cluster.get("homepage_score") or 0.0)


def _merge_clusters_by_id(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: dict[str, Dict[str, Any]] = {}
    order: list[str] = []
    for group in groups:
        for cluster in group or []:
            cluster_id = str(cluster.get("cluster_id") or "").strip()
            if not cluster_id:
                continue
            if cluster_id not in merged:
                order.append(cluster_id)
                merged[cluster_id] = cluster
                continue
            existing = merged[cluster_id]
            if cluster.get("generated_article") and not existing.get("generated_article"):
                merged[cluster_id] = {**existing, **cluster}
    return [merged[cluster_id] for cluster_id in order]


def _select_homepage_hero_clusters(
    clusters: List[Dict[str, Any]],
    *,
    hero_count: int = _HOMEPAGE_HERO_COUNT,
    candidate_pool: int = _HOMEPAGE_HERO_CANDIDATE_POOL,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Pick lead + supporting clusters based on score."""
    pool = clusters[:candidate_pool]
    if not pool:
        return [], list(clusters)

    sorted_pool = sorted(pool, key=_homepage_cluster_score, reverse=True)
    hero = sorted_pool[:hero_count]
    used_ids = {str(cluster["cluster_id"]) for cluster in hero if cluster.get("cluster_id")}
    remainder = [cluster for cluster in clusters if cluster.get("cluster_id") not in used_ids]
    return hero, remainder


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
    live_now: List[Any] = Field(default_factory=list)
    developing: List[Any] = Field(default_factory=list)
    wire: List[Any] = Field(default_factory=list)
    latest_wire: List[Any] = Field(default_factory=list)
    global_: List[Any] = Field(default_factory=list, alias="global")
    trending: List[Any] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)
    excluded_cluster_ids: List[str] = Field(default_factory=list)
    pipeline: Optional[Dict[str, Any]] = None
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
    # Simple truncation - no AI summarization
    if len(text) > 200:
        text = text[:197] + "..."
    return text


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
            -1 if cleanAndDecode(article.get("topic") or "") in _HARD_NEWS_TOPICS else 0,
            -_parse_time(_article_freshness_time(article)),
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


def _build_lead_display(cluster, lang: Optional[str] = "mk"):
    article = _primary_article(cluster)
    if not article:
        return {}
    source_count = len((cluster or {}).get("articles") or [])
    if cluster.get("is_breaking"):
        signal = "Најбрз развој денес"
    elif source_count >= 6:
        signal = "Приказна што ја движи домашната агенда"
    elif source_count >= 4:
        signal = "Тема што брзо се шири низ редакциите"
    else:
        signal = "развој што вреди да се следи"

    summary = _extract_preview_summary(article)

    return {
        "title": cleanAndDecode(article.get("title") or ""),
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


@router.get("/home", response_model=HomeResponse)
async def get_home(request: Request = None, lang: Optional[str] = "mk"):
    if isinstance(request, str):
        lang = request
        request = None

    cache_key = f"api:home:v8:{lang}"
    cached = cached_response(cache_key, ttl=300)
    if cached:
        return cached

    try:
        results = await asyncio.gather(
            fetch_news_data(sort="score", page_size=72, lang=lang),
            get_trending_route(lang=lang),
            get_stats_summary(lang=lang),
            return_exceptions=True,
        )

        news_result, trending, stats = results

        if isinstance(news_result, Exception):
            log.error(f"Home Route dependency error (news): {news_result}")
            raise news_result
        if not isinstance(news_result, dict):
            raise RuntimeError("Homepage news payload unavailable")

        if isinstance(trending, Exception):
            trending = []
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

        hero, remainder = _select_homepage_hero_clusters(clusters)
        hero_ids = {cluster.get("cluster_id") for cluster in hero if cluster.get("cluster_id")}
        clusters = hero + remainder

        lead = hero[0] if hero else None
        supporting = hero[1:_HOMEPAGE_HERO_COUNT]

        feed_clusters = list(clusters[_HOMEPAGE_FEED_START:])
        developing = _fill_developing_clusters(
            feed_clusters,
            exclude_ids=hero_ids,
            limit=_HOMEPAGE_DEVELOPING_LIMIT,
        )
        developing_ids = {c.get("cluster_id") for c in developing if c.get("cluster_id")}

        wire = [
            cluster
            for cluster in feed_clusters
            if cluster.get("cluster_id") not in developing_ids
            and (
                cluster.get("latest_wire_fit")
                or str(cluster.get("story_state") or "") == "singleton"
                or len(cluster.get("articles") or []) < 2
            )
        ][:_HOMEPAGE_WIRE_LIMIT]

        excluded_cluster_ids = list(hero_ids)
        recent_clusters = _clusters_sorted_by_recency(clusters)
        live_now = _rank_live_now_clusters(
            recent_clusters,
            exclude_cluster_ids=set(excluded_cluster_ids),
            limit=4,
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

        response = {
            "status": "success",
            "pipeline": reader_pipeline_status(),
            "lead": _compact_home_cluster(_decorate_cluster_display(lead), max_articles=4),
            "lead_display": _build_lead_display(lead, lang=lang),
            "supporting": _compact_home_clusters(_decorate_clusters_display(supporting), max_articles=4),
            "live_now": _compact_home_clusters(_decorate_clusters_display(live_now), max_articles=4),
            "developing": _compact_home_clusters(_decorate_clusters_display(developing), max_articles=4),
            "wire": _compact_home_clusters(_decorate_clusters_display(wire), max_articles=2),
            "latest_wire": _decorate_articles_display(latest_wire),
            "global": _compact_home_clusters(_decorate_clusters_display(global_clusters), max_articles=4),
            "stats": stats,
            "trending": trending if isinstance(trending, list) else [],
            "excluded_cluster_ids": excluded_cluster_ids,
        }
        set_cache(cache_key, response, ttl=300)
        return response
    except Exception as exc:
        log.error(f"Home Route Error: {exc}", exc_info=True)
        return soft_error(message="Failed to load homepage")


@router.get("/home/live-now")
async def get_home_live_now(exclude: str = "", lang: Optional[str] = "mk"):
    cache_key = f"api:home:live-now:v4:{exclude}:{lang}"
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
        return soft_error(clusters=[])


@router.get("/home/latest-wire")
async def get_home_latest_wire(limit: int = 15, lang: Optional[str] = "mk"):
    bounded_limit = max(1, min(int(limit or 15), 30))
    cache_key = f"api:home:latest-wire:v4:{bounded_limit}:{lang}"
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
        return soft_error(articles=[])
