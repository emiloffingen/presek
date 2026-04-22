import logging
import re
from fastapi import APIRouter

from utils import cached_response, set_cache
from .intelligence import get_top_entities
from .news import get_news
from .stats import get_briefing, get_stats_summary
from .system import get_trending_route

log = logging.getLogger("presek")
router = APIRouter()

_SOFT_EXCLUDE_TOPICS = {"Живот", "Забава", "Здравје"}
_HARD_NEWS_TOPICS = {"Политика", "Економија", "Криминал", "Спорт", "Технологија"}
_HARD_NEWS_CATEGORIES = {"Македонија", "Балкан", "Европа", "Германија", "Америка", "Свет"}
_FEATURE_PATTERNS = [
    re.compile(r"издание на", re.IGNORECASE),
    re.compile(r"интервју со", re.IGNORECASE),
    re.compile(r"интервју\b", re.IGNORECASE),
    re.compile(r"проверете дали", re.IGNORECASE),
    re.compile(r"пред да ", re.IGNORECASE),
    re.compile(r"постојано сте уморни", re.IGNORECASE),
    re.compile(r"овој минерал", re.IGNORECASE),
    re.compile(r"хороскоп", re.IGNORECASE),
    re.compile(r"рецепт", re.IGNORECASE),
    re.compile(r"фото\b", re.IGNORECASE),
    re.compile(r"видео\b", re.IGNORECASE),
    re.compile(r"галерија", re.IGNORECASE),
]


def _primary_article(cluster):
    return (cluster or {}).get("articles", [{}])[0] or {}


def _title_looks_like_feature(title):
    clean = str(title or "").strip()
    if not clean:
        return True
    if len(clean) > 180:
        return True
    if "?" in clean:
        return True
    return any(pattern.search(clean) for pattern in _FEATURE_PATTERNS)


def _parse_time(value):
    try:
        from utils import _coerce_datetime

        dt = _coerce_datetime(value)
        return dt.timestamp() if dt else 0
    except Exception:
        return 0


def _is_live_now_candidate(cluster):
    if "live_now_fit" in (cluster or {}):
        return bool(cluster.get("live_now_fit"))
    article = _primary_article(cluster)
    title = str(article.get("title") or "").strip()
    topic = str(article.get("topic") or "").strip()
    category = str(article.get("category") or "").strip()

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
                _parse_time(article.get("created_at")),
            )
        return (
            1 if cluster.get("is_breaking") else 0,
            1 if str(article.get("topic") or "").strip() in _HARD_NEWS_TOPICS else 0,
            _parse_time(article.get("created_at")),
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
    title = str((article or {}).get("title") or "").strip()
    topic = str((article or {}).get("topic") or "").strip()
    category = str((article or {}).get("category") or "").strip()
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
        title = str(article.get("title") or "").strip().lower()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        candidates.append(article)

    candidates.sort(
        key=lambda article: (
            1 if str(article.get("topic") or "").strip() in _HARD_NEWS_TOPICS else 0,
            _parse_time(article.get("created_at")),
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


def _normalize_focus_name(name):
    clean = re.sub(r"\s+", " ", str(name or "")).strip()
    clean = re.sub(r'^[-–—,.;:!?()[\]{}"\' ]+|[-–—,.;:!?()[\]{}"\' ]+$', "", clean)
    if not clean:
        return ""
    if re.fullmatch(r"[A-Za-zА-Яа-яЀ-ӿ\s-]+", clean) and clean == clean.lower():
        return " ".join(part[:1].upper() + part[1:] if part else part for part in clean.split(" "))
    return clean


@router.get("/home")
async def get_home():
    cache_key = "api:home:v1"
    cached = cached_response(cache_key, ttl=120)
    if cached:
        return cached
    try:
        news_result = await get_news(page_size=48)
        recent_result = await get_news(sort="recent", page_size=24)
        trending = await get_trending_route()
        top_entities = await get_top_entities(limit=12)
        stats = await get_stats_summary()
        briefing = await get_briefing()

        if not isinstance(news_result, dict):
            raise RuntimeError("Homepage news payload unavailable")

        clusters = news_result.get("clusters") or []
        global_clusters = news_result.get("global") or []

        lead = clusters[0] if clusters else None
        supporting = clusters[1:5]
        for_you_pool = clusters[5:11]
        feed_clusters = clusters[11:]
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
        wire = [
            cluster
            for cluster in feed_clusters
            if cluster.get("latest_wire_fit") or str(cluster.get("story_state") or "") == "singleton" or len(cluster.get("articles") or []) < 2
        ][:12]

        excluded_cluster_ids = [cluster_id for cluster_id in [lead.get("cluster_id") if lead else None, *[c.get("cluster_id") for c in supporting]] if cluster_id]
        recent_clusters = recent_result.get("clusters") if isinstance(recent_result, dict) else []
        live_now = _rank_live_now_clusters(recent_clusters, exclude_cluster_ids=excluded_cluster_ids, limit=4)

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
            normalized["name"] = _normalize_focus_name(entity.get("name", ""))
            if normalized["name"] and len(normalized["name"]) >= 3:
                focus_entities.append(normalized)

        response = {
            "status": "success",
            "lead": lead,
            "supporting": supporting,
            "live_now": live_now,
            "for_you_pool": for_you_pool,
            "developing": developing,
            "wire": wire,
            "latest_wire": latest_wire,
            "global": global_clusters,
            "stats": stats,
            "briefing": briefing,
            "trending": trending if isinstance(trending, list) else [],
            "focus_entities": focus_entities[:10],
            "excluded_cluster_ids": excluded_cluster_ids,
        }
        set_cache(cache_key, response, ttl=120)
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
async def get_home_latest_wire(limit: int = 15):
    bounded_limit = max(1, min(int(limit or 15), 30))
    cache_key = f"api:home:latest-wire:v1:{bounded_limit}"
    cached = cached_response(cache_key, ttl=120)
    if cached:
        return cached
    try:
        recent_result = await get_news(sort="recent", page_size=24)
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
