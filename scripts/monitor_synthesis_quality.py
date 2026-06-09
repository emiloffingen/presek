"""Monitor synthesis provider distribution and alert on elevated fallback rates."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import db_manager as db
from core.logging_config import get_logger

log = get_logger("presek_synthesis_monitor")

_REDIS_KEY = "presek:synthesis_quality"
_DEFAULT_FALLBACK_PROVIDERS = ("enhanced_fallback", "local", "", None)
_FALLBACK_RATIO_WARN = 0.35
_FALLBACK_RATIO_CRITICAL = 0.55


def _parse_args():
    parser = argparse.ArgumentParser(description="Monitor cluster synthesis provider quality.")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7).")
    parser.add_argument(
        "--warn-ratio",
        type=float,
        default=_FALLBACK_RATIO_WARN,
        help="Warn when fallback share exceeds this ratio.",
    )
    parser.add_argument(
        "--critical-ratio",
        type=float,
        default=_FALLBACK_RATIO_CRITICAL,
        help="Exit non-zero when fallback share exceeds this ratio.",
    )
    parser.add_argument("--write-redis", action="store_true", help="Persist snapshot to Redis for /api/health.")
    return parser.parse_args()


def _provider_counts(days: int):
    rows = db.execute(
        """
        SELECT COALESCE(NULLIF(generation_provider, ''), 'NULL') AS provider,
               COUNT(*) AS count
        FROM cluster_summaries
        WHERE created_at >= NOW() - make_interval(days => %s)
        GROUP BY 1
        ORDER BY count DESC
        """,
        (days,),
        read_only=True,
    )
    return {row["provider"]: int(row["count"]) for row in rows}


def _fallback_reason_counts(days: int, limit: int = 8):
    rows = db.execute(
        """
        SELECT COALESCE(NULLIF(fallback_reason, ''), 'none') AS reason,
               COUNT(*) AS count
        FROM cluster_summaries
        WHERE created_at >= NOW() - make_interval(days => %s)
          AND generation_provider IN ('enhanced_fallback', 'local')
        GROUP BY 1
        ORDER BY count DESC
        LIMIT %s
        """,
        (days, limit),
        read_only=True,
    )
    return {row["reason"]: int(row["count"]) for row in rows}


def _is_fallback_provider(provider: str) -> bool:
    normalized = (provider or "").strip().lower()
    return normalized in ("enhanced_fallback", "local", "null", "")


def build_report(days: int):
    counts = _provider_counts(days)
    total = sum(counts.values())
    fallback_total = sum(count for provider, count in counts.items() if _is_fallback_provider(provider))
    fallback_ratio = (fallback_total / total) if total else 0.0

    return {
        "window_days": days,
        "total_summaries": total,
        "fallback_total": fallback_total,
        "fallback_ratio": round(fallback_ratio, 3),
        "providers": counts,
        "top_fallback_reasons": _fallback_reason_counts(days),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_redis(report: dict):
    try:
        from utils import redis_client

        redis_client.setex(_REDIS_KEY, 3600 * 6, json.dumps(report))
    except Exception as exc:
        log.warning(f"[synthesis-monitor] Failed to write Redis snapshot: {exc}")


def evaluate_report(report: dict, warn_ratio: float, critical_ratio: float):
    ratio = report["fallback_ratio"]
    total = report["total_summaries"]

    log.info(
        "[synthesis-monitor] %sd window: %s summaries, fallback ratio %.1f%% (%s/%s)",
        report["window_days"],
        total,
        ratio * 100,
        report["fallback_total"],
        total,
    )
    for provider, count in report["providers"].items():
        log.info("[synthesis-monitor] provider %-20s %s", provider, count)

    if report["top_fallback_reasons"]:
        log.info("[synthesis-monitor] top fallback reasons: %s", report["top_fallback_reasons"])

    if total == 0:
        log.warning("[synthesis-monitor] No summaries in lookback window.")
        return 0

    if ratio >= critical_ratio:
        log.error(
            "[synthesis-monitor] CRITICAL fallback ratio %.1f%% exceeds %.1f%%",
            ratio * 100,
            critical_ratio * 100,
        )
        return 2

    if ratio >= warn_ratio:
        log.warning(
            "[synthesis-monitor] Elevated fallback ratio %.1f%% exceeds warn threshold %.1f%%",
            ratio * 100,
            warn_ratio * 100,
        )
        return 1

    log.info("[synthesis-monitor] Synthesis quality within expected bounds.")
    return 0


def main():
    args = _parse_args()
    report = build_report(args.days)
    if args.write_redis:
        _write_redis(report)
    raise SystemExit(evaluate_report(report, args.warn_ratio, args.critical_ratio))


if __name__ == "__main__":
    main()
