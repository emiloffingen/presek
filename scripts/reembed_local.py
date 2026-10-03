#!/usr/bin/env python
"""One-off migration of article/cluster vectors from Jina to the local e5 model.

Vectors from different models are not comparable, so the swap is staged in shadow
columns while the app keeps running, then flipped in one short transaction:

    prepare   add articles.embedding_local / cluster_metadata.centroid_local
              (+ *_jina backup columns for rollback)
    embed     fill articles.embedding_local in batches (resumable, run it again
              right before cutover to catch rows added since)
    centroids cluster_metadata.centroid_local = mean of the cluster's new vectors
    status    progress counts
    cutover   swap in one transaction, keeping the old vectors in *_jina
    rollback  swap the Jina vectors back

Run from the repo root with the env loaded: PYTHONPATH=. python scripts/reembed_local.py embed
"""

import sys
import time

from core.database import db_manager as db
from core.embeddings import article_text, generate_embeddings_batch

BATCH = 64


def prepare():
    for sql in (
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding_local vector(384)",
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding_jina vector(384)",
        "ALTER TABLE cluster_metadata ADD COLUMN IF NOT EXISTS centroid_local vector(384)",
        "ALTER TABLE cluster_metadata ADD COLUMN IF NOT EXISTS centroid_jina vector(384)",
    ):
        db.execute(sql, fetch=False)
    print("columns ready")


def embed():
    done = 0
    started = time.time()
    while True:
        rows = db.execute(
            "SELECT id, title, description FROM articles WHERE embedding_local IS NULL ORDER BY id DESC LIMIT %s",
            (BATCH,),
            read_only=False,
        )
        if not rows:
            break
        vecs = generate_embeddings_batch([article_text(r["title"], r.get("description")) for r in rows])
        pairs = [("[" + ",".join(map(str, v)) + "]", r["id"]) for r, v in zip(rows, vecs) if v]
        if not pairs:
            print("model returned no vectors; aborting")
            sys.exit(1)
        db.executemany("UPDATE articles SET embedding_local = %s::vector WHERE id = %s", pairs)
        done += len(pairs)
        rate = done / max(time.time() - started, 1e-6)
        print(f"embedded {done} ({rate:.1f}/s)", flush=True)
    print("embed complete")


def centroids():
    db.execute(
        """UPDATE cluster_metadata m SET centroid_local = s.c
           FROM (SELECT cluster_id, avg(embedding_local) AS c FROM articles
                 WHERE embedding_local IS NOT NULL AND cluster_id IS NOT NULL GROUP BY cluster_id) s
           WHERE s.cluster_id = m.cluster_id""",
        fetch=False,
    )
    print("centroids computed")


def status():
    row = db.execute(
        """SELECT count(*) AS total, count(embedding) AS jina, count(embedding_local) AS local,
                  count(*) FILTER (WHERE embedding_local IS NULL) AS todo FROM articles"""
    )[0]
    cm = db.execute(
        "SELECT count(*) AS total, count(centroid) AS jina, count(centroid_local) AS local FROM cluster_metadata"
    )[0]
    print("articles", dict(row))
    print("clusters", dict(cm))


def cutover():
    with db.connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE articles SET embedding_jina = embedding, embedding = embedding_local")
        cur.execute("UPDATE cluster_metadata SET centroid_jina = centroid, centroid = centroid_local")
        conn.commit()
    print("cutover done (old vectors kept in embedding_jina / centroid_jina)")


def rollback():
    with db.connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE articles SET embedding = embedding_jina WHERE embedding_jina IS NOT NULL")
        cur.execute("UPDATE cluster_metadata SET centroid = centroid_jina WHERE centroid_jina IS NOT NULL")
        conn.commit()
    print("rolled back to Jina vectors")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {
        "prepare": prepare,
        "embed": embed,
        "centroids": centroids,
        "status": status,
        "cutover": cutover,
        "rollback": rollback,
    }[cmd]()
