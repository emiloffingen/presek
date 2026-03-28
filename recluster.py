"""
recluster.py — One-time migration to fix the snowballed clustering in presek.db

What it does:
  1. Drops the orphaned 'article' table (leftover from old schema)
  2. Re-clusters ALL articles using the improved algorithm
     (higher threshold, cluster representatives, size cap)
  3. Prints before/after stats

Usage:
    python3 recluster.py                  # dry run (shows stats only)
    python3 recluster.py --apply          # actually writes changes

Run this ONCE after uploading the new clustering.py.
Back up presek.db first:  cp presek.db presek.db.bak
"""

import database
import sys
import math
import re
import uuid
from collections import Counter
from datetime import datetime

# ── Inline clustering logic (same as new clustering.py) ──────────

MK_SUFFIXES = [
    "увањето", "ување", "ањето", "ање", "ењето", "ење",
    "истите", "истот", "иста", "исти",
    "ските", "скиот", "ската", "ски", "ска", "ско",
    "ните", "ниот", "ната", "ното", "ни",
    "ите", "иот", "ата", "ото",
    "от", "та", "то",
]

MK_STOPWORDS = {
    "и","на","во","од","со","за","се","е","не","да","по","до","при",
    "но","или","ако","што","кој","која","кое","кои","дека","оти",
    "ги","го","им","му","ја","ми","ме","те","ве","ни","си","ке",
    "пред","под","над","зад","меѓу",
    "овој","оваа","ова","овие","тој","таа","тоа","тие",
    "еден","една","едно","нема","нови","нов","нова",
    "the","and","for","from","that","this","with","has",
}

THRESHOLD = 0.35
MAX_CLUSTER = 30
# How many recent articles to look back when clustering
LOOKBACK = 500

def mk_stem(word):
    if len(word) < 5:
        return word
    for s in MK_SUFFIXES:
        if word.endswith(s) and len(word) - len(s) >= 3:
            return word[:-len(s)]
    return word

def text_to_vector(text):
    words = re.findall(r'[а-шА-Ш\w]{3,}', text.lower())
    return Counter(mk_stem(w) for w in words if w not in MK_STOPWORDS)

def cosine(v1, v2):
    inter = set(v1) & set(v2)
    num = sum(v1[x] * v2[x] for x in inter)
    d1 = math.sqrt(sum(v**2 for v in v1.values()))
    d2 = math.sqrt(sum(v**2 for v in v2.values()))
    return num / (d1 * d2) if d1 and d2 else 0.0


def recluster(db_path, apply=False):
    conn = database.get_db()
    conn.row_factory = sqlite3.Row

    # ── Before stats ──
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    clusters_before = conn.execute("SELECT COUNT(DISTINCT cluster_id) FROM articles").fetchone()[0]
    mega = conn.execute("SELECT cluster_id, COUNT(*) as n FROM articles GROUP BY cluster_id ORDER BY n DESC LIMIT 1").fetchone()

    print(f"BEFORE: {total} articles, {clusters_before} clusters")
    print(f"  Largest cluster: {mega['cluster_id']} with {mega['n']} articles ({mega['n']*100//total}%)")
    print()

    # ── Drop orphaned table ──
    orphan = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='article'").fetchone()
    if orphan:
        if apply:
            conn.execute("DROP TABLE article")
            conn.commit()
            print("Dropped orphaned 'article' table.")
        else:
            print("Would drop orphaned 'article' table.")

    # ── Add description column if missing ──
    cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
    if "description" not in cols:
        if apply:
            conn.execute("ALTER TABLE articles ADD COLUMN description TEXT DEFAULT ''")
            conn.commit()
            print("Added 'description' column to articles table.")
        else:
            print("Would add 'description' column to articles table.")

    # ── Load all articles chronologically ──
    rows = conn.execute(
        "SELECT id, title FROM articles ORDER BY created_at ASC"
    ).fetchall()

    print(f"Re-clustering {len(rows)} articles with threshold={THRESHOLD}, max_cluster={MAX_CLUSTER}, lookback={LOOKBACK}...")

    # Process chronologically, maintaining a sliding window
    new_clusters = {}  # article_id → new_cluster_id
    # Window: list of (title, cluster_id) for recent articles
    window = []
    # Track cluster reps and sizes
    cluster_rep = {}    # cid → vector
    cluster_size = {}   # cid → count

    for i, row in enumerate(rows):
        title = row["title"] or ""
        aid = row["id"]
        vec = text_to_vector(title)

        if not vec:
            cid = str(uuid.uuid4())[:8]
            new_clusters[aid] = cid
            cluster_rep[cid] = vec
            cluster_size[cid] = 1
            window.append((title, cid))
            if len(window) > LOOKBACK:
                window.pop(0)
            continue

        # Find best matching cluster rep in the window
        # Build active reps from the window
        window_reps = {}
        window_sizes = {}
        for _, wcid in window:
            window_sizes[wcid] = window_sizes.get(wcid, 0) + 1
            if wcid not in window_reps and wcid in cluster_rep:
                window_reps[wcid] = cluster_rep[wcid]

        best_cid = None
        best_score = 0.0

        for cid, rep_vec in window_reps.items():
            if window_sizes.get(cid, 0) >= MAX_CLUSTER:
                continue
            score = cosine(vec, rep_vec)
            if score > THRESHOLD and score > best_score:
                best_score = score
                best_cid = cid

        if best_cid:
            cid = best_cid
            cluster_size[cid] = cluster_size.get(cid, 0) + 1
        else:
            cid = str(uuid.uuid4())[:8]
            cluster_rep[cid] = vec
            cluster_size[cid] = 1

        new_clusters[aid] = cid
        window.append((title, cid))
        if len(window) > LOOKBACK:
            window.pop(0)

        if (i + 1) % 1000 == 0:
            unique = len(set(new_clusters.values()))
            print(f"  Processed {i+1}/{len(rows)} — {unique} clusters so far")

    # ── After stats ──
    unique_clusters = len(set(new_clusters.values()))
    sizes = Counter(new_clusters.values())
    top5 = sizes.most_common(5)

    print()
    print(f"AFTER: {total} articles, {unique_clusters} clusters")
    print(f"  Top 5 clusters:")
    for cid, n in top5:
        # Get a sample title
        sample_id = [aid for aid, c in new_clusters.items() if c == cid][0]
        sample_title = conn.execute("SELECT title FROM articles WHERE id=%s", (sample_id,)).fetchone()["title"]
        print(f"    {cid}: {n} articles — \"{sample_title[:60]}\"")

    # Size distribution
    size_dist = Counter()
    for _, n in sizes.items():
        if n == 1: size_dist["singletons"] += 1
        elif n <= 3: size_dist["2-3"] += 1
        elif n <= 10: size_dist["4-10"] += 1
        elif n <= 30: size_dist["11-30"] += 1
        else: size_dist["30+"] += 1
    print(f"\n  Size distribution:")
    for bucket in ["singletons", "2-3", "4-10", "11-30", "30+"]:
        print(f"    {bucket}: {size_dist.get(bucket, 0)}")

    if apply:
        print("\nApplying changes...")
        conn.execute("BEGIN")
        for aid, cid in new_clusters.items():
            conn.execute("UPDATE articles SET cluster_id=%s WHERE id=%s", (cid, aid))
        conn.commit()
        print(f"Done. Updated {len(new_clusters)} articles.")
    else:
        print("\nDRY RUN — no changes written. Run with --apply to commit.")

    conn.close()


if __name__ == "__main__":
    import os
    db_path = "presek.db"

    # Check for --apply flag
    apply = "--apply" in sys.argv

    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found. Run from the app directory.")
        sys.exit(1)

    if apply:
        # Safety: check backup exists
        if not os.path.exists(db_path + ".bak"):
            print(f"Safety: creating backup → {db_path}.bak")
            import shutil
            shutil.copy2(db_path, db_path + ".bak")

    recluster(db_path, apply=apply)
