"""Backfill articles.full_content for MK articles using the crawler.

Bounded and rate-limited: enqueues crawl_article_task for articles that are
missing a body and whose source allows full-text display.
"""

import argparse
import sys
import time
from pathlib import Path

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import MK_ONLY
from core.database import db_manager as db


def _parse_args():
    parser = argparse.ArgumentParser(description="Backfill articles.full_content (MK, opt-in sources).")
    parser.add_argument("--days", type=int, default=30, help="Only articles newer than N days (default 30).")
    parser.add_argument("--limit", type=int, default=200, help="Max articles to enqueue (default 200).")
    parser.add_argument("--batch", type=int, default=25, help="Enqueue N then sleep (default 25).")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds to sleep between batches (default 1.0).")
    parser.add_argument("--dry-run", action="store_true", help="List candidates without enqueuing.")
    return parser.parse_args()


def main():
    args = _parse_args()
    country_clause = " AND a.country = 'MK'" if MK_ONLY else ""
    rows = (
        db.execute(
            f"""
            SELECT a.id, a.link
            FROM articles a
            JOIN sources s ON a.source = s.name
            WHERE a.full_content IS NULL
              AND s.full_text_allowed = TRUE
              AND a.created_at >= NOW() - make_interval(days => %s)
              {country_clause}
            ORDER BY a.created_at DESC
            LIMIT %s
            """,  # nosec B608 - static clauses with bound params
            (args.days, args.limit),
            read_only=True,
        )
        or []
    )

    print(f"candidates: {len(rows)}")
    if args.dry_run or not rows:
        for row in rows[:20]:
            print(row["id"], row["link"])
        return

    from tasks.ingestion_task import crawl_article_task

    enqueued = 0
    for i, row in enumerate(rows, start=1):
        crawl_article_task.delay(int(row["id"]), row["link"])
        enqueued += 1
        if i % max(1, args.batch) == 0:
            time.sleep(args.sleep)
    print(f"enqueued: {enqueued}")


if __name__ == "__main__":
    main()
