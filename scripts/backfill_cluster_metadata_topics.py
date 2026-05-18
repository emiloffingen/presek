import asyncio
import logging
import os
import sys

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import db_manager as db
from nlp.categories import detect_topic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_topics")


async def main():
    logger.info("Starting comprehensive backfill of topics...")

    # 1. Update articles first with new detect_topic logic
    logger.info("Step 1: Re-detecting topics for recent articles...")
    articles = await db.async_execute(
        """
        SELECT id, title, description
        FROM articles
        WHERE created_at >= NOW() - INTERVAL '7 days'
    """
    )

    art_count = 0
    for art in articles:
        new_topic = detect_topic(art["title"], art.get("description", ""))
        await db.async_execute(
            "UPDATE articles SET topic = %s WHERE id = %s",
            (new_topic, art["id"]),
            fetch=False,
        )
        art_count += 1
        if art_count % 1000 == 0:
            logger.info(f"Processed {art_count} articles...")

    # 2. Sync to cluster_metadata
    logger.info("Step 2: Syncing topics to cluster_metadata...")
    rows = await db.async_execute(
        """
        SELECT cluster_id, array_agg(DISTINCT topic) as topics
        FROM articles
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY cluster_id
    """
    )

    logger.info(f"Found {len(rows)} clusters to sync.")

    updated_count = 0
    for r in rows:
        cid = r["cluster_id"]
        topics = r["topics"]

        # Check if cluster_metadata exists
        meta = await db.async_execute_one("SELECT 1 FROM cluster_metadata WHERE cluster_id = %s", (cid,))

        if meta:
            await db.async_execute(
                "UPDATE cluster_metadata SET topics = %s WHERE cluster_id = %s",
                (topics, cid),
                fetch=False,
            )
            updated_count += 1
            if updated_count % 100 == 0:
                logger.info(f"Updated {updated_count} clusters...")

    logger.info(f"Finished. Updated {art_count} articles and {updated_count} clusters.")


if __name__ == "__main__":
    asyncio.run(main())
