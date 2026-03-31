#!/usr/bin/env python3
"""
One-time script to backfill embeddings for existing articles.
Run: python backfill_embeddings.py

Processes articles in batches, newest first. Safe to re-run
(skips articles that already have embeddings).
"""
import time
import sys
from database import get_db, init_db
from embeddings import generate_embeddings_batch, BATCH_SIZE

BATCH = 50  # articles per API call (stay under rate limits)


def backfill():
    init_db()
    conn = get_db()

    # Count articles needing embeddings
    total = conn.execute("SELECT COUNT(*) FROM articles WHERE embedding IS NULL").fetchone()[0]
    print(f"Articles without embeddings: {total}")

    if total == 0:
        print("Nothing to do.")
        conn.close()
        return

    processed = 0
    errors = 0

    while True:
        rows = conn.execute("""
            SELECT id, title, description
            FROM articles
            WHERE embedding IS NULL
            ORDER BY created_at DESC
            LIMIT %s
        """, (BATCH,)).fetchall()

        if not rows:
            break

        texts = []
        for r in rows:
            text = r['title'] or ''
            desc = r['description'] or ''
            if desc:
                text += ' ' + desc[:500]
            texts.append(text)

        embeddings = generate_embeddings_batch(texts)

        count = 0
        for r, emb in zip(rows, embeddings):
            if emb is not None:
                conn.execute(
                    "UPDATE articles SET embedding = %s WHERE id = %s",
                    (str(emb), r['id'])
                )
                count += 1
            else:
                errors += 1

        conn.commit()
        processed += count
        print(f"  Embedded {processed}/{total} articles ({errors} errors)", end='\r')

        # Rate limit: ~1 batch per second
        time.sleep(1)

    print(f"\nDone. Embedded {processed} articles ({errors} errors).")
    conn.close()


if __name__ == "__main__":
    backfill()
