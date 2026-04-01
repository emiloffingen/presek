import logging
import json
import os
import datetime
from database import get_db
from ai_engine import _call_ai
from prompts import ENTITY_EXTRACTION_PROMPT

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek")

conn = get_db()
cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
rows = conn.execute("""
    SELECT DISTINCT ON (cluster_id) cluster_id, title, description 
    FROM articles a
    WHERE created_at >= %s 
      AND NOT EXISTS (SELECT 1 FROM cluster_entities e WHERE e.cluster_id = a.cluster_id)
    LIMIT 20
""", (cutoff,)).fetchall()
conn.close()

print(f"Found {len(rows)} clusters to test.")

for r in rows:
    print(f"Testing cluster: {r['cluster_id']} | Title: {r['title'][:50]}...")
    text = f"Title: {r['title']}\nDescription: {r['description']}"
    res, tier = _call_ai(text, ENTITY_EXTRACTION_PROMPT, max_tokens=500, json_mode=True)
    print(f"Tier: {tier} | Result len: {len(res) if res else 0}")
