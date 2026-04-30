import json
import logging
import re
import datetime

from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from collections import defaultdict
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from database import db_manager as db
from utils import (
    score_cluster, rank_articles_in_cluster, calculate_reading_time,
    cached_response, set_cache, is_balanced, assess_cluster_synthesis_freshness,
    annotate_cluster_articles, score_cluster_for_homepage, build_read_next_clusters,
    event_stream, record_runtime_event, get_source_effective_weight, _coerce_datetime,
)
from ai_engine import PROVIDERS, _call_ai_async, clean_json_response
from config import (
    BREAKING_SCORE_THRESHOLD,
    API_MAX_PAGE,
    API_MAX_Q_LEN,
)
from nlp import (
    filter_cluster_tags,
)
from language import is_cyrillic_south_slavic
from api_helpers import (
    normalize_summary_text, normalize_perspectives, normalize_citation_sources
)
from .common import _source_admin_authorized, _error_json, cleanAndDecode, _news_row_limit

from .security import validate_cluster_id, validate_string_param

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


def _is_publicly_displayable_article(article):
    if article.get("is_translated"):
        return True
    return is_cyrillic_south_slavic(f"{article.get('title') or ''}. {article.get('description') or ''}")

_PUBLIC_ARTICLE_FIELDS = {
    "id",
    "cluster_id",
    "source",
    "link",
    "title",
    "original_title",
    "description",
    "summary",
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
    "coverage_balance"
    }


def _public_article_payload(article):
    from nlp.categories import normalize_headline
    import datetime
    res = {}
    for key, value in article.items():
        if key not in _PUBLIC_ARTICLE_FIELDS:
            continue
        if key == "title":
            res[key] = normalize_headline(value)
        elif key == "description" and value and len(str(value)) > 400:
            res[key] = str(value)[:397] + "..."
        elif key == "summary" and value and len(str(value)) > 500:
            res[key] = str(value)[:497] + "..."
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
    res["is_global"] = article.get("category") in ("Америка", "Германија")
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
    latest_dt = max((_coerce_datetime(a.get("ingested_at") or a.get("created_at")) for a in ranked), default=None)
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    hours_since_latest = max(0.0, ((now - latest_dt).total_seconds() / 3600.0)) if latest_dt else 999.0
    recent_cutoff = now - datetime.timedelta(hours=6)
    recent_developments = sum(
        1
        for article in ranked
        if (_coerce_datetime(article.get("ingested_at") or article.get("created_at")) or datetime.datetime.min) >= recent_cutoff
    )

    top_weights = [get_source_effective_weight(str(article.get("source") or "")) for article in ranked[:3]]
    avg_top_weight = (sum(top_weights) / len(top_weights)) if top_weights else 0.0
    if hours_since_latest <= 12:
        freshness_base = 10.0 - (hours_since_latest * 0.45)
    elif hours_since_latest <= 36:
        freshness_base = 4.6 - ((hours_since_latest - 12) * 0.11)
    else:
        freshness_base = max(0.0, 1.96 - ((hours_since_latest - 36) * 0.18))
    freshness_score = min(10.0, max(0.0, freshness_base) + min(1.6, max(0, recent_developments - 1) * 0.45))
    development_score = min(10.0, max(0, source_count - 1) * 1.85 + min(2.0, recent_developments * 0.6))
    trust_score = min(10.0, avg_top_weight * 5.0)
    importance_score = min(10.0, float(homepage_score or 0.0) * 3.0)
    novelty_score = min(10.0, freshness_score * (1.0 if source_count <= 2 else 0.65) + (1.25 if source_count == 1 else 0.0))

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
    live_now_score = max(0.0, freshness_score + development_score + (2.5 if story_state == "breaking" else 0.0) + (1.2 if topic in _HARD_NEWS_TOPICS else 0.0))
    latest_wire_score = max(0.0, freshness_score + novelty_score + (1.0 if source_count <= 1 else 0.0) + (1.0 if topic in _HARD_NEWS_TOPICS else 0.0))

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
    sort: str = "recent",
    timespan: Optional[str] = None, # '24h', '7d', '30d', 'all'
    page: int = 0,
    page_size: int = 24
):
    cache_key = f"api:news:v2:{q}:{category}:{topic}:{entity}:{subcategory}:{sort}:{timespan}:{page}:{page_size}"
    cached = cached_response(cache_key)
    if cached: return cached

    try:
        page = max(0, min(int(page or 0), API_MAX_PAGE))
        page_size = max(1, min(int(page_size or 24), 50))
        row_limit = _news_row_limit(page, page_size)
        if q: q = q.strip()[:API_MAX_Q_LEN]
        
        entity_info = None
        if q and page == 0:
            # Check if query matches a known entity
            e_row = await db.async_execute_one("""
                SELECT name, type, total_mentions, sentiment_score, image_url 
                FROM knowledge_entities 
                WHERE LOWER(name) = LOWER(%s)
            """, (q,))
            if e_row:
                entity_info = dict(e_row)

        # Handle legacy or thematic categories requested as 'category'
        # If 'category' is actually a theme (e.g., Politics), move it to 'topic'
        from nlp.categories import THEMATIC_TOPICS
        if category and category in THEMATIC_TOPICS and not topic:
            topic = category
            category = None

        if q:
            from embeddings import generate_query_embedding
            query_vec = generate_query_embedding(q)
            sort_by = "recent" if sort == "recent" else "hybrid"
            rows = await db.async_hybrid_search(q, query_vec, limit=row_limit, sort_by=sort_by) if query_vec else await db.async_search_articles(q, limit=row_limit)
        elif subcategory:
            rows = await db.async_execute("""
                SELECT cluster_id, MAX(created_at) as last_article
                FROM articles
                WHERE subcategory = %s
                GROUP BY cluster_id
                ORDER BY last_article DESC LIMIT %s
            """, (subcategory, page_size * (page + 1)))
            cids = [r['cluster_id'] for r in rows[page*page_size:(page+1)*page_size]]
            rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,)) if cids else []
        elif entity:
            rows = await db.async_execute("""
                SELECT cluster_id, updated_at as last_article 
                FROM cluster_metadata m
                JOIN cluster_entities ce USING (cluster_id)
                WHERE ce.entity_name = %s 
                ORDER BY updated_at DESC LIMIT %s
            """, (entity, page_size * (page + 1)))
            cids = [r['cluster_id'] for r in rows[page*page_size:(page+1)*page_size]]
            
            # Fallback: if no clusters found for this entity name, try searching for it
            if not cids and page == 0:
                rows = await db.async_execute("""
                    SELECT cluster_id, MAX(created_at) as last_article
                    FROM articles
                    WHERE title ILIKE %s OR summary ILIKE %s OR description ILIKE %s
                    GROUP BY cluster_id
                    ORDER BY last_article DESC LIMIT %s
                """, (f"%{entity}%", f"%{entity}%", f"%{entity}%", page_size))
                cids = [r['cluster_id'] for r in rows]

            rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,)) if cids else []
        elif topic:
            rows = await db.async_execute("""
                SELECT cluster_id, updated_at as last_article 
                FROM cluster_metadata m
                WHERE %s = ANY(topics)
                ORDER BY updated_at DESC LIMIT %s
            """, (topic, page_size * (page + 1)))
            cids = [r['cluster_id'] for r in rows[page*page_size:(page+1)*page_size]]
            
            # Fallback for topics like 'Политика' which might be in the article's topic column but not metadata topics array
            if not cids and page == 0:
                rows = await db.async_execute("""
                    SELECT cluster_id, MAX(created_at) as last_article
                    FROM articles
                    WHERE topic = %s OR category = %s
                    GROUP BY cluster_id
                    ORDER BY last_article DESC LIMIT %s
                """, (topic, topic, page_size))
                cids = [r['cluster_id'] for r in rows]

            rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,)) if cids else []
        elif category:
            rows = await db.async_execute("""
                SELECT cluster_id, updated_at as last_article 
                FROM cluster_metadata m
                WHERE category = %s
                ORDER BY updated_at DESC LIMIT %s
            """, (category, page_size * (page + 1)))
            cids = [r['cluster_id'] for r in rows[page*page_size:(page+1)*page_size]]
            rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,)) if cids else []
        else:
            rows = await db.async_execute("""
                SELECT cluster_id, updated_at as last_article 
                FROM cluster_metadata m
                ORDER BY updated_at DESC LIMIT %s
            """, (page_size * (page + 1),))
            cids = [r['cluster_id'] for r in rows[page*page_size:(page+1)*page_size]]
            rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,)) if cids else []

        clusters = defaultdict(list)
        cluster_relevance = {}
        for r in rows:
            if topic and r.get("topic") != topic and r.get("category") != topic:
                continue
            if category and r.get("category") != category:
                continue
            r['reading_time'] = calculate_reading_time(r.get('description', ''))
            cid = r['cluster_id']
            clusters[cid].append(r)
            # Track best relevance score for this cluster if searching
            if q:
                score = float(r.get('match_score', 0)) + float(r.get('rank', 0))
                if cid not in cluster_relevance or score > cluster_relevance[cid]:
                    cluster_relevance[cid] = score

        ranked_clusters = [annotate_cluster_articles(arts, prefer_recent=(sort == 'recent')) for arts in clusters.values()]
        if sort == 'popular':
            ranked_clusters.sort(key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        elif sort == 'recent':
            # Strict chronological sort by the lead article (which is now the newest)
            def get_recent_sort_key(cluster_arts):
                if not cluster_arts: return 0
                lead_art = cluster_arts[0]
                dt = _coerce_datetime(lead_art.get('ingested_at') or lead_art.get('created_at'))
                return dt.timestamp() if dt else 0

            ranked_clusters.sort(key=get_recent_sort_key, reverse=True)
        elif q:
            # Relevance-first for search results
            ranked_clusters.sort(key=lambda arts: cluster_relevance.get(arts[0]['cluster_id'], 0), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster_for_homepage, reverse=True)

        start = page * page_size
        paged_clusters = ranked_clusters[start:start + page_size]
        cid_list = [c[0]["cluster_id"] for c in paged_clusters]
        
        # --- NEW: Fetch Global Clusters (America & Germany) for homepage highlights ---
        global_clusters_raw = []
        if not q and not category and not topic and not entity and page == 0:
            g_rows = await db.async_execute("""
                SELECT * FROM articles 
                WHERE category IN ('Америка', 'Германија') 
                  AND created_at >= NOW() - INTERVAL '48 hours'
                ORDER BY created_at DESC LIMIT 100
            """)
            if g_rows:
                g_grouped = defaultdict(list)
                for r in g_rows: g_grouped[r['cluster_id']].append(r)
                g_ranked = [annotate_cluster_articles(arts) for arts in g_grouped.values()]
                g_ranked.sort(key=score_cluster_for_homepage, reverse=True)
                global_clusters_raw = g_ranked[:6] # Top 6 global stories

        all_cids = cid_list + [c[0]['cluster_id'] for c in global_clusters_raw]
        meta_rows = await db.async_execute("SELECT cluster_id, representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = ANY(%s)", (all_cids,)) if all_cids else []
        meta_map = {r['cluster_id']: r for r in meta_rows}
        synthesis_ids = set(await db.async_get_synthesis_ids(all_cids)) if all_cids else set()
        summary_rows = await db.async_execute(
            """
            SELECT cluster_id, synthetic_headline, synthetic_standfirst, key_facts,
                   analyst_entities, pulse_score, pluralism_score, narrative_diversity
            FROM cluster_summaries
            WHERE cluster_id = ANY(%s)
            """,
            (all_cids,),
        ) if all_cids else []
        summary_map = {r["cluster_id"]: r for r in summary_rows}

        def _format_cluster(arts):
            main = arts[0]
            cid = main["cluster_id"]
            s = score_cluster(arts)
            homepage_score = score_cluster_for_homepage(arts)
            editorial = _compute_editorial_signals(arts, s, homepage_score)
            meta = meta_map.get(cid, {})
            summary = summary_map.get(cid, {})
            return {
                "cluster_id": cid,
                "articles": [_public_article_payload(article) for article in arts],
                "representative_image": meta.get("representative_image"),
                "dominant_color": meta.get("dominant_color"),
                "synthetic_headline": summary.get("synthetic_headline"),
                "synthetic_standfirst": summary.get("synthetic_standfirst"),
                "key_facts": _as_list(summary.get("key_facts")),
                "analyst_entities": _as_list(summary.get("analyst_entities")),
                "pulse_score": summary.get("pulse_score"),
                "pluralism_score": summary.get("pluralism_score"),
                "narrative_diversity": _parse_maybe_json(summary.get("narrative_diversity")),
                "reading_time": main.get('reading_time', 1),
                "score": round(s, 3),
                "homepage_score": round(homepage_score, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_fact_check": any(a.get("is_fact_check") for a in arts),
                "has_balanced": is_balanced(arts),
                "entities": main.get("entity_names", []),
                **editorial,
            }

        result = [_format_cluster(arts) for arts in paged_clusters]
        global_result = [_format_cluster(arts) for arts in global_clusters_raw]

        final_response = {
            "status": "success", 
            "clusters": result, 
            "global": global_result,
            "page": page, 
            "page_size": page_size,
            "has_more": len(ranked_clusters) > start + page_size,
            "entity": entity_info
        }
        set_cache(cache_key, final_response, ttl=180)
        return final_response
    except Exception as e:
        log.error(f"News Route Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": "Internal server error"})

@router.get("/search/semantic")
async def semantic_search(
    q: str = Query(..., min_length=3, max_length=API_MAX_Q_LEN),
    limit: int = Query(24, ge=1, le=50)
):
    """
    Explicit Semantic Search endpoint.
    Uses MiniLM embeddings to find relevant clusters across languages.
    """
    cache_key = f"api:search:semantic:{q}:{limit}"
    cached = cached_response(cache_key)
    if cached: return cached

    try:
        from embeddings import generate_query_embedding
        query_vec = generate_query_embedding(q)
        if not query_vec:
            raise HTTPException(status_code=500, detail="Неуспешно генерирање на вектор за пребарување")
        
        # Fetch articles using vector distance
        rows = await db.async_search_semantic(query_vec, limit=limit)
        
        # Group by cluster ID
        clusters = defaultdict(list)
        for r in rows:
            r['reading_time'] = calculate_reading_time(r.get('description', ''))
            cid = r['cluster_id']
            clusters[cid].append(r)

        # Process and sort clusters by their best similarity score
        processed = [annotate_cluster_articles(arts) for arts in clusters.values()]
        processed.sort(key=lambda arts: arts[0].get('similarity', 0), reverse=True)

        cid_list = list(clusters.keys())
        synthesis_ids = set(await db.async_get_synthesis_ids(cid_list)) if cid_list else set()

        result = []
        for arts in processed:
            main = arts[0]
            cid = main["cluster_id"]
            result.append({
                "cluster_id": cid,
                "articles": [_public_article_payload(article) for article in arts],
                "similarity": round(float(main.get('similarity', 0)), 4),
                "reading_time": main.get('reading_time', 1),
                "score": round(score_cluster(arts), 3),
                "has_synthesis": cid in synthesis_ids,
                "entities": main.get("entity_names", [])
            })

        final_response = {"status": "success", "results": result}
        set_cache(cache_key, final_response, ttl=300)
        return final_response
    except Exception as e:
        log.error(f"Semantic Search Route Error: {e}", exc_info=True)
        if isinstance(e, HTTPException): raise e
        return JSONResponse(status_code=500, content={"message": "Internal server error"})

@router.get("/cluster/{cluster_id}")
async def get_cluster_detail(cluster_id: str):
    # Validate cluster_id
    validate_cluster_id(cluster_id)
    cache_key = f"api:cluster:detail:v2:{cluster_id}"
    cached = cached_response(cache_key, ttl=3600)
    if cached:
        return cached
    try:
        rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", (cluster_id,))
        if not rows: raise HTTPException(status_code=404, detail="Кластерот не е пронајден")
        rows = [row for row in rows if _is_publicly_displayable_article(row)]
        if not rows: raise HTTPException(status_code=404, detail="Кластерот не е пронајден")
        articles = annotate_cluster_articles(rows, prefer_recent=True)
        for a in articles: a['reading_time'] = calculate_reading_time(a.get('description', ''))
        public_articles = [_public_article_payload(article) for article in articles]

        log.debug(f"[debug] Fetching summary for cluster_id: '{cluster_id}'")
        s_row = await db.async_execute_one(
            """
            SELECT summary, generated_article, synthetic_headline, synthetic_standfirst,
                   perspectives, created_at, sentiment, tone_analysis, verification_report,
                   citation_sources, key_facts, analyst_entities, pulse_score,
                   pluralism_score, narrative_diversity, storyline_narrative
            FROM cluster_summaries
            WHERE cluster_id = %s
            """,
            (cluster_id,),
        )
        log.debug(f"[debug] s_row found: {bool(s_row)}")
        
        synthesis = s_row["summary"] if s_row else None
        generated_article = s_row["generated_article"] if s_row else None
        synthetic_headline = s_row["synthetic_headline"] if s_row else None
        synthetic_standfirst = s_row["synthetic_standfirst"] if s_row else None
        
        sentiment = _parse_maybe_json(s_row.get("sentiment")) if s_row else None
        tone_analysis = _parse_maybe_json(s_row.get("tone_analysis")) if s_row else None
        if isinstance(sentiment, dict) and tone_analysis and not sentiment.get("tone_analysis"):
            sentiment["tone_analysis"] = tone_analysis
        verification_report = _parse_maybe_json(s_row.get("verification_report")) if s_row else None
        ai_summary_bullets = [re.sub(r'^[-•*]\s*', '', line).strip() for line in synthesis.split('\n') if line.strip() and not line.strip().lower().startswith('статии:')] if synthesis else []
        perspectives = _parse_maybe_json(s_row.get("perspectives")) if s_row else []
        if not perspectives: perspectives = []
        citation_sources = normalize_citation_sources(_parse_maybe_json(s_row.get("citation_sources")) if s_row else [])
        key_facts = _as_list(s_row.get("key_facts")) if s_row else []
        analyst_entities = _as_list(s_row.get("analyst_entities")) if s_row else []
        narrative_diversity = _parse_maybe_json(s_row.get("narrative_diversity")) if s_row else None
        freshness = assess_cluster_synthesis_freshness(articles, (s_row or {}).get("created_at"))
        local_fallback_synthesis = bool(
            s_row
            and not str(generated_article or "").strip()
            and not verification_report
            and (
                "Локален сублимат" in str(synthetic_standfirst or "")
                or "Автоматски преглед" in str(synthetic_standfirst or "")
                or "AI анализа" in str(synthetic_standfirst or "")
            )
        )
        if local_fallback_synthesis:
            freshness = {
                **freshness,
                "refresh_needed": True,
                "is_stale": True,
                "freshness_score": max(float(freshness.get("freshness_score") or 0.0), 2.0),
                "reasons": [*freshness.get("reasons", []), "local_fallback_synthesis"],
            }

        cluster_meta = await db.async_execute_one("SELECT tags, topics, representative_image, dominant_color, centroid FROM cluster_metadata WHERE cluster_id = %s", (cluster_id,))
        tags = filter_cluster_tags((cluster_meta.get("tags") or []) if cluster_meta else [])
        topics = (cluster_meta.get("topics") or []) if cluster_meta else []
        rep_image = cluster_meta.get("representative_image") if cluster_meta else None
        dominant_color = cluster_meta.get("dominant_color") if cluster_meta else None
        current_tags = {str(tag or "").strip() for tag in tags if str(tag or "").strip()}
        current_topics = {str(topic or "").strip() for topic in topics if str(topic or "").strip()}
        current_entities = {
            str(entity or "").strip()
            for article in articles
            for entity in (article.get("entity_names") or [])
            if str(entity or "").strip()
        }

        # Just-in-time extraction if missing
        if rep_image and not dominant_color:
            from utils import get_dominant_color
            dominant_color = get_dominant_color(rep_image)
            if dominant_color:
                await db.async_execute("UPDATE cluster_metadata SET dominant_color = %s WHERE cluster_id = %s", (dominant_color, cluster_id), fetch=False)

        related = []
        if cluster_meta and cluster_meta.get("centroid"):
            centroid_vec = json.loads(cluster_meta["centroid"]) if isinstance(cluster_meta["centroid"], str) else list(cluster_meta["centroid"])
            vec_str = "[" + ",".join(map(str, centroid_vec)) + "]"
            
            # Use pgvector directly on cluster_metadata for lightning-fast related cluster discovery
            related_query = """
                SELECT cluster_id, (1 - (centroid <=> %s::vector)) as similarity
                FROM cluster_metadata
                WHERE cluster_id != %s
                  AND centroid IS NOT NULL
                  AND updated_at >= NOW() - INTERVAL '14 days'
                ORDER BY centroid <=> %s::vector
                LIMIT 15
            """
            related_results = await db.async_execute(related_query, (vec_str, cluster_id, vec_str))
            
            related_cids = []
            for r in related_results:
                similarity = float(r.get("similarity", 0))
                # We can be slightly more lenient here since the centroid is a stable representation
                if similarity >= 0.65:
                    related_cids.append(r["cluster_id"])
                    
            if related_cids:
                r_rows = await db.async_execute("SELECT a.*, COALESCE(m.tags, '{}') as cluster_tags FROM articles a LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE a.cluster_id = ANY(%s)", (related_cids,))
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
                    related.append({
                        "cluster_id": item["cluster_id"],
                        "title": item["title"],
                        "image_url": item.get("image_url"),
                        "tags": shared_tags,
                        "relationship_label": item.get("relationship_label") or "Сродна тема",
                        "shared_tags": shared_tags,
                        "shared_topics": shared_topics,
                        "shared_entities": shared_entities,
                        "has_synthesis": item["cluster_id"] in synthesis_ids,
                    })

        chrono = sorted(articles, key=lambda x: x['created_at'])
        timeline = []
        for i, a in enumerate(chrono):
            is_major = (a.get('source_signal') or {}).get('trust_level', 0) >= 0.8
            milestone = "ПОЧЕТОК" if i == 0 else ("КОНСЕНЗУС" if i == len(chrono)-1 and len(chrono)>=3 else "РАЗВОЈ")
            timeline.append({"article_id": a['id'], "title": cleanAndDecode(a['title']), "source": a['source'], "created_at": a['created_at'], "is_first": i == 0, "is_major": is_major, "milestone": milestone})

        response = {"status": "success", "data": {"cluster_id": cluster_id, "articles": public_articles, "timeline": timeline, "synthesis": synthesis, "has_synthesis": bool(synthesis), "generated_article": generated_article, "synthetic_headline": synthetic_headline, "synthetic_standfirst": synthetic_standfirst, "sentiment": sentiment, "verification_report": verification_report, "ai_summary_bullets": ai_summary_bullets, "citation_sources": citation_sources, "key_facts": key_facts, "analyst_entities": analyst_entities, "pulse_score": s_row.get("pulse_score") if s_row else None, "pluralism_score": s_row.get("pluralism_score") if s_row else None, "narrative_diversity": narrative_diversity, "storyline_narrative": s_row.get("storyline_narrative") if s_row else None, "synthesis_updated_at": freshness["synthesis_updated_at"], "synthesis_freshness": freshness, "perspectives": perspectives, "tags": tags, "topics": topics, "representative_image": rep_image, "dominant_color": dominant_color, "related": related, "total_reading_time": sum(a['reading_time'] for a in articles)}}
        set_cache(cache_key, response, ttl=3600)
        return response

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Cluster Detail Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Внатрешна серверска грешка")

@router.get("/cluster/{cluster_id}/history")
async def get_cluster_history(cluster_id: str):
    """
    Returns the historical versions of a cluster synthesis.
    """
    validate_cluster_id(cluster_id)
    try:
        rows = await db.async_execute("""
            SELECT summary, generated_article, synthetic_headline, synthetic_standfirst, perspectives, verification_report, created_at 
            FROM cluster_summary_history 
            WHERE cluster_id = %s 
            ORDER BY created_at DESC 
            LIMIT 20
        """, (cluster_id,))
        
        def _parse_maybe_json(val):
            if not val: return None
            if isinstance(val, (dict, list)): return val
            try: return json.loads(val)
            except Exception: return None

        history = []
        for r in rows:
            history.append({
                "summary": r["summary"],
                "generated_article": r["generated_article"],
                "synthetic_headline": r["synthetic_headline"],
                "synthetic_standfirst": r["synthetic_standfirst"],
                "perspectives": _parse_maybe_json(r["perspectives"]),
                "verification_report": _parse_maybe_json(r["verification_report"]),
                "created_at": r["created_at"]
            })
            
        return {"status": "success", "history": history}
    except Exception as e:
        log.error(f"Cluster History Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": "Internal server error"})

@router.get("/cluster/{cluster_id}/historical")
async def get_historical_events(cluster_id: str):
    """
    Finds semantically similar clusters from the 60-day archive.
    """
    validate_cluster_id(cluster_id)
    cache_key = f"api:cluster:{cluster_id}:historical:v1"
    cached = cached_response(cache_key)
    if cached: return cached

    try:
        # 1. Get average embedding for the target cluster
        vec_rows = await db.async_execute("SELECT embedding FROM articles WHERE cluster_id = %s AND embedding IS NOT NULL", (cluster_id,))
        if not vec_rows:
            return {"status": "success", "events": []}

        try:
            import numpy as np
        except ImportError:
            import sys
            if 'numpy' not in sys.modules:
                raise
            import numpy as np
        
        def parse_vec(v):
            if isinstance(v, str):
                import json
                v = json.loads(v)
            return np.array(v, dtype=np.float32)

        vecs = [parse_vec(r['embedding']) for r in vec_rows]
        avg_vec = np.mean(vecs, axis=0).tolist()
        vec_str = "[" + ",".join(map(str, avg_vec)) + "]"

        # 2. Query archive using vector similarity
        # Exclude today's window to find truly historical context
        rows = await db.async_execute("""
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
            WHERE similarity > 0.68
            ORDER BY cluster_id, similarity DESC, created_at DESC
            LIMIT 5
        """, (vec_str, cluster_id))

        events = []
        for r in sorted(rows, key=lambda x: x['similarity'], reverse=True):
            events.append({
                "cluster_id": r["cluster_id"],
                "title": cleanAndDecode(r["title"]),
                "created_at": r["created_at"],
                "category": r["category"],
                "similarity": round(float(r["similarity"]), 4)
            })

        res = {"status": "success", "events": events}
        set_cache(cache_key, res, ttl=3600)
        return res
    except Exception as e:
        log.error(f"Historical Search Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": "Internal server error"})

@router.get("/live")
async def get_live_route(request: Request):
    return StreamingResponse(event_stream("updates", request=request), media_type="text/event-stream")
