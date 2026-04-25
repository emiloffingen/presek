import os
import secrets
import logging
import datetime
import time
import re
import requests
import importlib.util
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
import fastapi
if not hasattr(fastapi, "responses"):
    import fastapi.responses
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

import database
from database import db_manager as db
import config
from version import APP_VERSION, APP_VERSION_LABEL, get_full_version_info

# Initialize Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.api")

app = FastAPI(
    title="Пресек API",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Startup Event
@app.on_event("startup")
async def startup_event():
    log.info(f"Пресек API v{APP_VERSION} ({APP_VERSION_LABEL}) starting up...")

# Import and include routers
from routes import home, news, intelligence, profile, stats, system

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "time": datetime.datetime.now().isoformat()
    }

@app.get("/api/version")
async def version_info():
    return get_full_version_info()

# Proxy for images to avoid CORS/Mixed content issues on client
@app.get("/proxy")
async def image_proxy(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    # Simple SSRF protection: only allow http/https
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        # Use a reasonable timeout and headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        response.raise_for_status()
        
        from fastapi.responses import StreamingResponse
        return StreamingResponse(response.iter_content(chunk_size=1024), media_type=response.headers.get("Content-Type"))
    except Exception as e:
        log.error(f"Proxy error for {url}: {e}")
        return RedirectResponse(url="/static/img/placeholder.svg")

# Legacy/Helper endpoints
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/img/favicon.ico")

@app.get("/ads.txt")
async def ads_txt():
    return FileResponse("static/ads.txt")

@app.get("/manifest.json")
async def manifest():
    return FileResponse("static/manifest.json")

@app.get("/sw.js")
async def sw_js():
    return FileResponse("sw.js")

@app.get("/static/generated/{filename}")
async def get_generated_image(filename: str):
    return FileResponse(os.path.join("static", "generated", filename))

@app.get("/api/delivery/track/{event_type}")
async def track_delivery_event(event_type: str, event_id: int, redirect: str = "/briefing"):
    p = await db.async_execute_one("SELECT sync_token, delivery_kind, channel, target, cluster_id FROM delivery_tracking_events WHERE id = %s", (event_id,))
    if p:
        await db.async_execute(
            "INSERT INTO delivery_tracking_events (parent_event_id, event_type, sync_token, delivery_kind, channel, target, cluster_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (event_id, event_type, p['sync_token'], p['delivery_kind'], p['channel'], p['target'], p['cluster_id']),
            fetch=False
        )
    _public_site_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.live")
    return RedirectResponse(url=f"{_public_site_url}{redirect}", status_code=302)

# Include routers with /api prefix (for Nginx/Public)
app.include_router(news.router, prefix="/api")
app.include_router(home.router, prefix="/api")
app.include_router(intelligence.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(system.router, prefix="/api")

@app.get("/api/entity-graph/{entity_name}")
async def entity_graph_lookup(entity_name: str):
    """Fetches persistent knowledge about an entity from the local graph."""
    from database import db_manager as db
    
    row = db.execute_one("""
        SELECT bio_summary, importance_score, last_seen, category 
        FROM entity_knowledge WHERE entity_name = %s
    """, (entity_name,))
    
    if not row:
        return {"status": "not_found"}
        
    return {"status": "success", "data": row}

@app.get("/api/research/{cluster_id}")
async def cluster_research(cluster_id: str, q: str):
    """Researches a cluster based on a user query using Gemma 2."""
    from local_analyst import analyst
    from database import db_manager as db
    
    # Get cluster context
    row = db.execute_one("""
        SELECT summary, generated_article 
        FROM cluster_summaries WHERE cluster_id = %s
    """, (cluster_id,))
    
    if not row:
        raise HTTPException(status_code=404, detail="Cluster not found")
        
    context = f"{row['summary']}\n{row['generated_article']}"
    answer = analyst.research_query(q, context)
    
    return {"status": "success", "answer": answer}
