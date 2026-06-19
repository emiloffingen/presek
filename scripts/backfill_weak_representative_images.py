#!/usr/bin/env python3
"""Backfill weak or broken cluster representative images."""

from __future__ import annotations

import argparse
import logging
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.database import db_manager as db
from nlp.image_quality import classify_image_url
from tasks.maintenance import repair_cluster_representative_images
from tasks.utils import invalidate_public_data_caches

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("backfill_weak_representative_images")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90, help="Look back window for active clusters")
    parser.add_argument("--limit", type=int, default=2000, help="Maximum clusters to scan")
    parser.add_argument(
        "--skip-reachability",
        action="store_true",
        help="Only replace weak URL patterns, skip HTTP reachability checks",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing to DB")
    args = parser.parse_args()

    rows = db.execute(
        """
        SELECT cm.cluster_id, cm.representative_image
        FROM cluster_metadata cm
        JOIN cluster_summaries cs ON cs.cluster_id = cm.cluster_id
        WHERE cm.representative_image IS NOT NULL
          AND cm.updated_at >= NOW() - (%s || ' days')::interval
        ORDER BY cm.updated_at DESC
        LIMIT %s
    """,
        (int(args.days), int(args.limit)),
    )

    if not rows:
        log.info("No clusters found in the requested window.")
        return 0

    weak_rows = [
        row
        for row in rows
        if classify_image_url(row.get("representative_image"))[0] != "ok"
    ]
    log.info("Scanned %s clusters, found %s with weak representative images", len(rows), len(weak_rows))

    if not weak_rows:
        return 0

    stats = repair_cluster_representative_images(
        weak_rows,
        check_reachability=not args.skip_reachability,
        dry_run=args.dry_run,
    )
    log.info(
        "Done: checked=%s replaced=%s cleared=%s unchanged=%s skipped=%s dry_run=%s",
        stats["checked"],
        stats["replaced"],
        stats["cleared"],
        stats["unchanged"],
        stats["skipped"],
        args.dry_run,
    )

    if not args.dry_run and (stats["replaced"] or stats["cleared"]):
        invalidate_public_data_caches()
        log.info("Public caches invalidated")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
