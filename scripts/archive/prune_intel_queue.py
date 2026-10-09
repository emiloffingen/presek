#!/usr/bin/env python3
"""Drop deferrable intel-heavy Celery tasks and prioritize summarize batches."""

import argparse
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tasks.utils import reprioritize_intel_queue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold", type=int, default=int(os.environ.get("INTEL_QUEUE_SECONDARY_DEFER_LIMIT", "150"))
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = reprioritize_intel_queue(defer_threshold=args.threshold, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not result.get("skipped") or result.get("reason") == "below_threshold" else 0


if __name__ == "__main__":
    raise SystemExit(main())
