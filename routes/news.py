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
from local_nlp import (
    filter_cluster_tags,
)
from api_helpers import (
    normalize_perspectives as _parse_perspectives_blob,
)
from .common import cleanAndDecode, _news_row_limit

log = logging.getLogger("presek")
router = APIRouter()

@router.get("/api/news")
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
            rows = db.hybrid_search(q, query_vec, limit=row_limit) if query_vec else db.search_articles(q, limit=row_limit)
        elif entity:
            rows = db.execute("SELECT a.* FROM articles a JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id WHERE ce.entity_name = %s ORDER BY a.created_at DESC LIMIT %s", (entity, row_limit))
        elif topic:
            rows = db.execute("SELECT * FROM articles WHERE topic = %s ORDER BY created_at DESC LIMIT %s", (topic, row_limit))
        elif category:
            rows = db.execute("SELECT * FROM articles WHERE category = %s ORDER BY created_at DESC LIMIT %s", (category, row_limit))
        else:
            rows = db.execute("SELECT * FROM articles ORDER BY created_at DESC LIMIT %s", (row_limit,))

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

        ranked_clusters = [annotate_cluster_articles(arts) for arts in clusters.values()]
        if sort == 'popular':
            ranked_clusters.sort(key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        elif q and sort == 'recent':
            # Relevance-first for search results
            ranked_clusters.sort(key=lambda arts: cluster_relevance.get(arts[0]['cluster_id'], 0), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster_for_homepage, reverse=True)

        start = page * page_size
        paged_clusters = ranked_clusters[start:start + page_size]
        cid_list = [c[0]["cluster_id"] for c in paged_clusters]
        rep_images = {r['cluster_id']: r['representative_image'] for r in db.execute("SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)", (cid_list,))} if cid_list else {}
        synthesis_ids = set(db.get_synthesis_ids(cid_list)) if cid_list else set()

        result = []
        for arts in paged_clusters:
            main = arts[0]
            cid = main["cluster_id"]
            s = score_cluster(arts)
            result.append({
                "cluster_id": cid,
                "articles": arts,
                "representative_image": rep_images.get(cid),
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

@router.get("/api/cluster/{cluster_id}")
async def get_cluster_detail(cluster_id: str):
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")
    try:
        rows = db.execute("SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", (cluster_id,))
        if not rows: raise HTTPException(status_code=404, detail="Cluster not found")
        articles = annotate_cluster_articles(rows)
        for a in articles: a['reading_time'] = calculate_reading_time(a.get('description', ''))

        s_row = db.execute_one("SELECT summary, generated_article, perspectives, created_at, sentiment, verification_report FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,))
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

        m_row = db.execute_one("SELECT tags, topics FROM cluster_metadata WHERE cluster_id = %s", (cluster_id,))
        tags = filter_cluster_tags((m_row.get("tags") or []) if m_row else [])
        topics = (m_row.get("topics") or []) if m_row else []

        related = []
        lead_article = articles[0] if articles else None
        if lead_article and lead_article.get("embedding"):
            lead_vec = json.loads(lead_article["embedding"]) if isinstance(lead_article["embedding"], str) else list(lead_article["embedding"])
            related_results = db.search_semantic(lead_vec, limit=8)
            related_cids = []
            seen = {cluster_id}
            for r in related_results:
                cid = r.get("cluster_id")
                if cid and cid not in seen:
                    related_cids.append(cid)
                    seen.add(cid)
                    if len(related_cids) >= 4: break
            if related_cids:
                r_rows = db.execute("SELECT a.*, COALESCE(m.tags, '{}') as cluster_tags FROM articles a LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE a.cluster_id = ANY(%s)", (related_cids,))
                r_grouped = defaultdict(list)
                for r in r_rows: r_grouped[r["cluster_id"]].append(r)
                for cid in related_cids:
                    arts = r_grouped.get(cid)
                    if arts:
                        main = annotate_cluster_articles(arts)[0]
                        related.append({"cluster_id": cid, "title": main["title"], "image_url": main.get("image_url"), "tags": filter_cluster_tags(main.get("cluster_tags", [])), "relationship_label": "Сродна тема"})

        chrono = sorted(articles, key=lambda x: x['created_at'])
        timeline = []
        for i, a in enumerate(chrono):
            is_major = (a.get('source_signal') or {}).get('trust_level', 0) >= 0.8
            milestone = "ПОЧЕТОК" if i == 0 else ("КОНСЕНЗУС" if i == len(chrono)-1 and len(chrono)>=3 else "РАЗВОЈ")
            timeline.append({"article_id": a['id'], "title": cleanAndDecode(a['title']), "source": a['source'], "created_at": a['created_at'], "is_first": i == 0, "is_major": is_major, "milestone": milestone})

        return {"status": "success", "data": {"cluster_id": cluster_id, "articles": articles, "timeline": timeline, "synthesis": synthesis, "generated_article": generated_article, "sentiment": sentiment, "verification_report": verification_report, "ai_summary_bullets": ai_summary_bullets, "synthesis_updated_at": freshness["synthesis_updated_at"], "synthesis_freshness": freshness, "perspectives": perspectives, "tags": tags, "topics": topics, "related": related, "total_reading_time": sum(a['reading_time'] for a in articles)}}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Cluster Detail Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/api/live")
async def get_live_route():
    return StreamingResponse(event_stream("updates"), media_type="text/event-stream")
