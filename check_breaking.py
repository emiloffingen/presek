
import asyncio
import database
from utils import score_cluster
from config import BREAKING_SCORE_THRESHOLD

async def main():
    # Initialize DB (if needed by your DB wrapper)
    sql = """
        SELECT m.cluster_id, 
               (SELECT title FROM articles WHERE cluster_id = m.cluster_id ORDER BY created_at DESC LIMIT 1) as title,
               (SELECT COALESCE(ingested_at, created_at) FROM articles WHERE cluster_id = m.cluster_id ORDER BY COALESCE(ingested_at, created_at) DESC LIMIT 1) as created_at
        FROM cluster_metadata m
        WHERE m.updated_at >= NOW() - INTERVAL '24 hours'
        ORDER BY m.updated_at DESC LIMIT 20
    """
    rows = await database.async_db.execute(sql)
    print(f"Threshold: {BREAKING_SCORE_THRESHOLD}")
    print("-" * 80)
    for r in rows:
        arts = await database.async_db.execute("SELECT * FROM articles WHERE cluster_id = %s", (r["cluster_id"],))
        score = score_cluster(arts)
        is_breaking = score >= BREAKING_SCORE_THRESHOLD
        marker = "[BREAKING]" if is_breaking else "          "
        print(f"{marker} Score: {score:5.2f} | {r['title']}")

if __name__ == "__main__":
    asyncio.run(main())
