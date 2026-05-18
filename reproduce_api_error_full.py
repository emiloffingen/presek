import asyncio
import datetime
import json
import os

from core.database import db_manager as db


async def test():
    try:
        lang = "sr"
        print(f"Fetching briefing for {lang}...")
        row = await db.async_execute_one(
            "SELECT * FROM daily_briefings WHERE lang = %s ORDER BY date DESC LIMIT 1", (lang,)
        )
        if not row:
            print("No row found")
            return

        target_date = row["date"]
        print(f"Target Date: {target_date}")

        print("Fetching subjects...")
        subjects = await db.async_execute(
            """
            SELECT name, total_mentions
            FROM knowledge_entities
            WHERE type = 'PERSON' AND last_seen >= %s::date - INTERVAL '24 hours'
              AND last_seen <= %s::date + INTERVAL '23 hours 59 minutes'
            ORDER BY total_mentions DESC LIMIT 6
        """,
            (target_date, target_date),
        )

        print("Fetching locations...")
        locations = await db.async_execute(
            """
            SELECT name, total_mentions
            FROM knowledge_entities
            WHERE type = 'GPE' AND last_seen >= %s::date - INTERVAL '24 hours'
              AND last_seen <= %s::date + INTERVAL '23 hours 59 minutes'
            ORDER BY total_mentions DESC LIMIT 8
        """,
            (target_date, target_date),
        )

        print("Fetching historical...")
        historical = await db.async_execute("SELECT date::text as day FROM daily_briefings ORDER BY date DESC LIMIT 14")

        print("Fetching lead cluster...")
        # Note: If this fails, it's likely due to missing columns or tables
        lead_cluster = await db.async_execute_one(
            """
            SELECT s.cluster_id, s.synthetic_headline, m.representative_image
            FROM cluster_summaries s
            JOIN cluster_metadata m ON s.cluster_id = m.cluster_id
            JOIN articles a ON s.cluster_id = a.cluster_id
            WHERE a.created_at >= %s::date AND a.created_at < %s::date + INTERVAL '1 day'
            GROUP BY s.cluster_id, s.synthetic_headline, m.representative_image, s.pluralism_score
            ORDER BY s.pluralism_score DESC, COUNT(a.id) DESC
            LIMIT 1
        """,
            (target_date, target_date),
        )

        print("Fetching stats...")
        stats_res = await db.async_execute_one(
            """
            SELECT
                COUNT(*) as total_articles,
                COUNT(DISTINCT source) as total_sources
            FROM articles
            WHERE created_at >= %s::date AND created_at < %s::date + INTERVAL '1 day'
        """,
            (target_date, target_date),
        )

        print("Building final response...")
        res = {
            "status": "success",
            "date": str(target_date),
            "content": row["content"],
            "metadata": row.get("metadata") or {},
            "subjects": subjects,
            "locations": locations,
            "historical_dates": historical,
            "lead_cluster": lead_cluster,
            "day_stats": stats_res,
        }
        print("Success!")

    except Exception as e:
        print(f"FAILED with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())
