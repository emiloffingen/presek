from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging
from typing import Optional, List
from collections import defaultdict

from database import db_manager as db
from utils import score_cluster, rank_articles_in_cluster, calculate_reading_time
from ai_engine import PROVIDERS, _call_ai
from prompts import SYNTHESIS_SYSTEM_PROMPT

log = logging.getLogger("presek")

app = FastAPI(title="Presek API 6.0", version="6.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "6.0.0-async"}

@app.get("/api/intelligence/entity/{name}")
async def get_entity_profile(name: str):
    """Returns detailed profile and relationships for an entity."""
    entity = db.execute_one(\"\"\"
        SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score
        FROM knowledge_entities WHERE name = %s
    \"\"\", (name,))
    
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Get top relationships
    relationships = db.execute(\"\"\"
        SELECT 
            CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity,
            weight
        FROM knowledge_relationships
        WHERE entity_a = %s OR entity_b = %s
        ORDER BY weight DESC LIMIT 10
    \"\"\", (name, name, name))
    
    return {
        "profile": entity,
        "related": relationships
    }

@app.get("/api/news")
async def get_news(
    q: Optional[str] = None,
    category: Optional[str] = None,
    topic: Optional[str] = None,
    entity: Optional[str] = None,
    sort: str = "recent",
    page: int = 0,
    page_size: int = 24
):
    try:
        if q:
            rows = db.search_articles(q, limit=100)
        elif entity:
            # Filter clusters containing this entity
            rows = db.execute(\"\"\"
                SELECT a.* FROM articles a
                JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id
                WHERE ce.entity_name = %s
                ORDER BY a.created_at DESC LIMIT 100
            \"\"\", (entity,))
        elif category:
            rows = db.get_articles_by_country(None, category=category, limit=100)
        else:
            rows = db.get_articles_by_country("🇲🇰", limit=100)

        clusters = defaultdict(list)
        for r in rows:
            r['reading_time'] = calculate_reading_time(r.get('description', ''))
            clusters[r['cluster_id']].append(r)

        ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        
        if sort == 'popular':
            ranked_clusters.sort(key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster, reverse=True)

        start = page * page_size
        paged = ranked_clusters[start:start + page_size]

        result = []
        for arts in paged:
            main = arts[0]
            result.append({
                "cluster_id": main["cluster_id"],
                "articles": arts,
                "is_breaking": any(a.get("is_breaking") for a in arts), # Simplified
                "score": score_cluster(arts)
            })

        return {
            "status": "success",
            "clusters": result,
            "page": page,
            "has_more": len(ranked_clusters) > start + page_size
        }
    except Exception as e:
        log.error(f"FastAPI News Error: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/api/chat/stream")
async def chat_stream(cluster_id: str, query: str):
    """Streams AI response for a specific cluster."""
    
    # 1. Get cluster context
    articles = db.execute("SELECT title, description, source FROM articles WHERE cluster_id = %s LIMIT 10", (cluster_id,))
    if not articles:
        raise HTTPException(status_code=404, detail="Cluster not found")
    
    context = "\n".join([f"- [{a['source']}]: {a['title']}" for a in articles])
    prompt = f"Во контекст на овие вести:\n{context}\n\nКорисникот прашува: {query}"
    system = "Ти си асистент на Пресек. Одговарај на македонски јазик кратко и јасно врз основа на дадените вести."

    async def generate():
        provider = PROVIDERS.get("gemini")
        if not provider:
            yield "data: " + json.dumps({"error": "No AI provider available"}) + "\n\n"
            return

        async for chunk in provider.stream_call(prompt, system, 1000):
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
