import asyncio
import logging
from core.database import db_manager as db
import numpy as np

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.historical_prototype")


async def run_historical_prototype(limit=3):
    print("\n--- Presek Semantic Historical Linking Prototype ---")
    print("Goal: Link current stories to related events from the 60-day archive.\n")

    # 1. Get a recent 'major' cluster (with 5+ sources) to test
    target_clusters = db.execute(
        """
        SELECT cluster_id, COUNT(*) as source_count, MIN(title) as sample_title
        FROM articles 
        WHERE created_at >= NOW() - INTERVAL '24 hours'
        GROUP BY cluster_id 
        HAVING COUNT(*) >= 5
        ORDER BY source_count DESC 
        LIMIT %s
    """,
        (limit,),
    )

    for c in target_clusters:
        cid = c["cluster_id"]
        print(f"\n[CURRENT STORY] {c['sample_title'][:80]}...")

        # 2. Get the average embedding for this cluster
        vec_rows = db.execute(
            "SELECT embedding FROM articles WHERE cluster_id = %s AND embedding IS NOT NULL",
            (cid,),
        )
        if not vec_rows:
            continue

        # Ensure we have floats, db returns them as strings or lists
        def parse_vec(v):
            if isinstance(v, str):
                import json

                v = json.loads(v)
            return np.array(v, dtype=np.float32)

        vecs = [parse_vec(r["embedding"]) for r in vec_rows]
        avg_vec = np.mean(vecs, axis=0).tolist()

        # 3. Search the ARCHIVE (last 60 days) for similar clusters
        # We look for clusters that are OLDER than 48 hours to ensure they are 'historical'
        archive_results = db.execute(
            """
            WITH archive_pool AS (
                SELECT cluster_id, title, created_at,
                       (1 - (embedding <=> %s::vector)) as similarity
                FROM articles
                WHERE cluster_id != %s
                  AND created_at < NOW() - INTERVAL '48 hours'
                  AND embedding IS NOT NULL
            )
            SELECT DISTINCT ON (cluster_id) 
                   cluster_id, title, created_at, similarity
            FROM archive_pool
            WHERE similarity > 0.65
            ORDER BY cluster_id, similarity DESC, created_at DESC
            LIMIT 5
        """,
            (avg_vec, cid),
        )

        if not archive_results:
            print("  ⚪ No related historical events found in the 60-day archive.")
        else:
            print(f"  🔍 Found {len(archive_results)} related historical events:")
            # Sort by similarity for display
            archive_results.sort(key=lambda x: x["similarity"], reverse=True)
            for res in archive_results:
                date_str = res["created_at"].strftime("%d.%m.%Y")
                print(
                    f"    - [{date_str}] (Sim: {res['similarity']:.4f}) {res['title'][:70]}..."
                )

        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(run_historical_prototype())
