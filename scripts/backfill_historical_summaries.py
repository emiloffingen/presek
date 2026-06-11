#!/usr/bin/env python3
"""Enqueue Gemma-only historical article summary backfill."""

import argparse
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tasks.intelligence import backfill_historical_article_summaries_task


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Article count to enqueue (default: adaptive headroom sizing).",
    )
    parser.add_argument("--reset-cursor", action="store_true")
    args = parser.parse_args()

    if args.reset_cursor:
        from tasks.utils import redis_client
        from tasks.intelligence import _HISTORICAL_SUMMARY_CURSOR_KEY

        redis_client.delete(_HISTORICAL_SUMMARY_CURSOR_KEY)
        print(json.dumps({"reset_cursor": True}, indent=2))

    result = backfill_historical_article_summaries_task(limit=args.limit)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
