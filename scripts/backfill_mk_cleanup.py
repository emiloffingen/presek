#!/usr/bin/env python3
"""One-off backfill: repair non-Macedonian leaks in already-published
cluster_summaries. Dry-run by default; pass --apply to write. Run from the
repo root with PYTHONPATH set and DATABASE_URL in the environment:

    set -a; . ./.env; set +a
    PYTHONPATH=. .venv/bin/python scripts/backfill_mk_cleanup.py [--apply]
"""

import os
import sys

import psycopg

from tasks.intelligence.synthesis_mk_cleanup import repair_foreign_leaks as repair

APPLY = "--apply" in sys.argv
FIELDS = [
    "summary",
    "synthetic_headline",
    "synthetic_standfirst",
    "storyline_narrative",
    "quote",
    "generated_article",
]

url = os.environ["DATABASE_URL"]
per_field = {f: 0 for f in FIELDS}
changed_rows = 0
examples = []

with psycopg.connect(url, connect_timeout=15) as c:
    rows = c.execute("SELECT cluster_id, " + ", ".join(FIELDS) + " FROM cluster_summaries").fetchall()
    for row in rows:
        cid = row[0]
        vals = row[1:]
        updates = {}
        for f, v in zip(FIELDS, vals):
            if not v:
                continue
            nv = repair(v)
            if nv != v:
                updates[f] = nv
                per_field[f] += 1
        if not updates:
            continue
        changed_rows += 1
        if len(examples) < 25:
            f0 = next(iter(updates))
            examples.append((cid, f0, vals[FIELDS.index(f0)], updates[f0]))
        if APPLY:
            setclause = ", ".join(f"{f}=%s" for f in updates)
            c.execute(
                f"UPDATE cluster_summaries SET {setclause} WHERE cluster_id=%s",
                (*updates.values(), cid),
            )
    if APPLY:
        c.commit()

print(f"{'APPLIED' if APPLY else 'DRY-RUN'}: rows to change: {changed_rows} / {len(rows)}")
print("per field:", per_field)
print("\n--- examples (before -> after) ---")
for cid, f, before, after in examples:
    print(f"\n[{cid}] {f}")
    print("  BEFORE:", (before or "")[:220].replace("\n", " "))
    print("  AFTER :", (after or "")[:220].replace("\n", " "))
