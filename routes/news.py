import json
import logging
import re
from typing import Optional, List
from collections import defaultdict
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from database import db_manager as db
from utils import (
    score_cluster, rank_articles_in_cluster, calculate_reading_time, 
    cached_response, set_cache, is_balanced, assess_cluster_synthesis_freshness,
    annotate_cluster_articles, score_cluster_for_homepage,
    event_stream, record_runtime_event,
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
from api_helpers import (
    normalize_perspectives as _parse_perspectives_blob,
)
from .common import cleanAndDecode, _news_row_limit
from .security import validate_cluster_id, validate_string_param

log = logging.getLogger("presek")
router = APIRouter()

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
    from categories import normalize_headline
    import datetime
    res = {}
    for key, value in article.items():
        if key not in _PUBLIC_ARTICLE_FIELDS:
            continue
        if key == "title":
            res[key] = normalize_headline(value)
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
    return res

@router.get("/news")
async def get_news(
    q: Optional[str] = None,
    category: Optional[str] = None,
    topic: Optional[str] = None,
    entity: Optional[str] = None,
    sort: str = "recent",
    page: int = 0,
    page_size: int = 24
):
    cache_key = f"api:news:{q}:{category}:{topic}:{entity}:{sort}:{page}:{page_size}"
    cached = cached_response(cache_key)
    if cached: return cached

    try:
        page = max(0, min(int(page or 0), API_MAX_PAGE))
        page_size = max(1, min(int(page_size or 24), 50))
        row_limit = _news_row_limit(page, page_size)
        if q: q = q.strip()[:API_MAX_Q_LEN]

        if q:
            from embeddings import generate_query_embedding
            query_vec = generate_query_embedding(q)
            rows = await db.async_hybrid_search(q, query_vec, limit=row_limit) if query_vec else await db.async_search_articles(q, limit=row_limit)
        elif entity:
            rows = await db.async_execute("SELECT cluster_id, MAX(created_at) as last_article FROM cluster_entities ce JOIN articles a USING (cluster_id) WHERE ce.entity_name = %s GROUP BY cluster_id ORDER BY last_article DESC LIMIT %s", (entity, page_size * (page + 1)))
            cids = [r['cluster_id'] for r in rows[page*page_size:(page+1)*page_size]]
            rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,)) if cids else []
        elif topic:
            rows = await db.async_execute("SELECT cluster_id, MAX(created_at) as last_article FROM articles WHERE topic = %s GROUP BY cluster_id ORDER BY last_article DESC LIMIT %s", (topic, page_size * (page + 1)))
            cids = [r['cluster_id'] for r in rows[page*page_size:(page+1)*page_size]]
            rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,)) if cids else []
        elif category:
            rows = await db.async_execute("SELECT cluster_id, MAX(created_at) as last_article FROM articles WHERE category = %s GROUP BY cluster_id ORDER BY last_article DESC LIMIT %s", (category, page_size * (page + 1)))
            cids = [r['cluster_id'] for r in rows[page*page_size:(page+1)*page_size]]
            rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,)) if cids else []
        else:
            rows = await db.async_execute("SELECT cluster_id, MAX(created_at) as last_article FROM articles GROUP BY cluster_id ORDER BY last_article DESC LIMIT %s", (page_size * (page + 1),))
            cids = [r['cluster_id'] for r in rows[page*page_size:(page+1)*page_size]]
            rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,)) if cids else []

        clusters = defaultdict(list)
        cluster_relevance = {}
        for r in rows:
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
                dt = _coerce_datetime(lead_art.get('created_at'))
                return dt.timestamp() if dt else 0
            
            from utils import _coerce_datetime
            ranked_clusters.sort(key=get_recent_sort_key, reverse=True)
        elif q:
            # Relevance-first for search results
            ranked_clusters.sort(key=lambda arts: cluster_relevance.get(arts[0]['cluster_id'], 0), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster_for_homepage, reverse=True)

        start = page * page_size
        paged_clusters = ranked_clusters[start:start + page_size]
        cid_list = [c[0]["cluster_id"] for c in paged_clusters]
        meta_rows = await db.async_execute("SELECT cluster_id, representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = ANY(%s)", (cid_list,)) if cid_list else []
        meta_map = {r['cluster_id']: r for r in meta_rows}
        synthesis_ids = set(await db.async_get_synthesis_ids(cid_list)) if cid_list else set()

        result = []
        for arts in paged_clusters:
            main = arts[0]
            cid = main["cluster_id"]
            s = score_cluster(arts)
            meta = meta_map.get(cid, {})
            result.append({
                "cluster_id": cid,
                "articles": [_public_article_payload(article) for article in arts],
                "representative_image": meta.get("representative_image"),
                "dominant_color": meta.get("dominant_color"),
                "reading_time": main.get('reading_time', 1),
                "score": round(s, 3),
                "homepage_score": round(score_cluster_for_homepage(arts), 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_fact_check": any(a.get("is_fact_check") for a in arts),
                "has_balanced": is_balanced(arts),
                "entities": main.get("entity_names", [])
            })

        final_response = {"status": "success", "clusters": result, "page": page, "has_more": len(ranked_clusters) > start + page_size}
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
            raise HTTPException(status_code=500, detail="Failed to generate query embedding")
        
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
    try:
        rows = await db.async_execute("SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", (cluster_id,))
        if not rows: raise HTTPException(status_code=404, detail="Cluster not found")
        articles = annotate_cluster_articles(rows, prefer_recent=True)
        for a in articles: a['reading_time'] = calculate_reading_time(a.get('description', ''))
        public_articles = [_public_article_payload(article) for article in articles]

        s_row = await db.async_execute_one("SELECT summary, generated_article, perspectives, created_at, sentiment, verification_report FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,))
        synthesis = s_row["summary"] if s_row else None
        generated_article = s_row["generated_article"] if s_row else None
        
        def _parse_maybe_json(val):
            if not val: return None
            if isinstance(val, (dict, list)): return val
            try: return json.loads(val)
            except Exception: return None

        sentiment = _parse_maybe_json(s_row.get("sentiment")) if s_row else None
        verification_report = _parse_maybe_json(s_row.get("verification_report")) if s_row else None
        ai_summary_bullets = [re.sub(r'^[-•*]\s*', '', line).strip() for line in synthesis.split('\n') if line.strip() and not line.strip().lower().startswith('статии:')] if synthesis else []
        perspectives = _parse_maybe_json(s_row.get("perspectives")) if s_row else []
        if not perspectives: perspectives = []
        freshness = assess_cluster_synthesis_freshness(articles, (s_row or {}).get("created_at"))

        m_row = await db.async_execute_one("SELECT tags, topics, representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = %s", (cluster_id,))
        tags = filter_cluster_tags((m_row.get("tags") or []) if m_row else [])
        topics = (m_row.get("topics") or []) if m_row else []
        rep_image = m_row.get("representative_image") if m_row else None
        dominant_color = m_row.get("dominant_color") if m_row else None
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
        lead_article = articles[0] if articles else None
        if lead_article and lead_article.get("embedding"):
            lead_vec = json.loads(lead_article["embedding"]) if isinstance(lead_article["embedding"], str) else list(lead_article["embedding"])
            related_results = await db.async_search_semantic(lead_vec, limit=8)
            related_cids = []
            seen = {cluster_id}
            for r in related_results:
                cid = r.get("cluster_id")
                if cid and cid not in seen:
                    related_cids.append(cid)
                    seen.add(cid)
                    if len(related_cids) >= 4: break
            if related_cids:
                r_rows = await db.async_execute("SELECT a.*, COALESCE(m.tags, '{}') as cluster_tags FROM articles a LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE a.cluster_id = ANY(%s)", (related_cids,))
                r_grouped = defaultdict(list)
                for r in r_rows: r_grouped[r["cluster_id"]].append(r)
                synthesis_ids = set(await db.async_get_synthesis_ids(related_cids)) if related_cids else set()
                for cid in related_cids:
                    arts = r_grouped.get(cid)
                    if arts:
                        main = annotate_cluster_articles(arts)[0]
                        candidate_tags = {
                            str(tag or "").strip()
                            for article in arts
                            for tag in (article.get("cluster_tags") or [])
                            if str(tag or "").strip()
                        }
                        candidate_topics = {
                            str(article.get("topic") or "").strip()
                            for article in arts
                            if str(article.get("topic") or "").strip()
                        }
                        candidate_entities = {
                            str(entity or "").strip()
                            for article in arts
                            for entity in (article.get("entity_names") or [])
                            if str(entity or "").strip()
                        }
                        shared_tags = sorted(current_tags & candidate_tags)[:3]
                        shared_topics = sorted(current_topics & candidate_topics)[:2]
                        shared_entities = sorted(current_entities & candidate_entities)[:3]
                        related.append({
                            "cluster_id": cid,
                            "title": main["title"],
                            "image_url": main.get("image_url"),
                            "tags": filter_cluster_tags(main.get("cluster_tags", [])),
                            "relationship_label": "Сродна тема",
                            "shared_tags": shared_tags,
                            "shared_topics": shared_topics,
                            "shared_entities": shared_entities,
                            "has_synthesis": cid in synthesis_ids,
                        })

        chrono = sorted(articles, key=lambda x: x['created_at'])
        timeline = []
        for i, a in enumerate(chrono):
            is_major = (a.get('source_signal') or {}).get('trust_level', 0) >= 0.8
            milestone = "ПОЧЕТОК" if i == 0 else ("КОНСЕНЗУС" if i == len(chrono)-1 and len(chrono)>=3 else "РАЗВОЈ")
            timeline.append({"article_id": a['id'], "title": cleanAndDecode(a['title']), "source": a['source'], "created_at": a['created_at'], "is_first": i == 0, "is_major": is_major, "milestone": milestone})

        return {"status": "success", "data": {"cluster_id": cluster_id, "articles": public_articles, "timeline": timeline, "synthesis": synthesis, "has_synthesis": bool(synthesis), "generated_article": generated_article, "sentiment": sentiment, "verification_report": verification_report, "ai_summary_bullets": ai_summary_bullets, "synthesis_updated_at": freshness["synthesis_updated_at"], "synthesis_freshness": freshness, "perspectives": perspectives, "tags": tags, "topics": topics, "representative_image": rep_image, "dominant_color": dominant_color, "related": related, "total_reading_time": sum(a['reading_time'] for a in articles)}}

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Cluster Detail Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

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
