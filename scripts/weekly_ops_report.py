#!/usr/bin/env python3
"""Write weekly editorial ops quality report to shared logs."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.logging_config import get_logger
from core.ops_report import build_weekly_ops_report

log = get_logger("presek_weekly_ops")


async def main():
    report = await build_weekly_ops_report()
    app_root = Path(os.environ.get("APP_ROOT", Path.home() / "presek-runtime"))
    out_dir = app_root / "shared" / "logs" / "ops_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = out_dir / f"weekly_ops_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("[weekly-ops] wrote %s", out_path)
    print(out_path)


if __name__ == "__main__":
    asyncio.run(main())
