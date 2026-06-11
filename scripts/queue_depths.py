#!/usr/bin/env python3
"""Print Celery queue depths as JSON or plain text (for baseline/cron scripts)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.queue_status import queue_status_payload


def main() -> int:
    payload = queue_status_payload()
    if "--json" in sys.argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        depths = payload.get("depths") or {}
        print(f"intel_status={payload.get('intel_status')} intel_heavy={payload.get('intel_heavy_depth')}")
        for name, depth in sorted(depths.items()):
            print(f"{name}={depth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
