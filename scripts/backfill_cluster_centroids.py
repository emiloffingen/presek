import numpy as np
import json
from core.database import db_manager as db
import datetime


def backfill_centroids():
    print("Backfilling centroids for recent clusters...")
    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    clusters = db.execute(
        "SELECT DISTINCT cluster_id FROM articles WHERE created_at >= %s", (cutoff,)
    )

    count = 0
    for c in clusters:
        cid = c["cluster_id"]
        arts = db.execute(
            "SELECT embedding FROM articles WHERE cluster_id = %s AND embedding IS NOT NULL",
            (cid,),
        )

        if not arts:
            continue

        def parse_vec(v):
            if isinstance(v, str):
                v = json.loads(v)
            return np.array(v, dtype=np.float32)

        vecs = [parse_vec(a["embedding"]) for a in arts]
        if vecs:
            centroid = np.mean(vecs, axis=0).tolist()
            centroid_str = (
                f"[{','.join(map(str, centroid))}]" if len(centroid) == 384 else None
            )
            db.execute(
                "INSERT INTO cluster_metadata (cluster_id, centroid, updated_at) VALUES (%s, %s, NOW()) ON CONFLICT (cluster_id) DO UPDATE SET centroid = EXCLUDED.centroid, updated_at = NOW()",
                (cid, centroid_str),
                fetch=False,
            )
            count += 1
            if count % 50 == 0:
                print(f"  Processed {count} clusters...")

    print(f"Successfully backfilled {count} centroids.")


if __name__ == "__main__":
    backfill_centroids()
