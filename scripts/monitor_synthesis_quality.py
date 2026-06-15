"""Monitor synthesis provider distribution and alert on elevated fallback rates."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import db_manager as db
from core.logging_config import get_logger

log = get_logger("presek_synthesis_monitor")

_REDIS_KEY = "presek:synthesis_quality"
_ALERT_COOLDOWN_KEY = "presek:ops_alert:synthesis"
_ALERT_COOLDOWN_SECONDS = 6 * 3600
_QUEUE_WARN_DEPTH = int(os.environ.get("CELERY_QUEUE_WARN_DEPTH", "150"))
_QUEUE_CRITICAL_DEPTH = int(os.environ.get("CELERY_QUEUE_CRITICAL_DEPTH", "500"))
_FALLBACK_RATIO_WARN = 0.35
_FALLBACK_RATIO_CRITICAL = 0.55


def _parse_args():
    parser = argparse.ArgumentParser(description="Monitor cluster synthesis provider quality.")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Single-window lookback in days (legacy mode). Default: write 1d primary + 7d history snapshot.",
    )
    parser.add_argument(
        "--warn-ratio",
        type=float,
        default=_FALLBACK_RATIO_WARN,
        help="Warn when 24h fallback share exceeds this ratio.",
    )
    parser.add_argument(
        "--critical-ratio",
        type=float,
        default=_FALLBACK_RATIO_CRITICAL,
        help="Exit non-zero when 24h fallback share exceeds this ratio.",
    )
    parser.add_argument("--write-redis", action="store_true", help="Persist snapshot to Redis for /api/health.")
    parser.add_argument("--notify", action="store_true", help="Send ntfy alert on warn/critical (rate-limited).")
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
    return normalized in ("enhanced_fallback", "local")


def _celery_queue_depth(queue_name: str = "celery") -> int:
    try:
        if queue_name != "celery":
            from utils import redis_client

            return int(redis_client.llen(queue_name) or 0)

        from core.health import _probe_celery_queue

        return int(_probe_celery_queue().get("celery_depth", 0))
    except Exception as exc:
        log.warning(f"[synthesis-monitor] Failed to read queue depth: {exc}")
        return 0


def build_report(days: int):
    counts = _provider_counts(days)
    total = sum(counts.values())
    legacy_unknown_total = int(counts.get("NULL", 0))
    fallback_total = sum(count for provider, count in counts.items() if _is_fallback_provider(provider))
    fallback_ratio = (fallback_total / total) if total else 0.0

    return {
        "window_days": days,
        "total_summaries": total,
        "fallback_total": fallback_total,
        "fallback_ratio": round(fallback_ratio, 3),
        "legacy_unknown_total": legacy_unknown_total,
        "providers": counts,
        "top_fallback_reasons": _fallback_reason_counts(days),
    }


def _unsummarized_counts():
    rows = db.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE summary IS NULL) AS total,
            COUNT(*) FILTER (
                WHERE summary IS NULL
                  AND created_at >= NOW() - interval '24 hours'
            ) AS last_24h
        FROM articles
        """,
        read_only=True,
    )
    row = rows[0] if rows else {}
    return {
        "unsummarized_total": int(row.get("total") or 0),
        "unsummarized_24h": int(row.get("last_24h") or 0),
    }


def _runtime_fallback_reason_counts():
    """Today's synthesis_path Redis counters grouped by fallback reason."""
    try:
        from utils import redis_client

        bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        data = redis_client.hgetall(f"presek:runtime_events:{bucket}") or {}
        reasons = {}
        for key, value in data.items():
            field = key.decode() if isinstance(key, bytes) else str(key)
            if not field.startswith("synthesis_path|"):
                continue
            reason = "none"
            for part in field.split("|"):
                if part.startswith("reason="):
                    reason = part.split("=", 1)[1]
                    break
            reasons[reason] = reasons.get(reason, 0) + int(value)
        return dict(sorted(reasons.items(), key=lambda item: -item[1]))
    except Exception as exc:
        log.warning(f"[synthesis-monitor] Failed to read runtime fallback reasons: {exc}")
        return {}


def build_snapshot(primary_days: int = 1, history_days: int = 7):
    from core.limits import FAST_SYNTHESIS_STUCK_HOURS, LOW_SCORE_SYNTHESIS_MIN
    from core.synthesis_quality import count_low_score_syntheses, count_stuck_fast_syntheses, count_upgradeable_syntheses

    primary = build_report(primary_days)
    history = build_report(history_days)
    queue_depth = _celery_queue_depth()
    unsummarized = _unsummarized_counts()
    stuck_fast = count_stuck_fast_syntheses(FAST_SYNTHESIS_STUCK_HOURS)
    upgradeable = count_upgradeable_syntheses(days=primary_days)
    low_score_count = count_low_score_syntheses(min_score=LOW_SCORE_SYNTHESIS_MIN, days=primary_days)
    runtime_fallback_reasons = _runtime_fallback_reason_counts()

    status = "ok"
    if (
        primary["fallback_ratio"] >= _FALLBACK_RATIO_CRITICAL
        or queue_depth >= _QUEUE_CRITICAL_DEPTH
        or stuck_fast > 0
    ):
        status = "critical"
    elif (
        primary["fallback_ratio"] >= _FALLBACK_RATIO_WARN
        or queue_depth >= _QUEUE_WARN_DEPTH
    ):
        status = "warn"

    return {
        "status": status,
        "primary": primary,
        "history": history,
        "celery_queue_depth": queue_depth,
        "celery_queue_warn_depth": _QUEUE_WARN_DEPTH,
        "celery_queue_critical_depth": _QUEUE_CRITICAL_DEPTH,
        "unsummarized_total": unsummarized["unsummarized_total"],
        "unsummarized_24h": unsummarized["unsummarized_24h"],
        "stuck_fast_synthesis_count": stuck_fast,
        "stuck_fast_synthesis_hours": FAST_SYNTHESIS_STUCK_HOURS,
        "provisional_count_24h": upgradeable["provisional_count"],
        "fallback_count_24h": upgradeable["fallback_count"],
        "low_score_count_24h": low_score_count,
        "runtime_fallback_reasons_24h": runtime_fallback_reasons,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_redis(snapshot: dict):
    try:
        from utils import redis_client

        redis_client.setex(_REDIS_KEY, 3600 * 6, json.dumps(snapshot))
    except Exception as exc:
        log.warning(f"[synthesis-monitor] Failed to write Redis snapshot: {exc}")


def _alert_cooldown_active() -> bool:
    try:
        from utils import redis_client

        return bool(redis_client.get(_ALERT_COOLDOWN_KEY))
    except Exception:
        return False


def _mark_alert_sent():
    try:
        from utils import redis_client

        redis_client.setex(_ALERT_COOLDOWN_KEY, _ALERT_COOLDOWN_SECONDS, "1")
    except Exception as exc:
        log.warning(f"[synthesis-monitor] Failed to set alert cooldown: {exc}")


def _send_ops_alert(snapshot: dict, exit_code: int):
    if exit_code == 0 or _alert_cooldown_active():
        return

    from core.config import NTFY_TOPIC
    from tasks.delivery.core import _send_ntfy_message

    primary = snapshot["primary"]
    lines = [
        f"status={snapshot['status']}",
        f"24h fallback={primary['fallback_ratio'] * 100:.1f}% ({primary['fallback_total']}/{primary['total_summaries']})",
        f"celery queue={snapshot['celery_queue_depth']}",
    ]
    if primary.get("top_fallback_reasons"):
        top_reason = next(iter(primary["top_fallback_reasons"]))
        lines.append(f"top reason={top_reason}")

    priority_tag = "warning" if exit_code == 1 else "rotating_light"
    title = "Presek synthesis ops alert"
    if _send_ntfy_message(NTFY_TOPIC, title, "\n".join(lines), tags=f"robot,{priority_tag}"):
        _mark_alert_sent()
        log.info("[synthesis-monitor] Ops alert sent via ntfy")
    else:
        log.warning("[synthesis-monitor] Ops alert not sent (ntfy unavailable)")


def evaluate_report(report: dict, warn_ratio: float, critical_ratio: float):
    ratio = report["fallback_ratio"]
    total = report["total_summaries"]

    log.info(
        "[synthesis-monitor] %sd window: %s summaries, fallback ratio %.1f%% (%s/%s), legacy unknown %s",
        report["window_days"],
        total,
        ratio * 100,
        report["fallback_total"],
        total,
        report.get("legacy_unknown_total", 0),
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


def evaluate_snapshot(snapshot: dict, warn_ratio: float, critical_ratio: float):
    exit_code = evaluate_report(snapshot["primary"], warn_ratio, critical_ratio)

    queue_depth = snapshot["celery_queue_depth"]
    log.info("[synthesis-monitor] celery queue depth: %s", queue_depth)
    if queue_depth >= _QUEUE_CRITICAL_DEPTH:
        log.error(
            "[synthesis-monitor] CRITICAL celery queue depth %s exceeds %s",
            queue_depth,
            _QUEUE_CRITICAL_DEPTH,
        )
        exit_code = max(exit_code, 2)
    elif queue_depth >= _QUEUE_WARN_DEPTH:
        log.warning(
            "[synthesis-monitor] Elevated celery queue depth %s exceeds warn threshold %s",
            queue_depth,
            _QUEUE_WARN_DEPTH,
        )
        exit_code = max(exit_code, 1)

    return exit_code


def main():
    args = _parse_args()
    if args.days is not None:
        report = build_report(args.days)
        if args.write_redis:
            _write_redis(report)
        raise SystemExit(evaluate_report(report, args.warn_ratio, args.critical_ratio))

    snapshot = build_snapshot()
    if args.write_redis:
        _write_redis(snapshot)

    exit_code = evaluate_snapshot(snapshot, args.warn_ratio, args.critical_ratio)
    if args.notify:
        _send_ops_alert(snapshot, exit_code)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
