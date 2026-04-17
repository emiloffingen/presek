
import asyncio
import logging
import json
import numpy as np
from database import db_manager as db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.backfill_centroids")

def parse_vec(v):
    if isinstance(v, str):
        v = json.loads(v)
    return np.array(v, dtype=np.float32)

async def backfill():
    print("\n--- Backfilling Cluster Centroids ---")
    
    # 1. Get all clusters from cluster_summaries that don't have a centroid
    rows = db.execute("SELECT cluster_id FROM cluster_summaries WHERE centroid IS NULL")
    if not rows:
        print("All clusters already have centroids.")
        return

    print(f"Processing {len(rows)} clusters...")

    for i, row in enumerate(rows, 1):
        cid = row['cluster_id']
        # Fetch embeddings for all articles in this cluster
        arts = db.execute("SELECT embedding FROM articles WHERE cluster_id = %s AND embedding IS NOT NULL", (cid,))
        if not arts:
            continue
        
        vec_pool = [parse_vec(a['embedding']) for a in arts]
        if vec_pool:
            centroid = np.mean(vec_pool, axis=0).tolist()
            db.execute("UPDATE cluster_summaries SET centroid = %s WHERE cluster_id = %s", (centroid, cid), fetch=False)
        
        if i % 50 == 0:
            print(f" Progress: {i}/{len(rows)}")

    print("Backfill complete.")

if __name__ == "__main__":
    asyncio.run(backfill())
