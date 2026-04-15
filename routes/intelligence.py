import json
import logging
import re
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException

from database import db_manager as db
from embeddings import generate_query_embedding

router = APIRouter()

@router.get("/storylines/recent")
async def get_recent_storylines(limit: int = 10):
    """Fetch recently active long-term storylines."""
    return db.execute("""
        SELECT s.*, 
               (SELECT COUNT(*) FROM storyline_clusters WHERE storyline_id = s.id) as cluster_count
        FROM storylines s
        WHERE s.is_active = TRUE
        ORDER BY s.last_activity DESC
        LIMIT %s
    """, (limit,))

@router.get("/storyline/{storyline_id}")
async def get_storyline_detail(storyline_id: int):
    """Fetch a storyline and its constituent clusters for a timeline view."""
    story = db.execute_one("SELECT * FROM storylines WHERE id = %s", (storyline_id,))
    if not story:
        return {"error": "Storyline not found"}
    
    clusters = db.execute("""
        SELECT c.*, sc.relevance_score
        FROM storyline_clusters sc
        JOIN cluster_summaries c ON sc.cluster_id = c.cluster_id
        WHERE sc.storyline_id = %s
        ORDER BY c.created_at ASC
    """, (storyline_id,))
    
    return {"story": story, "timeline": clusters}

@router.get("/media-pulse")
async def get_media_pulse():
    """Daily sentiment and bias radar data."""
    return db.execute("""
        SELECT a.category, 
               AVG((cs.sentiment->>'score')::float) as avg_sentiment,
               COUNT(DISTINCT a.source) as source_diversity,
               COUNT(*) as article_count
        FROM articles a
        JOIN cluster_summaries cs ON a.cluster_id = cs.cluster_id
        WHERE a.created_at >= NOW() - INTERVAL '24 hours'
        GROUP BY a.category
        HAVING COUNT(*) > 5
    """)

@router.get("/entity/{name}/power-map")
async def get_entity_power_map(name: str, limit: int = 6):
    """Fetch related entities from the knowledge graph."""
    return db.execute("""
        SELECT CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity,
               weight
        FROM knowledge_relationships
        WHERE entity_a = %s OR entity_b = %s
        ORDER BY weight DESC
        LIMIT %s
    """, (name, name, name, limit))

@router.get("/search/semantic")
async def semantic_search(q: str, limit: int = 20):
    """AI-powered search using the HNSW vector index."""
    embedding = generate_query_embedding(q)
    if not embedding:
        return {"error": "Could not generate embedding"}
    
    return db.search_semantic(embedding, limit=limit)
from utils import cached_response, set_cache, score_cluster
from nlp import normalize_tag_name
from .common import cleanAndDecode, _is_valid_focus_entity

log = logging.getLogger("presek")
router = APIRouter()

@router.get("/api/intelligence/source-pulse")
async def get_source_pulse():
    sql = """
        WITH first_reporters AS (
            SELECT DISTINCT ON (cluster_id) source, cluster_id
            FROM articles
            ORDER BY cluster_id, created_at ASC
        )
        SELECT 
            a.source,
            AVG(CAST(s.sentiment->>'score' AS REAL)) as avg_sentiment,
            AVG(CAST(s.sentiment->'tone_analysis'->>'objectivity' AS REAL)) as avg_objectivity,
            AVG(CAST(s.sentiment->'tone_analysis'->>'sensationalism' AS REAL)) as avg_sensationalism,
            COUNT(DISTINCT a.cluster_id) as cluster_count,
            (SELECT COUNT(*) FROM first_reporters fr 
             WHERE fr.source = a.source 
               AND fr.cluster_id IN (SELECT cluster_id FROM articles WHERE created_at >= NOW() - INTERVAL '7 days')
            ) as first_report_count
        FROM cluster_summaries s
        JOIN articles a ON s.cluster_id = a.cluster_id
        WHERE s.sentiment IS NOT NULL AND s.created_at >= NOW() - INTERVAL '7 days'
        GROUP BY a.source HAVING COUNT(DISTINCT a.cluster_id) >= 3
        ORDER BY cluster_count DESC
    """
    return {"status": "success", "data": db.execute(sql)}

@router.get("/api/intelligence/entity/{name}")
async def get_entity_profile(name: str):
    entity = db.execute_one("SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score FROM knowledge_entities WHERE name = %s", (name,))
    if not entity:
        if not db.execute_one("SELECT 1 FROM cluster_metadata WHERE %s = ANY(tags) LIMIT 1", (name,)):
            raise HTTPException(status_code=404, detail="Entity not found")
        entity = {"name": name, "type": "ENTITY", "total_mentions": 0, "first_seen": None, "last_seen": None, "sentiment_score": 0}
    
    relationships = db.execute("SELECT CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity, weight FROM knowledge_relationships WHERE entity_a = %s OR entity_b = %s ORDER BY weight DESC LIMIT 8", (name, name, name))
    media_stats = db.execute("SELECT a.source, COUNT(DISTINCT a.cluster_id) as mention_count FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE %s = ANY(m.tags) GROUP BY a.source ORDER BY mention_count DESC LIMIT 5", (name,))
    category_stats = db.execute("SELECT a.category, COUNT(DISTINCT a.cluster_id) as count FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id WHERE %s = ANY(m.tags) AND a.category IS NOT NULL AND a.category != '' GROUP BY a.category ORDER BY count DESC LIMIT 5", (name,))
    sentiment_history = db.execute("SELECT DATE(a.created_at) as day, AVG(CAST(s.sentiment->>'score' AS FLOAT)) as avg_sentiment, COUNT(DISTINCT a.cluster_id) as volume FROM articles a JOIN cluster_metadata m ON a.cluster_id = m.cluster_id JOIN cluster_summaries s ON a.cluster_id = s.cluster_id WHERE %s = ANY(m.tags) AND a.created_at >= NOW() - INTERVAL '14 days' AND s.sentiment IS NOT NULL GROUP BY day ORDER BY day ASC", (name,))
    recent = db.execute("SELECT c.cluster_id, (SELECT title FROM articles WHERE cluster_id = c.cluster_id ORDER BY created_at DESC LIMIT 1) as title, c.updated_at as created_at, s.summary, s.sentiment FROM cluster_metadata c LEFT JOIN cluster_summaries s ON c.cluster_id = s.cluster_id WHERE %s = ANY(c.tags) ORDER BY c.updated_at DESC LIMIT 10", (name,))
    
    processed = []
    for c in recent:
        bullets = [re.sub(r'^[-•*]\s*', '', line).strip() for line in (c["summary"] or "").split('\n') if line.strip() and not line.strip().lower().startswith('статии:')]
        sent = json.loads(c["sentiment"]) if isinstance(c["sentiment"], str) else c["sentiment"]
        processed.append({"cluster_id": c["cluster_id"], "title": cleanAndDecode(c["title"]), "created_at": c["created_at"], "bullets": bullets[:2], "sentiment": sent})

    return {"profile": entity, "related": relationships, "media": media_stats, "categories": category_stats, "sentiment_history": sentiment_history, "clusters": processed}

@router.get("/api/intelligence/top-entities")
async def get_top_entities(limit: int = 10):
    cache_key = f"api:top-entities:{limit}"
    cached = cached_response(cache_key)
    if cached: return cached
    fetch_limit = max(limit * 6, 40)
    rows = db.execute("SELECT tag AS name, COUNT(*) AS total_mentions FROM (SELECT cm.cluster_id, UNNEST(cm.tags) AS tag FROM cluster_metadata cm JOIN articles a ON a.cluster_id = cm.cluster_id WHERE a.created_at >= NOW() - INTERVAL '48 hours' AND cm.tags IS NOT NULL GROUP BY cm.cluster_id, tag) t GROUP BY tag ORDER BY total_mentions DESC LIMIT %s", (fetch_limit,))
    filtered = []
    seen = set()
    for row in rows:
        norm = normalize_tag_name(row["name"])
        if not _is_valid_focus_entity(norm, None): continue
        if norm.casefold() in seen: continue
        seen.add(norm.casefold())
        filtered.append({"name": norm, "type": None, "total_mentions": row.get("total_mentions")})
        if len(filtered) >= limit: break
    set_cache(cache_key, filtered, ttl=600)
    return filtered

@router.get("/api/intelligence/entity/{name}/topics")
async def get_entity_topics(name: str):
    return {"status": "success", "data": db.execute("SELECT a.topic, COUNT(*) as count FROM articles a JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id WHERE ce.entity_name = %s AND a.topic IS NOT NULL GROUP BY a.topic ORDER BY count DESC LIMIT 5", (name,))}

@router.get("/api/intelligence/live-map")
async def get_live_map():
    return {"status": "success", "data": db.execute("SELECT source, COUNT(*) as activity_score FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' GROUP BY source ORDER BY activity_score DESC")}

@router.get("/api/intelligence/compare-sources")
async def compare_sources(s1: str, s2: str):
    rows = db.execute("SELECT a.source, AVG(CAST(s.sentiment->>'score' AS REAL)) as avg_sentiment, AVG(CAST(s.sentiment->'tone_analysis'->>'objectivity' AS REAL)) as avg_objectivity, AVG(CAST(s.sentiment->'tone_analysis'->>'sensationalism' AS REAL)) as avg_sensationalism, COUNT(DISTINCT a.cluster_id) as cluster_count FROM cluster_summaries s JOIN articles a ON s.cluster_id = a.cluster_id WHERE a.source = ANY(%s) AND s.sentiment IS NOT NULL AND s.created_at >= NOW() - INTERVAL '30 days' GROUP BY a.source", ([s1, s2],))
    overlap = db.execute_one("WITH src_c AS (SELECT source, cluster_id FROM articles WHERE source = ANY(%s) AND created_at >= NOW() - INTERVAL '30 days' GROUP BY source, cluster_id) SELECT COUNT(*) FILTER (WHERE s1.cluster_id IS NOT NULL AND s2.cluster_id IS NOT NULL) as shared_clusters, COUNT(*) FILTER (WHERE s1.cluster_id IS NOT NULL AND s2.cluster_id IS NULL) as s1_exclusive, COUNT(*) FILTER (WHERE s1.cluster_id IS NULL AND s2.cluster_id IS NOT NULL) as s2_exclusive FROM (SELECT DISTINCT cluster_id FROM src_c WHERE source = %s) s1 FULL OUTER JOIN (SELECT DISTINCT cluster_id FROM src_c WHERE source = %s) s2 ON s1.cluster_id = s2.cluster_id", ([s1, s2], s1, s2))
    return {"status": "success", "data": rows, "overlap": overlap}

@router.post("/api/intelligence/recommendations")
async def get_personalized_recommendations(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    recent_ids = payload.get("recentlyRead", [])[:10]
    followed = payload.get("followedTopics", [])
    limit = min(int(payload.get("limit", 6)), 20)
    if not recent_ids and not followed: return {"status": "success", "clusters": []}
    user_vectors = []
    if recent_ids:
        rows = db.execute("SELECT embedding FROM articles WHERE cluster_id = ANY(%s) AND embedding IS NOT NULL LIMIT 20", (recent_ids,))
        for r in rows:
            if r["embedding"]: user_vectors.append(json.loads(r["embedding"]) if isinstance(r["embedding"], str) else list(r["embedding"]))
    from embeddings import generate_query_embedding
    for t in followed:
        vec = generate_query_embedding(t)
        if vec: user_vectors.append(vec)
    if not user_vectors: return {"status": "success", "clusters": []}
    import numpy as np
    avg_vec = np.mean(user_vectors, axis=0).tolist()
    results = db.search_semantic(avg_vec, limit=limit * 3)
    seen = set(recent_ids)
    cids = []
    for r in results:
        cid = r.get("cluster_id")
        if cid and cid not in seen:
            cids.append(cid)
            seen.add(cid)
            if len(cids) >= limit: break
    if not cids: return {"status": "success", "clusters": []}
    rows = db.execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,))
    cmap = {}
    for r in rows: cmap.setdefault(r["cluster_id"], []).append(r)
    formatted = []
    for cid in cids:
        arts = cmap.get(cid, [])
        if not arts: continue
        s_row = db.execute_one("SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cid,))
        m_row = db.execute_one("SELECT representative_image FROM cluster_metadata WHERE cluster_id = %s", (cid,))
        formatted.append({"cluster_id": cid, "articles": arts, "representative_image": m_row["representative_image"] if m_row else None, "score": score_cluster(arts), "has_synthesis": bool(s_row and s_row["summary"]), "is_breaking": any(a.get("is_breaking") for a in arts), "reason": "Предлог за Вас"})
    return {"status": "success", "clusters": formatted}
