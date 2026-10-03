"""Brokerless full-content backfill for offloading to CI.

Fetches articles that are missing ``full_content`` and whose source allows
full-text display, extracts the body with the crawler, and writes it straight
back to the database.

Unlike ``scripts/backfill_fulltext.py`` this does not use Celery or Redis, so it
can run from a GitHub Actions runner (or any host that can reach the primary
database). Image processing and cache invalidation are intentionally skipped:
both are Celery/Redis-bound post-crawl steps, and the stale caches expire on
their own.
"""

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import FULLTEXT_ENABLED, FULLTEXT_MAX_CHARS, MK_ONLY
from core.crawler import crawler
from core.database import db_manager as db
from core.text_extraction import clean_extracted_article_text


def _parse_args():
    parser = argparse.ArgumentParser(description="Backfill articles.full_content without Celery (CI-offloadable).")
    parser.add_argument("--days", type=int, default=30, help="Only articles newer than N days (default 30).")
    parser.add_argument("--limit", type=int, default=200, help="Max articles to process (default 200).")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent crawls (default 4).")
    parser.add_argument("--dry-run", action="store_true", help="List candidates without crawling.")
    return parser.parse_args()


def _candidates(days, limit):
    country_clause = " AND a.country = 'MK'" if MK_ONLY else ""
    return (
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
            """,  # nosec B608 - static clause with bound params
            (days, limit),
            read_only=True,
        )
        or []
    )


def _persist(article_id, result):
    updates = []
    params = []
    if result.get("image_url"):
        updates.append("image_url = %s")
        params.append(result["image_url"])
    if FULLTEXT_ENABLED and result.get("content"):
        body = clean_extracted_article_text(str(result["content"])).strip()
        if len(body) > FULLTEXT_MAX_CHARS:
            body = body[:FULLTEXT_MAX_CHARS]
        if body:
            updates.append("full_content = %s")
            params.append(body)
    if not updates:
        return False
    params.append(article_id)
    sql = f"UPDATE articles SET {', '.join(updates)} WHERE id = %s AND full_content IS NULL"  # nosec B608 - allowlisted columns with bound params
    db.execute(sql, tuple(params), fetch=False)
    return True


async def _crawl_all(rows, concurrency):
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def crawl_one(row):
        async with semaphore:
            try:
                return row, await crawler.extract_all(row["link"])
            except Exception as exc:
                return row, {"error": str(exc)}

    return await asyncio.gather(*(crawl_one(row) for row in rows))


def _close_pools():
    for attr in ("_pool", "_read_pool"):
        pool = getattr(db, attr, None)
        if pool is not None:
            try:
                pool.close()
            except Exception:
                pass


def _run(args):
    if not FULLTEXT_ENABLED:
        print("FULLTEXT_ENABLED is false; nothing to do")
        return

    rows = _candidates(args.days, args.limit)
    print(f"candidates: {len(rows)}")
    if args.dry_run or not rows:
        for row in rows[:20]:
            print(row["id"], row["link"])
        return

    results = asyncio.run(_crawl_all(rows, args.concurrency))
    updated = 0
    failed = 0
    for row, result in results:
        if result.get("error"):
            failed += 1
            print(f"skip {row['id']}: {result['error']}")
            continue
        if _persist(int(row["id"]), result):
            updated += 1
    print(f"processed {len(rows)}: updated {updated}, failed {failed}")
    if failed == len(rows):
        raise SystemExit(1)


def main():
    args = _parse_args()
    try:
        _run(args)
    finally:
        _close_pools()


if __name__ == "__main__":
    main()
