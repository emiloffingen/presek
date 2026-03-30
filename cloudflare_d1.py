import json
import logging
import urllib.request
import urllib.error
from config import CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, CLOUDFLARE_D1_DATABASE_ID

log = logging.getLogger("presek.d1")

BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/d1/database/{CLOUDFLARE_D1_DATABASE_ID}/query"

def query_d1(sql: str, params: list = None):
    """Execute a query on Cloudflare D1."""
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_D1_DATABASE_ID:
        return None
        
    payload = {
        "sql": sql,
        "params": params or []
    }
    
    try:
        req = urllib.request.Request(
            BASE_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("success"):
                log.warning(f"[d1] API error: {data.get('errors')}")
            return data.get("result")
    except Exception as e:
        log.warning(f"[d1] Query failed: {e}")
        return None

def sync_clusters_to_d1(clusters_data: list):
    """
    Sync top clusters to D1 for edge delivery.
    Expects a list of dicts from the news API.
    """
    if not clusters_data:
        return
        
    # 1. Clear old top news
    query_d1("DELETE FROM top_news;")
    
    # 2. Insert new clusters as JSON for simplicity at the edge
    sql = "INSERT INTO top_news (cluster_id, data, updated_at) VALUES (?, ?, ?);"
    
    now = datetime.datetime.now().isoformat()
    for cluster in clusters_data:
        query_d1(sql, [
            cluster["cluster_id"], 
            json.dumps(cluster),
            now
        ])
    
    log.info(f"[d1] Synced {len(clusters_data)} clusters to edge.")

import datetime
