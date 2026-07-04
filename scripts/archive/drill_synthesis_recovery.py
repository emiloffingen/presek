#!/usr/bin/env python3
"""Operational drill: verify synthesis recovery hooks respond."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Presek synthesis recovery drill")
    parser.add_argument("--lang", default="sr", choices=("sr", "mk"))
    parser.add_argument("--cluster-id", default="", help="Optional cluster to trace")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report: dict = {"status": "ok", "checks": []}

    try:
        import asyncio

        from core.ops_snapshot import build_ops_snapshot

        ops = asyncio.run(build_ops_snapshot())
        report["ops_status"] = ops.get("status")
        report["checks"].append({"name": "ops_snapshot", "ok": bool(ops)})
    except Exception as exc:
        report["status"] = "fail"
        report["checks"].append({"name": "ops_snapshot", "ok": False, "error": str(exc)})

    try:
        from core.synthesis_quality import list_stuck_fast_synthesis_cluster_ids

        stuck = list_stuck_fast_synthesis_cluster_ids(max_age_hours=24, limit=20)
        report["stuck_fast_count"] = len(stuck)
        report["checks"].append({"name": "stuck_fast_scan", "ok": True, "count": len(stuck)})
    except Exception as exc:
        report["status"] = "fail"
        report["checks"].append({"name": "stuck_fast_scan", "ok": False, "error": str(exc)})

    try:
        from core.copy_quality import assess_copy_purity

        sr_diag = assess_copy_purity("Vlada Srbije je usvojila izmene.", lang="sr")
        mk_diag = assess_copy_purity("Холандија и Јапонија го поделија поенот.", lang="mk")
        report["copy_gates"] = {"sr_ok": sr_diag.get("ok"), "mk_ok": mk_diag.get("ok")}
        report["checks"].append({
            "name": "copy_quality_gates",
            "ok": bool(sr_diag.get("ok")) and bool(mk_diag.get("ok")),
        })
    except Exception as exc:
        report["status"] = "fail"
        report["checks"].append({"name": "copy_quality_gates", "ok": False, "error": str(exc)})

    try:
        from core.queue_status import queue_status_payload

        queues = queue_status_payload()
        report["queue_depths"] = queues.get("depths")
        report["checks"].append({"name": "queue_status", "ok": isinstance(queues, dict)})
    except Exception as exc:
        report["status"] = "fail"
        report["checks"].append({"name": "queue_status", "ok": False, "error": str(exc)})

    if args.cluster_id:
        try:
            import asyncio

            from core.synthesis_trace import build_cluster_synthesis_trace

            trace = asyncio.run(build_cluster_synthesis_trace(args.cluster_id, lang=args.lang))
            report["trace"] = {
                "cluster_id": trace.get("cluster_id"),
                "recommended_actions": trace.get("recommended_actions"),
                "pending_fast_upgrade": trace.get("pending_fast_upgrade"),
            }
            report["checks"].append({"name": "cluster_trace", "ok": bool(trace.get("cluster_id"))})
        except Exception as exc:
            report["status"] = "fail"
            report["checks"].append({"name": "cluster_trace", "ok": False, "error": str(exc)})

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Drill status: {report['status']}")
        for check in report["checks"]:
            mark = "OK" if check.get("ok") else "FAIL"
            print(f" - [{mark}] {check['name']}")

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
