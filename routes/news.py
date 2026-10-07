import asyncio
import os
import datetime
import json
import logging
import re
from collections import defaultdict
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.api_errors import soft_error
from core.config import API_MAX_PAGE, API_MAX_Q_LEN, BREAKING_SCORE_THRESHOLD, DEFAULT_LANG
from core.database import db_manager as db
from core.embeddings import local_similarity
from core.input_validation import validate_cluster_id as validate_cluster_id_input
from core.input_validation import validate_language_code
from core.language import is_cyrillic_south_slavic, transliterate_cyr_to_lat, transliterate_lat_to_cyr
from core.queue_status import reader_pipeline_status
from core.synthesis_quality import build_synthesis_meta, synthesis_needs_upgrade
from core.trust_signals import build_trust_summary
from nlp import filter_cluster_tags
from utils import (
    _coerce_datetime,
    annotate_cluster_articles,
    assess_cluster_synthesis_freshness,
    build_read_next_clusters,
    cached_response,
    calculate_reading_time,
    event_stream,
    get_source_effective_weight,
    is_balanced,
    score_cluster,
    score_cluster_for_homepage,
    set_cache,
)

from .common import _error_json, _news_row_limit, cleanAndDecode
from .security import validate_cluster_id

log = logging.getLogger("presek")
router = APIRouter()


class ArticleResponse(BaseModel):
    id: str
    title: str
    link: str
    source: str
    created_at: str
    category: Optional[str] = None
    topic: Optional[str] = None
    image_url: Optional[str] = None


class ClusterResponse(BaseModel):
    cluster_id: str
    title: str
    summary: Optional[str] = None
    articles: List[ArticleResponse]


class NewsResponse(BaseModel):
    status: str
    page: int
    page_size: int
    clusters: List[Any]
    global_clusters: Optional[List[Any]] = None
    entity: Optional[Any] = None


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


def _is_publicly_displayable_article(article):
    # Support both dict and tuple (psycopg Row) formats
    a = dict(article) if not isinstance(article, dict) else article
    if a.get("is_translated"):
        return True
    return is_cyrillic_south_slavic(f"{a.get('title') or ''}. {a.get('description') or ''}")


_PUBLIC_ARTICLE_FIELDS = {
    "id",
    "cluster_id",
    "source",
    "link",
    "title",
    "original_title",
    "description",
    "summary",
    "full_content",
    "category",
    "subcategory",
    "topic",
    "country",
    "created_at",
    "ingested_at",
    "image_url",
    "image_caption",
    "clicks",
    "original_description",
    "is_translated",
    "is_fact_check",
    "is_redundant",
    "reading_time",
    "entity_names",
    "source_signal",
    "match_score",
    "rank",
    "hybrid_score",
    "is_global",
    "coverage_balance",
}

_ARTICLE_LIST_COLUMNS = (
    "id, cluster_id, source, link, title, original_title, description, summary, "
    "category, subcategory, topic, country, created_at, ingested_at, image_url, "
    "image_caption, clicks, original_description, is_translated, is_fact_check, "
    "is_redundant, reading_time, entity_names, source_signal, is_global, coverage_balance"
)


# Time budget for the semantic half of search; the text-search fallback needs a fraction of it.
_SEARCH_SEMANTIC_TIMEOUT_MS = int(os.environ.get("SEARCH_SEMANTIC_TIMEOUT_MS", "4000"))


def _public_article_payload(article, lang=DEFAULT_LANG, include_full_content: bool = False):
    from core.language import transliterate_cyr_to_lat, transliterate_lat_to_cyr
    from nlp.categories import normalize_headline

    res = {}
    for key, value in article.items():
        if key not in _PUBLIC_ARTICLE_FIELDS:
            continue
        if key == "full_content" and not include_full_content:
            continue
        if key == "title":
            val = normalize_headline(value)
            if lang == "sr":
                val = transliterate_cyr_to_lat(val)
            elif lang == "mk":
                val = transliterate_lat_to_cyr(val)
            res[key] = val
        elif key == "description" and value:
            from nlp.utils import extract_clean_summary_text

            val = extract_clean_summary_text(str(value))
            if lang == "sr":
                val = transliterate_cyr_to_lat(val)
            elif lang == "mk":
                val = transliterate_lat_to_cyr(val)
            if len(val) > 400:
                res[key] = val[:397] + "..."
            else:
                res[key] = val
        elif key == "summary" and value:
            from nlp.utils import extract_clean_summary_text

            val = extract_clean_summary_text(str(value))
            if lang == "sr":
                val = transliterate_cyr_to_lat(val)
            elif lang == "mk":
                val = transliterate_lat_to_cyr(val)
            if len(val) > 500:
                res[key] = val[:497] + "..."
            else:
                res[key] = val
        elif key == "created_at" and value:
            if isinstance(value, (datetime.datetime, datetime.date)):
                # If it's a naive datetime, assume UTC and append Z
                if isinstance(value, datetime.datetime) and value.tzinfo is None:
                    res[key] = value.isoformat() + "Z"
                else:
                    res[key] = value.isoformat()
            else:
                res[key] = str(value) + ("Z" if "Z" not in str(value) and "T" in str(value) else "")
        else:
            res[key] = value

    # Check if the article is from a global category
    res["is_global"] = article.get("category") in ("Amerika", "Evropa", "Germanija")
    return res


def _parse_maybe_json(val):
    if not val:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return None


def _as_list(val):
    parsed = _parse_maybe_json(val)
    return parsed if isinstance(parsed, list) else []


def _title_looks_like_feature(title):
    clean = str(title or "").strip()
    if not clean:
        return True
    if len(clean) > 180:
        return True
    if "?" in clean:
        return True
    return any(pattern.search(clean) for pattern in _FEATURE_PATTERNS)


def _compute_editorial_signals(arts, cluster_score, homepage_score):
    ranked = list(arts or [])
    if not ranked:
        return {
            "source_count": 0,
            "importance_score": 0.0,
            "freshness_score": 0.0,
            "development_score": 0.0,
            "trust_score": 0.0,
            "novelty_score": 0.0,
            "story_state": "stale",
            "live_now_fit": False,
            "latest_wire_fit": False,
            "live_now_score": 0.0,
            "latest_wire_score": 0.0,
        }

    main = ranked[0]
    unique_sources = {str(a.get("source") or "").strip() for a in ranked if str(a.get("source") or "").strip()}
    source_count = len(unique_sources)
    latest_dt = max(
        (_coerce_datetime(a.get("ingested_at") or a.get("created_at")) for a in ranked),
        default=None,
    )
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    hours_since_latest = max(0.0, ((now - latest_dt).total_seconds() / 3600.0)) if latest_dt else 999.0
    recent_cutoff = now - datetime.timedelta(hours=6)
    recent_developments = sum(
        1
        for article in ranked
        if (_coerce_datetime(article.get("ingested_at") or article.get("created_at")) or datetime.datetime.min)
        >= recent_cutoff
    )

    top_weights = [get_source_effective_weight(str(article.get("source") or "")) for article in ranked[:3]]
    avg_top_weight = (sum(top_weights) / len(top_weights)) if top_weights else 0.0
    if hours_since_latest <= 12:
        freshness_base = 10.0 - (hours_since_latest * 0.45)
    elif hours_since_latest <= 36:
        freshness_base = 4.6 - ((hours_since_latest - 12) * 0.11)
    else:
        freshness_base = max(0.0, 1.96 - ((hours_since_latest - 36) * 0.18))
    freshness_score = min(
        10.0,
        max(0.0, freshness_base) + min(1.6, max(0, recent_developments - 1) * 0.45),
    )
    development_score = min(10.0, max(0, source_count - 1) * 1.85 + min(2.0, recent_developments * 0.6))
    trust_score = min(10.0, avg_top_weight * 5.0)
    importance_score = min(10.0, float(homepage_score or 0.0) * 3.0)
    novelty_score = min(
        10.0,
        freshness_score * (1.0 if source_count <= 2 else 0.65) + (1.25 if source_count == 1 else 0.0),
    )

    if hours_since_latest >= 36:
        story_state = "stale"
    elif cluster_score >= BREAKING_SCORE_THRESHOLD:
        story_state = "breaking"
    elif source_count >= 3 and recent_developments >= 2:
        story_state = "developing"
    elif source_count >= 2:
        story_state = "confirmed"
    else:
        story_state = "singleton"

    title = str(main.get("title") or "").strip()
    topic = str(main.get("topic") or "").strip()
    category = str(main.get("category") or "").strip()
    hard_news = topic in _HARD_NEWS_TOPICS or category in _HARD_NEWS_CATEGORIES
    feature_like = _title_looks_like_feature(title)
    soft_topic = topic in _SOFT_EXCLUDE_TOPICS

    live_now_fit = (
        not feature_like
        and not soft_topic
        and hard_news
        and story_state in {"breaking", "developing", "confirmed"}
        and freshness_score >= 2.0
    ) or bool(cluster_score >= BREAKING_SCORE_THRESHOLD)
    latest_wire_fit = (
        not feature_like
        and not soft_topic
        and hard_news
        and story_state in {"singleton", "confirmed", "breaking"}
        and source_count <= 2
        and freshness_score >= 1.0
    )
    live_now_score = max(
        0.0,
        freshness_score
        + development_score
        + (2.5 if story_state == "breaking" else 0.0)
        + (1.2 if topic in _HARD_NEWS_TOPICS else 0.0),
    )
    latest_wire_score = max(
        0.0,
        freshness_score
        + novelty_score
        + (1.0 if source_count <= 1 else 0.0)
        + (1.0 if topic in _HARD_NEWS_TOPICS else 0.0),
    )

    return {
        "source_count": source_count,
        "importance_score": round(importance_score, 3),
        "freshness_score": round(freshness_score, 3),
        "development_score": round(development_score, 3),
        "trust_score": round(trust_score, 3),
        "novelty_score": round(novelty_score, 3),
        "story_state": story_state,
        "live_now_fit": bool(live_now_fit),
        "latest_wire_fit": bool(latest_wire_fit),
        "live_now_score": round(live_now_score, 3),
        "latest_wire_score": round(latest_wire_score, 3),
    }


@router.get("/news", response_model=NewsResponse)
async def get_news(
    q: Optional[str] = None,
    category: Optional[str] = None,
    topic: Optional[str] = None,
    entity: Optional[str] = None,
    subcategory: Optional[str] = None,
    country: Optional[str] = None,
    lang: Optional[str] = "mk",
    sort: str = "recent",
    timespan: Optional[str] = None,  # '24h', '7d', '30d', 'all'
    page: int = 0,
    page_size: int = 24,
):
    try:
        # The public deployment is Macedonian-only. Legacy callers may still
        # send lang=sr, but must not receive the retired Serbian edition.
        lang = "mk"
        return await fetch_news_data(
            q=q,
            category=category,
            topic=topic,
            entity=entity,
            subcategory=subcategory,
            country=country,
            lang=lang,
            sort=sort,
            timespan=timespan,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        log.error(f"News Route Error in Endpoint: {e}", exc_info=True)
        return _error_json("Internal server error", 500)


async def fetch_news_data(
    q: Optional[str] = None,
    category: Optional[str] = None,
    topic: Optional[str] = None,
    entity: Optional[str] = None,
    subcategory: Optional[str] = None,
    country: Optional[str] = None,
    lang: Optional[str] = DEFAULT_LANG,
    sort: str = "recent",
    timespan: Optional[str] = None,  # '24h', '7d', '30d', 'all'
    page: int = 0,
    page_size: int = 24,
):
    cache_key = f"api:news:v2:{q}:{category}:{topic}:{entity}:{subcategory}:{country}:{lang}:{sort}:{timespan}:{page}:{page_size}"
    cached = cached_response(cache_key)
    if cached:
        return cached

    try:
        page = max(0, min(int(page or 0), API_MAX_PAGE))
        page_size = max(1, min(int(page_size or 24), 100))
        row_limit = _news_row_limit(page, page_size)
        if q:
            row_limit = min(row_limit, 500)
            q = q.strip()[:API_MAX_Q_LEN]

        # Map country to MK/RS if not provided but lang is
        if not country and lang:
            country = "MK" if lang == "mk" else "RS"

        entity_info = None
        if q and page == 0:
            # Check if query matches a known entity
            e_row = await db.async_execute_one(
                """
                SELECT name, type, total_mentions, sentiment_score, image_url
                FROM knowledge_entities
                WHERE LOWER(name) = LOWER(%s)
            """,
                (q,),
                read_only=True,
            )
            if e_row:
                entity_info = dict(e_row)

        # Handle legacy or thematic categories requested as 'category'
        # If 'category' is actually a theme (e.g., Politics), move it to 'topic'
        from nlp.categories import THEMATIC_TOPICS

        if category and category in THEMATIC_TOPICS and not topic:
            topic = category
            category = None

        if q:
            from core.embeddings import get_query_embedding_async

            query_vec = await get_query_embedding_async(q)
            sort_by = "recent" if sort == "recent" else "hybrid"
            rows = None
            if query_vec:
                # The semantic half is an enhancement. If it errors or exceeds its time
                # budget (Postgres cancels it), fall back to plain text search instead of
                # failing the whole page; the page itself gives up after 8 seconds.
                try:
                    rows = await db.async_hybrid_search(
                        q,
                        query_vec,
                        limit=row_limit,
                        sort_by=sort_by,
                        timespan=timespan,
                        country=country,
                        timeout_ms=_SEARCH_SEMANTIC_TIMEOUT_MS,
                    )
                except Exception as e:
                    log.warning(f"[search] hybrid search failed ({type(e).__name__}); falling back to text search: {e}")
            if rows is None:
                rows = await db.async_search_articles(q, limit=row_limit, timespan=timespan, country=country)
        elif subcategory:
            query = """
                SELECT cluster_id, MAX(created_at) as last_article
                FROM articles
                WHERE subcategory = %s
            """
            params = [subcategory]
            if country:
                query += " AND country = %s"
                params.append(country)

            query += " GROUP BY cluster_id ORDER BY last_article DESC LIMIT %s"
            params.append(page_size * (page + 1))

            rows = await db.async_execute(query, tuple(params), read_only=True)
            # Fetch the full pool here; python-side grouping/filtering below can
            # drop clusters, and paged_clusters at the end does the actual paging.
            # (Slicing a window here AND paging below would double-page and
            # return empty results for page >= 1.)
            cids = [r["cluster_id"] for r in rows]
            rows = (
                await db.async_execute(
                    f"SELECT {_ARTICLE_LIST_COLUMNS} FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",  # nosec B608 - static column constant with bound params
                    (cids,),
                    read_only=True,
                )
                if cids
                else []
            )
        elif entity:
            # Escape LIKE special characters in entity search
            escaped_entity = entity.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = """
                WITH entity_clusters AS (
                    SELECT ce.cluster_id
                    FROM cluster_entities ce
                    WHERE LOWER(ce.entity_name) = LOWER(%s)
                    UNION
                    SELECT a.cluster_id
                    FROM articles a
                    WHERE a.title ILIKE %s ESCAPE '\\'
                       OR a.summary ILIKE %s ESCAPE '\\'
                       OR a.description ILIKE %s ESCAPE '\\'
                )
                SELECT a.cluster_id, MAX(COALESCE(a.ingested_at, a.created_at)) as last_article
                FROM articles a
                JOIN entity_clusters ec ON ec.cluster_id = a.cluster_id
                WHERE 1=1
            """
            params = [
                entity,
                f"%{escaped_entity}%",
                f"%{escaped_entity}%",
                f"%{escaped_entity}%",
            ]
            if country:
                query += " AND a.country = %s"
                params.append(country)

            query += " GROUP BY a.cluster_id ORDER BY last_article DESC LIMIT %s"
            params.append(page_size * (page + 1))

            rows = await db.async_execute(query, tuple(params), read_only=True)
            # Full pool (see subcategory branch): downstream paged_clusters pages.
            cids = [r["cluster_id"] for r in rows]

            rows = (
                await db.async_execute(
                    f"SELECT {_ARTICLE_LIST_COLUMNS} FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",  # nosec B608 - static column constant with bound params
                    (cids,),
                    read_only=True,
                )
                if cids
                else []
            )
        elif topic:
            query = """
                WITH topic_clusters AS (
                    SELECT m.cluster_id
                    FROM cluster_metadata m
                    WHERE %s = ANY(m.topics)
                    UNION
                    SELECT a.cluster_id
                    FROM articles a
                    WHERE a.topic = %s OR a.category = %s
                )
                SELECT a.cluster_id, MAX(COALESCE(a.ingested_at, a.created_at)) as last_article
                FROM articles a
                JOIN topic_clusters tc ON tc.cluster_id = a.cluster_id
                WHERE 1=1
            """
            params = [topic, topic, topic]
            if country:
                query += " AND a.country = %s"
                params.append(country)

            query += " GROUP BY a.cluster_id ORDER BY last_article DESC LIMIT %s"
            params.append(page_size * (page + 1))

            rows = await db.async_execute(query, tuple(params), read_only=True)
            # Full pool (see subcategory branch): downstream paged_clusters pages.
            cids = [r["cluster_id"] for r in rows]

            rows = (
                await db.async_execute(
                    # Slim list columns only: payloads go through _public_article_payload
                    # (which drops full_content anyway) and synthesis fields come from
                    # the separate summary_map query below — no JOIN needed here.
                    f"SELECT {_ARTICLE_LIST_COLUMNS} FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",  # nosec B608 - static column constant with bound params
                    (cids,),
                    read_only=True,
                )
                if cids
                else []
            )
        elif category:
            query = """
                SELECT a.cluster_id, MAX(COALESCE(a.ingested_at, a.created_at)) AS last_article
                FROM articles a
                WHERE a.category = %s
                  AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '7 days'
            """
            params = [category]
            if country:
                query += " AND a.country = %s"
                params.append(country)

            query += " GROUP BY a.cluster_id ORDER BY last_article DESC LIMIT %s"
            params.append(page_size * (page + 1))

            rows = await db.async_execute(query, tuple(params), read_only=True)
            # Full pool (see subcategory branch): downstream paged_clusters pages.
            cids = [r["cluster_id"] for r in rows]
            rows = (
                await db.async_execute(
                    f"SELECT {_ARTICLE_LIST_COLUMNS} FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",  # nosec B608 - static column constant with bound params
                    (cids,),
                    read_only=True,
                )
                if cids
                else []
            )
        else:
            # Fallback: rank by latest article activity, not cluster_metadata.updated_at
            # (metadata lags when intel-heavy work is deferred during ingestion).
            query = """
                SELECT a.cluster_id, MAX(COALESCE(a.ingested_at, a.created_at)) AS last_article
                FROM articles a
                WHERE COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '7 days'
            """
            params = []
            if country:
                query += " AND a.country = %s"
                params.append(country)

            # Fetch a larger pool of recent candidate clusters (e.g. 500) so python-side
            # ranking boosts (synthesis, source count, etc.) can filter and bubble up the best stories.
            candidate_limit = max(500, page_size * 5)
            query += " GROUP BY a.cluster_id ORDER BY last_article DESC LIMIT %s"
            params.append(candidate_limit)

            rows = await db.async_execute(query, tuple(params), read_only=True)
            # Full pool (see subcategory branch): downstream paged_clusters pages.
            cids = [r["cluster_id"] for r in rows]
            rows = (
                await db.async_execute(
                    f"SELECT {_ARTICLE_LIST_COLUMNS} FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",  # nosec B608 - static column constant with bound params
                    (cids,),
                    read_only=True,
                )
                if cids
                else []
            )

        clusters = defaultdict(list)
        cluster_relevance = {}
        for r in rows:
            if topic and r.get("topic") != topic and r.get("category") != topic:
                continue
            if category and r.get("category") != category:
                continue
            # Filter articles by country to prevent cross-language leakage on language-specific homepages.
            # We check if 'country' is populated in the article to remain compatible with mock articles in tests.
            if country and r.get("country") and r.get("country") != country:
                continue
            r["reading_time"] = calculate_reading_time(r.get("description", ""))
            cid = r["cluster_id"]
            clusters[cid].append(r)
            # Track best relevance score for this cluster if searching
            if q:
                score = float(r.get("match_score", 0)) + float(r.get("rank", 0))
                if cid not in cluster_relevance or score > cluster_relevance[cid]:
                    cluster_relevance[cid] = score

        ranked_clusters = [
            annotate_cluster_articles(arts, prefer_recent=(sort == "recent")) for arts in clusters.values() if arts
        ]
        if sort == "popular":
            ranked_clusters.sort(
                key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts),
                reverse=True,
            )
        elif sort == "recent":
            # Strict chronological sort by the lead article (which is now the newest)
            def get_recent_sort_key(cluster_arts):
                if not cluster_arts:
                    return 0
                lead_art = cluster_arts[0]
                dt = _coerce_datetime(lead_art.get("ingested_at") or lead_art.get("created_at"))
                return dt.timestamp() if dt else 0

            ranked_clusters.sort(key=get_recent_sort_key, reverse=True)
        elif q:
            # Relevance-first for search results
            ranked_clusters.sort(
                key=lambda arts: cluster_relevance.get(arts[0]["cluster_id"], 0),
                reverse=True,
            )
        else:
            candidate_cids = [arts[0]["cluster_id"] for arts in ranked_clusters if arts]
            candidate_synthesis_ids = (
                set(await db.async_get_synthesis_ids(candidate_cids, lang=lang)) if candidate_cids else set()
            )

            def homepage_sort_key(arts):
                if not arts:
                    return 0.0
                cid = arts[0]["cluster_id"]
                score = score_cluster_for_homepage(arts)
                source_count = len({a.get("source") for a in arts if a.get("source")})
                if cid in candidate_synthesis_ids:
                    score *= 1.35
                if source_count >= 3:
                    score *= 1.15
                elif source_count >= 2:
                    score *= 1.08
                return score

            ranked_clusters.sort(key=homepage_sort_key, reverse=True)

        start = page * page_size
        paged_clusters = ranked_clusters[start : start + page_size]
        cid_list = [c[0]["cluster_id"] for c in paged_clusters]

        # --- NEW: Fetch Global Clusters (America & Europe) for homepage highlights ---
        global_clusters_raw = []
        if not q and not category and not topic and not entity and page == 0:
            g_query = f"""
                SELECT {_ARTICLE_LIST_COLUMNS} FROM articles
                WHERE category IN ('Amerika', 'Evropa')
                  AND created_at >= NOW() - INTERVAL '48 hours'
            """  # nosec B608 - static column constant with bound params
            g_params = []
            if country:
                g_query += " AND country = %s"
                g_params.append(country)
            g_query += " ORDER BY created_at DESC LIMIT 100"
            g_rows = await db.async_execute(g_query, tuple(g_params), read_only=True)
            if g_rows:
                g_grouped = defaultdict(list)
                for r in g_rows:
                    g_grouped[r["cluster_id"]].append(r)
                g_ranked = [annotate_cluster_articles(arts) for arts in g_grouped.values()]
                g_cids = [arts[0]["cluster_id"] for arts in g_ranked if arts]
                g_synthesis_ids = set(await db.async_get_synthesis_ids(g_cids, lang=lang)) if g_cids else set()

                def global_sort_key(arts):
                    if not arts:
                        return 0.0
                    cid = arts[0]["cluster_id"]
                    score = score_cluster_for_homepage(arts)
                    if cid in g_synthesis_ids:
                        score *= 1.25
                    return score

                g_ranked.sort(key=global_sort_key, reverse=True)
                global_clusters_raw = g_ranked[:6]  # Top 6 global stories

        all_cids = cid_list + [c[0]["cluster_id"] for c in global_clusters_raw]
        meta_rows = (
            await db.async_execute(
                "SELECT cluster_id, representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = ANY(%s)",
                (all_cids,),
                read_only=True,
            )
            if all_cids
            else []
        )
        meta_map = {r["cluster_id"]: r for r in meta_rows}
        synthesis_ids = set(await db.async_get_synthesis_ids(all_cids, lang=lang)) if all_cids else set()
        summary_rows = (
            await db.async_execute(
                """
            SELECT cluster_id, synthetic_headline, synthetic_standfirst, key_facts,
                   analyst_entities, pulse_score, pluralism_score, narrative_diversity,
                   created_at, generation_provider, generation_model, quality_score, fallback_reason
            FROM cluster_summaries
            WHERE cluster_id = ANY(%s) AND lang = %s
            """,
                (all_cids, lang),
                read_only=True,
            )
            if all_cids
            else []
        )
        summary_map = {r["cluster_id"]: r for r in summary_rows}

        def _format_cluster(arts):
            main = arts[0]
            cid = main["cluster_id"]
            s = score_cluster(arts)
            homepage_score = score_cluster_for_homepage(arts)
            if cid in synthesis_ids:
                homepage_score *= 1.25
            editorial = _compute_editorial_signals(arts, s, homepage_score)
            meta = meta_map.get(cid, {})
            summary = summary_map.get(cid, {})
            synthesis_freshness = assess_cluster_synthesis_freshness(arts, summary.get("created_at"))
            synthesis_meta = build_synthesis_meta(summary, lang=lang)
            return {
                "cluster_id": cid,
                "articles": [_public_article_payload(article, lang=lang) for article in arts],
                "representative_image": meta.get("representative_image"),
                "dominant_color": meta.get("dominant_color"),
                "synthetic_headline": summary.get("synthetic_headline"),
                "synthetic_standfirst": summary.get("synthetic_standfirst"),
                "key_facts": _as_list(summary.get("key_facts")),
                "analyst_entities": _as_list(summary.get("analyst_entities")),
                "pulse_score": summary.get("pulse_score"),
                "pluralism_score": summary.get("pluralism_score"),
                "narrative_diversity": _parse_maybe_json(summary.get("narrative_diversity")),
                "trust_summary": build_trust_summary(
                    sources_count=len({a.get("source") for a in arts if a.get("source")}),
                    pluralism_score=summary.get("pluralism_score"),
                    is_stale=bool(synthesis_freshness.get("is_stale")),
                    is_provisional=synthesis_meta.get("is_provisional"),
                    needs_upgrade=synthesis_meta.get("needs_upgrade"),
                    lang=lang,
                ),
                "synthesis_updated_at": synthesis_freshness.get("synthesis_updated_at"),
                "synthesis_freshness": synthesis_freshness,
                "synthesis_meta": synthesis_meta,
                "reading_time": main.get("reading_time", 1),
                "score": round(s, 3),
                "homepage_score": round(homepage_score, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_fact_check": any(a.get("is_fact_check") for a in arts),
                "has_balanced": is_balanced(arts),
                "entities": [transliterate_cyr_to_lat(e) for e in main.get("entity_names", [])]
                if lang == "sr"
                else (
                    [transliterate_lat_to_cyr(e) for e in main.get("entity_names", [])]
                    if lang == "mk"
                    else main.get("entity_names", [])
                ),
                **editorial,
            }

        result = [_format_cluster(arts) for arts in paged_clusters]
        global_result = [_format_cluster(arts) for arts in global_clusters_raw]

        final_response = {
            "status": "success",
            "clusters": result,
            "global_clusters": global_result,
            "page": page,
            "page_size": page_size,
            "has_more": len(ranked_clusters) > start + page_size,
            "entity": entity_info,
        }
        set_cache(cache_key, final_response, ttl=180)
        return final_response
    except Exception as e:
        log.error(f"News Route Error: {e}", exc_info=True)
        raise e


@router.get("/search/semantic")
async def semantic_search(
    q: str = Query(..., min_length=3, max_length=API_MAX_Q_LEN),
    limit: int = Query(24, ge=1, le=50),
    lang: str = DEFAULT_LANG,
):
    """
    Explicit Semantic Search endpoint.
    Uses MiniLM embeddings to find relevant clusters across languages.
    """
    cache_key = f"api:search:semantic:{q}:{limit}:{lang}"
    cached = cached_response(cache_key)
    if cached:
        return cached

    try:
        from core.embeddings import get_query_embedding_async

        query_vec = await get_query_embedding_async(q)
        if not query_vec:
            detail = (
                "Неуспешно генерирање вектори за пребарување"
                if lang == "sr"
                else "Неуспешно генерирање на вектор за пребарување"
            )
            raise HTTPException(status_code=500, detail=detail)

        # Fetch articles using vector distance
        rows = await db.async_search_semantic(query_vec, limit=limit)

        # Group by cluster ID
        clusters = defaultdict(list)
        for r in rows:
            r["reading_time"] = calculate_reading_time(r.get("description", ""))
            cid = r["cluster_id"]
            clusters[cid].append(r)

        # Process and sort clusters by their best similarity score
        processed = [annotate_cluster_articles(arts) for arts in clusters.values()]
        processed.sort(key=lambda arts: arts[0].get("similarity", 0), reverse=True)

        cid_list = list(clusters.keys())
        synthesis_ids = set(await db.async_get_synthesis_ids(cid_list)) if cid_list else set()

        result = []
        for arts in processed:
            main = arts[0]
            cid = main["cluster_id"]
            result.append(
                {
                    "cluster_id": cid,
                    "articles": [_public_article_payload(article, lang=lang) for article in arts],
                    "similarity": round(float(main.get("similarity", 0)), 4),
                    "reading_time": main.get("reading_time", 1),
                    "score": round(score_cluster(arts), 3),
                    "has_synthesis": cid in synthesis_ids,
                    "entities": main.get("entity_names", []),
                }
            )

        final_response = {"status": "success", "results": result}
        set_cache(cache_key, final_response, ttl=300)
        return final_response
    except Exception as e:
        log.error(f"Semantic Search Route Error: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        return _error_json("Internal server error", 500)


def _looks_like_leaked_json_fragment(text: str) -> bool:
    from nlp.utils import looks_like_leaked_json_fragment

    return looks_like_leaked_json_fragment(text)


def _clean_leaked_json_string(text: str) -> dict:
    data = {}
    if not text:
        return data

    clean = text.strip()
    lines = []
    for line in clean.splitlines():
        line_s = line.strip()
        if line_s.startswith("•"):
            line_s = line_s[1:].strip()
        lines.append(line_s)
    clean_lines = "\n".join(lines).strip()

    try:
        parsed = json.loads(clean_lines)
        if isinstance(parsed, dict):
            for k in ["synthetic_headline", "synthetic_standfirst", "summary", "generated_article", "key_facts"]:
                if k in parsed:
                    data[k] = parsed[k]
    except Exception:
        # Fall back to regex extraction for truncated/broken JSON
        headline_match = re.search(r'"synthetic_headline"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if headline_match:
            try:
                data["synthetic_headline"] = (
                    headline_match.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
                )
            except Exception:
                data["synthetic_headline"] = headline_match.group(1)

        standfirst_match = re.search(r'"synthetic_standfirst"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if standfirst_match:
            try:
                data["synthetic_standfirst"] = (
                    standfirst_match.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
                )
            except Exception:
                data["synthetic_standfirst"] = standfirst_match.group(1)

        article_match = re.search(r'"generated_article"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if article_match:
            try:
                data["generated_article"] = (
                    article_match.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
                )
            except Exception:
                data["generated_article"] = article_match.group(1)

        summary_match = re.search(r'"summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_lines)
        if summary_match:
            try:
                data["summary"] = summary_match.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
            except Exception:
                data["summary"] = summary_match.group(1)
        else:
            truncated_summary = re.search(r'"summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)', clean_lines)
            if truncated_summary:
                try:
                    data["summary"] = (
                        truncated_summary.group(1).encode("utf-8").decode("unicode-escape", errors="ignore")
                    )
                except Exception:
                    data["summary"] = truncated_summary.group(1)

        summary_array_match = re.search(r'"summary"\s*:\s*\[(.*?)\]', clean_lines, re.DOTALL)
        if summary_array_match:
            array_content = summary_array_match.group(1)
            bullet_matches = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', array_content)
            bullets = []
            for b in bullet_matches:
                try:
                    bullets.append(b.encode("utf-8").decode("unicode-escape", errors="ignore"))
                except Exception:
                    bullets.append(b)
            if bullets:
                data["summary"] = bullets

    for k in data:
        if isinstance(data[k], str):
            data[k] = data[k].replace('\\"', '"').replace("\\n", "\n").strip()
        elif isinstance(data[k], list):
            data[k] = [str(item).replace('\\"', '"').replace("\\n", "\n").strip() for item in data[k]]

    return data


def _maybe_enqueue_synthesis_upgrade(cluster_id: str, s_row: dict | None) -> None:
    """Queue a full-quality re-synthesis when readers hit provisional or fallback content."""
    if not s_row or not synthesis_needs_upgrade(
        s_row.get("fallback_reason"),
        s_row.get("generation_provider"),
    ):
        return

    try:
        from core.celery_app import celery_app
        from tasks.utils import acquire_task_lock

        lock_key = f"lock:jit_synthesis_upgrade:{cluster_id}"
        if not acquire_task_lock(lock_key, 1800):
            return

        celery_app.send_task(
            "tasks.intelligence.synthesize_cluster_task",
            args=[cluster_id, None],
            kwargs={"fast_mode": False},
            countdown=10,
            queue="synthesis",
        )
        log.info("[cluster] JIT synthesis upgrade enqueued for %s", cluster_id)
    except Exception as e:
        log.warning("[cluster] JIT synthesis upgrade enqueue failed for %s: %s", cluster_id, e)


def _maybe_enqueue_missing_synthesis(cluster_id: str, freshness: dict, unique_sources: int) -> None:
    """Queue synthesis once per cluster when readers hit a page with no summary yet."""
    reasons = freshness.get("reasons") or []
    if "missing_synthesis" not in reasons:
        return

    from core.config import AUTO_SUMMARIZE_MIN_SRC

    if unique_sources < AUTO_SUMMARIZE_MIN_SRC:
        return

    try:
        from core.celery_app import celery_app
        from tasks.utils import acquire_task_lock

        lock_key = f"lock:jit_synthesis:{cluster_id}"
        if not acquire_task_lock(lock_key, 900):
            return

        celery_app.send_task(
            "tasks.summarization.build_extractive_clusters_task",
            kwargs={"cluster_ids": [cluster_id]},
            countdown=5,
        )
        log.info("[cluster] JIT synthesis enqueued for %s (%s sources)", cluster_id, unique_sources)
    except Exception as e:
        log.warning("[cluster] JIT synthesis enqueue failed for %s: %s", cluster_id, e)


def _maybe_enqueue_missing_synthesis_from_cache(cluster_id: str, cached: dict) -> None:
    try:
        data = cached.get("data") or {}
        freshness = data.get("synthesis_freshness") or {}
        sources = {article.get("source") for article in (data.get("articles") or []) if article.get("source")}
        _maybe_enqueue_missing_synthesis(cluster_id, freshness, len(sources))
        synthesis_meta = data.get("synthesis_meta") or {}
        if synthesis_meta.get("needs_upgrade"):
            _maybe_enqueue_synthesis_upgrade(
                cluster_id,
                {
                    "fallback_reason": synthesis_meta.get("fallback_reason"),
                    "generation_provider": synthesis_meta.get("generation_provider"),
                },
            )
    except Exception as e:
        log.debug("[cluster] JIT synthesis cache hook failed for %s: %s", cluster_id, e)


@router.get("/entity-graph/{entity_name}")
async def get_entity_graph(entity_name: str, lang: Optional[str] = "mk"):
    """Entity context card: bio, importance, recency, mentions and relations.

    Backed by entity_knowledge, knowledge_entities, cluster_entities and
    knowledge_relationships. Returns {status, data} as the frontend expects.
    """
    name = cleanAndDecode(entity_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="entity name required")

    cache_key = f"api:entity-graph:v1:{name.lower()}:{lang}"
    cached = cached_response(cache_key, ttl=300)
    if cached:
        return cached

    try:
        ent = await db.async_execute_one(
            "SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score "
            "FROM knowledge_entities WHERE LOWER(name) = LOWER(%s)",
            (name,),
        )
        mentions = await db.async_execute_one(
            "SELECT COUNT(DISTINCT cluster_id) AS n FROM cluster_entities WHERE LOWER(entity_name) = LOWER(%s)",
            (name,),
        )
        rels = await db.async_execute(
            """
            SELECT entity_b AS related, weight FROM knowledge_relationships
            WHERE LOWER(entity_a) = LOWER(%s)
            UNION
            SELECT entity_a AS related, weight FROM knowledge_relationships
            WHERE LOWER(entity_b) = LOWER(%s)
            ORDER BY weight DESC
            LIMIT 8
            """,
            (name, name),
        )

        cluster_count = (mentions or {}).get("n", 0)
        if not ent and not cluster_count:
            result = {"status": "not_found", "data": None}
            set_cache(cache_key, result, ttl=120)
            return result

        mentions_total = (ent or {}).get("total_mentions") or cluster_count or 1
        # Lightweight extractive bio: how often and where the entity appears.
        etype = (ent or {}).get("type") or "MISC"
        bio = f"{name} се појавува во {cluster_count} кластери ({mentions_total} споменувања)."
        data = {
            "name": (ent or {}).get("name") or name,
            "bio_summary": bio,
            "summary": bio,
            "importance_score": mentions_total,
            "category": etype,
            "type": etype,
            "last_seen": (ent or {}).get("last_seen"),
            "first_seen": (ent or {}).get("first_seen"),
            "total_mentions": mentions_total,
            "cluster_count": cluster_count,
            "sentiment_score": (ent or {}).get("sentiment_score"),
            "related": [
                {"name": r.get("related"), "weight": r.get("weight")} for r in (rels or []) if r.get("related")
            ],
        }
        result = {"status": "success", "data": data}
        set_cache(cache_key, result, ttl=300)
        return result
    except Exception as e:
        log.debug("[entity-graph] lookup failed for %s: %s", name, e)
        return {"status": "error", "data": None}


@router.get("/article/{article_id}")
async def get_article_detail(article_id: int, lang: Optional[str] = DEFAULT_LANG):
    """Full original text for a single article, with source attribution.

    The body is only returned when the source allows full-text display
    (``sources.full_text_allowed``); otherwise the client falls back to a link.
    """
    lang = validate_language_code(lang, allowed_languages=["sr", "mk"])
    cache_key = f"api:article:detail:v1:{article_id}:{lang}"
    cached = cached_response(cache_key, ttl=3600)
    if cached:
        if isinstance(cached, dict) and cached.get("__missing"):
            # Negative cache: known-missing/purged article ID (crawler sweep).
            # Short TTL so newly-ingested IDs recover fast.
            raise HTTPException(status_code=404, detail="tekstot ne e najden")
        return cached

    try:
        row = await db.async_execute_one(
            f"SELECT {_ARTICLE_LIST_COLUMNS}, full_content FROM articles WHERE id = %s",  # nosec B608 - static column constant with bound params
            (article_id,),
            read_only=True,
        )
    except Exception as e:
        log.debug("[article] lookup failed for %s: %s", article_id, e)
        row = None

    if not row or not _is_publicly_displayable_article(row):
        set_cache(cache_key, {"__missing": True}, ttl=120)
        raise HTTPException(status_code=404, detail="tekstot ne e najden")

    allowed = True
    attribution_name = None
    try:
        srow = await db.async_execute_one(
            "SELECT full_text_allowed, attribution_name FROM sources WHERE name = %s",
            (row.get("source"),),
            read_only=True,
        )
        if srow:
            allowed = bool(srow.get("full_text_allowed", True))
            attribution_name = srow.get("attribution_name")
    except Exception as e:
        log.debug("[article] source flag lookup failed for %s: %s", article_id, e)

    payload = _public_article_payload(row, lang=lang, include_full_content=allowed)
    payload["full_text_allowed"] = allowed
    payload["attribution"] = attribution_name or row.get("source")
    payload["original_url"] = row.get("link")
    payload["published_at"] = row.get("created_at")

    set_cache(cache_key, payload, ttl=3600)
    return payload


@router.get("/cluster/{cluster_id}")
async def get_cluster_detail(cluster_id: str, lang: Optional[str] = DEFAULT_LANG):
    # Validate cluster_id using comprehensive validation
    validate_cluster_id_input(cluster_id)
    # Validate language code
    lang = validate_language_code(lang, allowed_languages=["sr", "mk"])
    cache_key = f"api:cluster:detail:v3:{cluster_id}:{lang}"
    cached = cached_response(cache_key, ttl=3600)
    if cached:
        if isinstance(cached, dict) and cached.get("__missing"):
            # Negative cache: known-missing cluster (crawler sweep of
            # purged/merged IDs). Short TTL so newly-ingested IDs recover fast.
            raise HTTPException(status_code=404, detail="klaster nije pronadjen")
        _maybe_enqueue_missing_synthesis_from_cache(cluster_id, cached)
        return cached

    def _remember_missing():
        try:
            set_cache(cache_key, {"__missing": True}, ttl=120)
        except Exception:
            log.debug("[cluster] negative cache write failed for %s", cluster_id)

    try:
        # Map language to country for article filtering
        country_filter = "MK" if lang == "mk" else "RS"
        rows = await db.async_execute(
            f"SELECT {_ARTICLE_LIST_COLUMNS} FROM articles WHERE cluster_id = %s AND country = %s ORDER BY created_at DESC",  # nosec B608 - static column constant with bound params
            (cluster_id, country_filter),
            read_only=True,
        )
        if not rows:
            _remember_missing()
            raise HTTPException(status_code=404, detail="klaster nije pronadjen")
        rows = [row for row in rows if _is_publicly_displayable_article(row)]
        if not rows:
            _remember_missing()
            raise HTTPException(status_code=404, detail="klaster nije pronadjen")
        articles = annotate_cluster_articles(rows, prefer_recent=True)
        for a in articles:
            a["reading_time"] = calculate_reading_time(a.get("description", ""))
        public_articles = [
            _public_article_payload(article, lang=lang, include_full_content=False) for article in articles
        ]

        log.debug(f"[debug] Fetching summary for cluster_id: '{cluster_id}' ({lang})")
        s_row = await db.async_execute_one(
            """
            SELECT summary, generated_article, synthetic_headline, synthetic_standfirst,
                   perspectives, created_at, sentiment, tone_analysis, verification_report,
                   citation_sources, key_facts, analyst_entities, pulse_score,
                   pluralism_score, narrative_diversity, storyline_narrative,
                   generation_provider, generation_model, quality_score, fallback_reason
            FROM cluster_summaries
            WHERE cluster_id = %s AND lang = %s
            """,
            (cluster_id, lang),
            read_only=True,
        )

        # Fallback to Serbian if the requested language summary is missing
        if not s_row and lang != "sr":
            log.info(f"Summary for {cluster_id} not found in {lang}, falling back to sr")
            s_row = await db.async_execute_one(
                """
                SELECT summary, generated_article, synthetic_headline, synthetic_standfirst,
                       perspectives, created_at, sentiment, tone_analysis, verification_report,
                       citation_sources, key_facts, analyst_entities, pulse_score,
                       pluralism_score, narrative_diversity, storyline_narrative,
                       generation_provider, generation_model, quality_score, fallback_reason
                FROM cluster_summaries
                WHERE cluster_id = %s AND lang = 'sr'
                """,
                (cluster_id,),
                read_only=True,
            )

        log.debug(f"[debug] s_row found: {bool(s_row)}")

        # Synthesis and AI Content Mapping
        summary_text = s_row.get("summary") if s_row else ""
        generated_article = s_row.get("generated_article") if s_row else None
        synthetic_headline = s_row.get("synthetic_headline") if s_row else None
        synthetic_standfirst = s_row.get("synthetic_standfirst") if s_row else None

        # Self-healing for raw leaked JSON fragments in summary or generated_article
        leaked_data = {}
        if summary_text and _looks_like_leaked_json_fragment(summary_text):
            leaked_data = _clean_leaked_json_string(summary_text)
        elif generated_article and _looks_like_leaked_json_fragment(generated_article):
            leaked_data = _clean_leaked_json_string(generated_article)

        if leaked_data:
            if "synthetic_headline" in leaked_data and leaked_data["synthetic_headline"] and not synthetic_headline:
                synthetic_headline = leaked_data["synthetic_headline"]
            if (
                "synthetic_standfirst" in leaked_data
                and leaked_data["synthetic_standfirst"]
                and not synthetic_standfirst
            ):
                synthetic_standfirst = leaked_data["synthetic_standfirst"]
            if "generated_article" in leaked_data and leaked_data["generated_article"]:
                generated_article = leaked_data["generated_article"]
            if "summary" in leaked_data:
                if isinstance(leaked_data["summary"], list):
                    summary_text = "\n".join(f"• {b}" for b in leaked_data["summary"])
                else:
                    summary_text = str(leaked_data["summary"])

        # Build synthesis response (string for backward compatibility with frontend split())
        synthesis = summary_text or ""
        has_synthesis = bool(s_row and s_row.get("summary"))
        synthesis_meta = build_synthesis_meta(s_row, lang=lang)

        # Extra metadata from summary row
        key_facts = _as_list(s_row.get("key_facts")) if s_row else []
        analyst_entities = _as_list(s_row.get("analyst_entities")) if s_row else []
        perspectives = _parse_maybe_json(s_row.get("perspectives")) if s_row else []
        verification_report = _parse_maybe_json(s_row.get("verification_report")) if s_row else None
        sentiment = _parse_maybe_json(s_row.get("sentiment")) if s_row else None
        tone_analysis = _parse_maybe_json(s_row.get("tone_analysis")) if s_row else None
        citation_sources = _parse_maybe_json(s_row.get("citation_sources")) if s_row else []

        freshness = assess_cluster_synthesis_freshness(articles, (s_row or {}).get("created_at"))
        unique_sources_for_jit = len({a.get("source") for a in articles if a.get("source")})
        _maybe_enqueue_missing_synthesis(cluster_id, freshness, unique_sources_for_jit)
        _maybe_enqueue_synthesis_upgrade(cluster_id, s_row)

        cluster_meta = await db.async_execute_one(
            "SELECT tags, topics, representative_image, dominant_color, centroid FROM cluster_metadata WHERE cluster_id = %s",
            (cluster_id,),
            read_only=True,
        )

        tags = filter_cluster_tags((cluster_meta.get("tags") or []) if cluster_meta else [])
        topics = (cluster_meta.get("topics") or []) if cluster_meta else []
        rep_image = cluster_meta.get("representative_image") if cluster_meta else None
        dominant_color = cluster_meta.get("dominant_color") if cluster_meta else None
        current_tags = {str(tag or "").strip() for tag in tags if str(tag or "").strip()}
        current_topics = {str(topic or "").strip() for topic in topics if str(topic or "").strip()}

        # Just-in-time extraction if missing
        if rep_image and not dominant_color:
            from utils import get_dominant_color

            dominant_color = await get_dominant_color(rep_image)
            if dominant_color:
                await db.async_execute(
                    "UPDATE cluster_metadata SET dominant_color = %s WHERE cluster_id = %s",
                    (dominant_color, cluster_id),
                    fetch=False,
                )

        related = []
        if cluster_meta and cluster_meta.get("centroid"):
            centroid_vec = (
                json.loads(cluster_meta["centroid"])
                if isinstance(cluster_meta["centroid"], str)
                else list(cluster_meta["centroid"])
            )
            vec_str = "[" + ",".join(map(str, centroid_vec)) + "]"

            # Use pgvector directly on cluster_metadata for lightning-fast related cluster discovery
            # Filter by country to ensure related content matches the current market
            related_query = """
                SELECT m.cluster_id, (1 - (m.centroid <=> %s::vector)) as similarity
                FROM cluster_metadata m
                JOIN articles a ON a.cluster_id = m.cluster_id
                WHERE m.cluster_id != %s
                  AND m.centroid IS NOT NULL
                  AND m.updated_at >= NOW() - INTERVAL '14 days'
                  AND a.country = %s
                GROUP BY m.cluster_id, m.centroid
                ORDER BY m.centroid <=> %s::vector
                LIMIT 15
            """
            related_results = await db.async_execute(
                related_query, (vec_str, cluster_id, country_filter, vec_str), read_only=True
            )

            related_cids = []
            for r in related_results:
                similarity = float(r.get("similarity", 0))
                # We can be slightly more lenient here since the centroid is a stable representation
                if similarity >= local_similarity(0.65):
                    related_cids.append(r["cluster_id"])

            if related_cids:
                r_rows = await db.async_execute(
                    "SELECT a.*, COALESCE(m.tags, '{}') as cluster_tags FROM articles a LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE a.cluster_id = ANY(%s)",
                    (related_cids,),
                    read_only=True,
                )
                synthesis_ids = set(await db.async_get_synthesis_ids(related_cids)) if related_cids else set()
                scored_related = build_read_next_clusters(
                    cluster_id,
                    articles,
                    tags,
                    r_rows,
                    limit=5,
                )
                for item in scored_related:
                    shared_tags = item.get("shared_tags", [])
                    shared_topics = item.get("shared_topics", [])
                    shared_entities = item.get("shared_entities", [])
                    related.append(
                        {
                            "cluster_id": item["cluster_id"],
                            "title": item["title"],
                            "image_url": item.get("image_url"),
                            "tags": shared_tags,
                            "relationship_label": item.get("relationship_label") or "Srodna tema",
                            "relationship_note": item.get("relationship_note"),
                            "shared_tags": shared_tags,
                            "shared_topics": shared_topics,
                            "shared_entities": shared_entities,
                            "source": item.get("source"),
                            "created_at": item.get("created_at"),
                            "has_synthesis": item["cluster_id"] in synthesis_ids,
                        }
                    )

        if not related:
            fallback_topics = sorted(
                current_topics
                | {
                    str(article.get("topic") or "").strip()
                    for article in articles
                    if str(article.get("topic") or "").strip()
                }
            )
            fallback_categories = sorted(
                {
                    str(article.get("category") or "").strip()
                    for article in articles
                    if str(article.get("category") or "").strip()
                }
            )
            match_clauses = ["a.country = %s"]
            fallback_params = [cluster_id, country_filter]
            if fallback_topics:
                match_clauses.append(
                    "(a.topic = ANY(%s) OR EXISTS (SELECT 1 FROM unnest(COALESCE(m.topics, '{}')) AS topic WHERE topic = ANY(%s)))"
                )
                fallback_params.extend([fallback_topics, fallback_topics])
            if fallback_categories:
                match_clauses.append("a.category = ANY(%s)")
                fallback_params.append(fallback_categories)
            if current_tags:
                match_clauses.append("EXISTS (SELECT 1 FROM unnest(COALESCE(m.tags, '{}')) AS tag WHERE tag = ANY(%s))")
                fallback_params.append(sorted(current_tags))

            if len(match_clauses) > 1:
                fallback_rows = await db.async_execute(
                    f"""
                    SELECT a.*, COALESCE(m.tags, '{{}}') as cluster_tags
                    FROM articles a
                    LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id
                    WHERE a.cluster_id != %s
                      AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '14 days'
                      AND ({" AND ".join(match_clauses[:1])} AND ({" OR ".join(match_clauses[1:])}))
                    ORDER BY COALESCE(a.ingested_at, a.created_at) DESC
                    LIMIT 200
                """,  # nosec B608 - static clause list with bound params
                    tuple(fallback_params),
                    read_only=True,
                )
                scored_related = build_read_next_clusters(
                    cluster_id,
                    articles,
                    tags,
                    fallback_rows,
                    limit=5,
                )
                related_cids = [item["cluster_id"] for item in scored_related]
                synthesis_ids = set(await db.async_get_synthesis_ids(related_cids)) if related_cids else set()
                for item in scored_related:
                    shared_tags = item.get("shared_tags", [])
                    shared_topics = item.get("shared_topics", [])
                    shared_entities = item.get("shared_entities", [])
                    related.append(
                        {
                            "cluster_id": item["cluster_id"],
                            "title": item["title"],
                            "image_url": item.get("image_url"),
                            "tags": shared_tags,
                            "relationship_label": item.get("relationship_label") or "Srodna tema",
                            "relationship_note": item.get("relationship_note"),
                            "shared_tags": shared_tags,
                            "shared_topics": shared_topics,
                            "shared_entities": shared_entities,
                            "source": item.get("source"),
                            "created_at": item.get("created_at"),
                            "has_synthesis": item["cluster_id"] in synthesis_ids,
                        }
                    )

        def get_jaccard_similarity(s1: str, s2: str) -> float:
            words1 = set(re.findall(r"\w+", s1.lower()))
            words2 = set(re.findall(r"\w+", s2.lower()))
            if not words1 or not words2:
                return 0.0
            return len(words1.intersection(words2)) / len(words1.union(words2))

        chrono = sorted(articles, key=lambda x: x["created_at"])
        consolidated_chrono = []
        for a in chrono:
            is_dup = False
            for existing in consolidated_chrono:
                time_diff = abs((a["created_at"] - existing["created_at"]).total_seconds())
                if time_diff < 6 * 3600:
                    sim = get_jaccard_similarity(a.get("title") or "", existing.get("title") or "")
                    if sim > 0.65:
                        is_dup = True
                        if "sources" not in existing:
                            existing["sources"] = [existing["source"]]
                        if a["source"] not in existing["sources"]:
                            existing["sources"].append(a["source"])
                        break
            if not is_dup:
                a["sources"] = [a["source"]]
                consolidated_chrono.append(a)

        timeline = []

        from nlp.local_analyst import LocalAnalyst

        analyst = LocalAnalyst()

        for i, a in enumerate(consolidated_chrono):
            is_major = (a.get("source_signal") or {}).get("trust_level", 0) >= 0.8
            title_text = a.get("title") or ""
            desc_text = a.get("description") or ""

            # 1. Clean Title using Clickbait Scrubber
            clean_title = analyst.get_zero_token_normalized_headline(title_text, lang=lang)

            # 2. Extract clean 1-sentence chronological event summary
            clean_desc = ""
            if desc_text:
                sentences = re.split(r"(?<=[.!?])\s+", desc_text.strip())
                if sentences and len(sentences[0]) > 10:
                    clean_desc = sentences[0]
            if not clean_desc or len(clean_desc) < 15:
                clean_desc = clean_title

            # 3. Dynamic Broadsheet Milestones
            lower_title = title_text.lower()
            lower_desc = desc_text.lower()

            official_keywords = {
                "vlada",
                "sobranie",
                "ministar",
                "mup",
                "policija",
                "skupština",
                "saopštenje",
                "soopstenie",
                "mvr",
                "srbije",
                "makedonije",
            }
            reaction_keywords = {
                "protest",
                "strajk",
                "reaguje",
                "osudili",
                "kritika",
                "reakcija",
                "demant",
                "demantira",
                "odgovori",
                "obtozi",
                "optužio",
            }
            escalation_keywords = {
                "napustio",
                "odbio",
                "sukob",
                "prekinuo",
                "incident",
                "uhapšen",
                "uapsen",
                "pretepan",
                "teško",
                "tesko",
                "kriza",
            }

            if i == 0:
                milestone = "ПОЧЕТОК НА МЕДИУМСКО ИЗВЕСТУВАЊЕ" if lang == "mk" else "POČETAK MEDIJSKOG IZVEŠTAVANJA"
            elif any(k in lower_title or k in lower_desc for k in official_keywords):
                milestone = "ОФИЦИЈАЛНО СООПШТЕНИЕ" if lang == "mk" else "ZVANIČNO SAOPŠTENJE"
            elif any(k in lower_title or k in lower_desc for k in reaction_keywords):
                milestone = "РЕАКЦИЈА" if lang == "mk" else "REAKCIJA"
            elif any(k in lower_title or k in lower_desc for k in escalation_keywords):
                milestone = "ЕСКАЛАЦИЈА" if lang == "mk" else "ESKALACIJA"
            elif i == len(consolidated_chrono) - 1 and len(consolidated_chrono) >= 3:
                milestone = "КОНСЕНЗУС НА МЕДИУМИТЕ" if lang == "mk" else "KONSENZUS MEDIJA"
            else:
                milestone = "хронологија" if lang == "mk" else "hronologija"

            sources_list = a.get("sources", [a["source"]])
            if len(sources_list) > 2:
                formatted_source = f"{sources_list[0]}, {sources_list[1]} + {len(sources_list) - 2}"
            elif len(sources_list) == 2:
                formatted_source = f"{sources_list[0]}, {sources_list[1]}"
            else:
                formatted_source = sources_list[0]

            timeline.append(
                {
                    "article_id": a["id"],
                    "title": clean_title,
                    "source": formatted_source,
                    "created_at": a["created_at"],
                    "is_first": i == 0,
                    "is_major": is_major,
                    "milestone": milestone,
                    "description": clean_desc,
                }
            )

        # Calculate zero-token stance vectors and editorial divergence index
        stance_vectors = {}
        sentiments = []
        from nlp.sentiment import analyze_sentiment_locally

        for a in articles:
            text_context = f"{a.get('title') or ''} {a.get('description') or ''}"
            score = analyze_sentiment_locally(text_context, bypass_llm=True)
            sentiments.append(score)
            src = a.get("source") or "izvor"
            if src not in stance_vectors:
                stance_vectors[src] = []
            stance_vectors[src].append(score)

        # Average sentiment per source
        avg_stance_vectors = {src: round(sum(scores) / len(scores), 2) for src, scores in stance_vectors.items()}

        # Calculate standard deviation/divergence
        if len(sentiments) > 1:
            mean = sum(sentiments) / len(sentiments)
            variance = sum((x - mean) ** 2 for x in sentiments) / len(sentiments)
            editorial_divergence = round(variance**0.5, 2)
        else:
            editorial_divergence = 0.0

        from core.cross_lingual import get_cross_lingual_counterparts

        pluralism_score = s_row.get("pluralism_score") if s_row else None
        pulse_score = s_row.get("pulse_score") if s_row else None
        narrative_diversity = _parse_maybe_json(s_row.get("narrative_diversity")) if s_row else None
        unique_sources = len({a.get("source") for a in articles if a.get("source")})
        has_verification = bool(
            verification_report and (verification_report.get("agreements") or verification_report.get("conflicts"))
        )
        trust_summary = build_trust_summary(
            sources_count=unique_sources,
            pluralism_score=pluralism_score,
            is_stale=bool(freshness.get("is_stale")),
            has_verification=has_verification,
            is_provisional=synthesis_meta.get("is_provisional"),
            needs_upgrade=synthesis_meta.get("needs_upgrade"),
            lang=lang,
        )
        cross_lingual_counterparts = await get_cross_lingual_counterparts(cluster_id, lang)

        response = {
            "status": "success",
            "pipeline": reader_pipeline_status(),
            "data": {
                "cluster_id": cluster_id,
                "articles": public_articles,
                "timeline": timeline,
                "synthesis": synthesis,
                "has_synthesis": has_synthesis,
                "generated_article": generated_article,
                "synthetic_headline": synthetic_headline,
                "synthetic_standfirst": synthetic_standfirst,
                "key_facts": key_facts,
                "analyst_entities": analyst_entities,
                "perspectives": perspectives,
                "verification_report": verification_report,
                "sentiment": sentiment,
                "tone_analysis": tone_analysis,
                "citation_sources": citation_sources,
                "pluralism_score": pluralism_score,
                "pulse_score": pulse_score,
                "narrative_diversity": narrative_diversity,
                "trust_summary": trust_summary,
                "cross_lingual_counterparts": cross_lingual_counterparts,
                "synthesis_updated_at": freshness["synthesis_updated_at"],
                "synthesis_freshness": freshness,
                "synthesis_meta": synthesis_meta,
                "tags": tags,
                "topics": topics,
                "representative_image": rep_image,
                "dominant_color": dominant_color,
                "related": related,
                "total_reading_time": sum(a["reading_time"] for a in articles),
                "stance_vectors": avg_stance_vectors,
                "editorial_divergence": editorial_divergence,
            },
        }

        cache_ttl = (
            120
            if ("missing_synthesis" in (freshness.get("reasons") or []) or synthesis_meta.get("needs_upgrade"))
            else 3600
        )
        set_cache(cache_key, response, ttl=cache_ttl)
        return response

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Cluster Detail Error: {e}", exc_info=True)
        detail = "Unutrašnja serverska greška" if lang == "sr" else "Внатрешна серверска грешка"
        raise HTTPException(status_code=500, detail=detail)


@router.get("/cluster/{cluster_id}/history")
async def get_cluster_history(cluster_id: str, lang: Optional[str] = DEFAULT_LANG):
    """
    Returns the historical versions of a cluster synthesis.
    """
    validate_cluster_id(cluster_id)
    try:
        rows = await db.async_execute(
            """
            SELECT summary, generated_article, synthetic_headline, synthetic_standfirst, perspectives, verification_report, created_at
            FROM cluster_summary_history
            WHERE cluster_id = %s AND lang = %s
            ORDER BY created_at DESC
            LIMIT 20
        """,
            (cluster_id, lang),
            read_only=True,
        )

        def _parse_maybe_json(val):
            if not val:
                return None
            if isinstance(val, (dict, list)):
                return val
            try:
                return json.loads(val)
            except Exception:
                return None

        history = []
        for r in rows:
            history.append(
                {
                    "summary": r["summary"],
                    "generated_article": r["generated_article"],
                    "synthetic_headline": r["synthetic_headline"],
                    "synthetic_standfirst": r["synthetic_standfirst"],
                    "perspectives": _parse_maybe_json(r["perspectives"]),
                    "verification_report": _parse_maybe_json(r["verification_report"]),
                    "created_at": r["created_at"],
                }
            )

        return {"status": "success", "history": history}
    except Exception as e:
        log.error(f"Cluster History Error: {e}", exc_info=True)
        return _error_json("Internal server error", 500)


@router.get("/cluster/{cluster_id}/historical")
async def get_historical_events(cluster_id: str):
    """
    Finds semantically similar clusters from the 60-day archive.
    """
    validate_cluster_id(cluster_id)
    cache_key = f"api:cluster:{cluster_id}:historical:v1"
    cached = cached_response(cache_key)
    if cached:
        return cached

    try:
        # 1. Get average embedding for the target cluster
        vec_rows = await db.async_execute(
            "SELECT embedding FROM articles WHERE cluster_id = %s AND embedding IS NOT NULL",
            (cluster_id,),
            read_only=True,
        )
        if not vec_rows:
            return {"status": "success", "events": []}

        from core.embeddings import average_embeddings

        avg_vec = average_embeddings([r["embedding"] for r in vec_rows])
        if not avg_vec:
            return {"status": "success", "events": []}
        vec_str = "[" + ",".join(map(str, avg_vec)) + "]"

        # 2. Query archive using vector similarity
        # Exclude today's window to find truly historical context
        rows = await db.async_execute(
            """
            WITH archive_pool AS (
                SELECT cluster_id, title, created_at, category,
                       (1 - (embedding <=> %s::vector)) as similarity
                FROM articles
                WHERE cluster_id != %s
                  AND created_at < NOW() - INTERVAL '48 hours'
                  AND embedding IS NOT NULL
            )
            SELECT DISTINCT ON (cluster_id)
                   cluster_id, title, created_at, category, similarity
            FROM archive_pool
            WHERE similarity > %s
            ORDER BY cluster_id, similarity DESC, created_at DESC
            LIMIT 5
        """,
            (vec_str, cluster_id, local_similarity(0.68)),
            read_only=True,
        )

        events = []
        for r in sorted(rows, key=lambda x: x["similarity"], reverse=True):
            events.append(
                {
                    "cluster_id": r["cluster_id"],
                    "title": cleanAndDecode(r["title"]),
                    "created_at": r["created_at"],
                    "category": r["category"],
                    "similarity": round(float(r["similarity"]), 4),
                }
            )

        res = {"status": "success", "events": events}
        set_cache(cache_key, res, ttl=3600)
        return res
    except Exception as e:
        log.error(f"Historical Search Error: {e}", exc_info=True)
        return _error_json("Internal server error", 500)


@router.get("/live")
async def get_live_route(request: Request):
    return StreamingResponse(event_stream("updates", request=request), media_type="text/event-stream")


@router.get("/cluster/{cluster_id}/audio")
async def get_cluster_audio(cluster_id: str, lang: Optional[str] = DEFAULT_LANG):
    """Generates or fetches the cluster synthesis TTS audio and returns its public URL."""
    validate_cluster_id(cluster_id)

    s_row = await db.async_execute_one(
        "SELECT generated_article, summary FROM cluster_summaries WHERE cluster_id = %s AND lang = %s",
        (cluster_id, lang),
    )
    if not s_row and lang != "sr":
        s_row = await db.async_execute_one(
            "SELECT generated_article, summary FROM cluster_summaries WHERE cluster_id = %s AND lang = 'sr'",
            (cluster_id,),
        )

    from core.audio_service import AudioService, select_cluster_audio_text

    content = ""
    if s_row and (s_row.get("generated_article") or s_row.get("summary")):
        content = select_cluster_audio_text(
            s_row.get("generated_article"),
            s_row.get("summary"),
        )
    if not content:
        # No synthesis stored yet: narrate the cluster's latest headlines instead.
        a_rows = (
            await db.async_execute(
                "SELECT title, description FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 5",
                (cluster_id,),
                read_only=True,
            )
            or []
        )
        headlines = [str(r.get("title") or "").strip() for r in a_rows]
        headlines = [h for h in headlines if h]
        if not headlines:
            raise HTTPException(status_code=404, detail="Не е пронајдена синтеза за овој кластер.")
        lead = str((a_rows[0] or {}).get("description") or "").strip()
        narration = "Вести: " + ". ".join(headlines)
        if lead:
            narration += ". " + lead
        content = select_cluster_audio_text(None, narration)
    if not content:
        raise HTTPException(status_code=404, detail="Не е пронајдена синтеза за овој кластер.")
    loop = asyncio.get_running_loop()
    audio_url = await loop.run_in_executor(None, AudioService.generate_cluster_audio, cluster_id, content, lang)

    if not audio_url:
        return soft_error(message="Failed to synthesize cluster audio.")

    return {"status": "success", "audio_url": audio_url}
