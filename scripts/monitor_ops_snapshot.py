#!/usr/bin/env python3
"""Alert on editorial ops snapshot warnings via ntfy (rate-limited)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.logging_config import get_logger
from core.ops_snapshot import build_ops_snapshot

log = get_logger("presek_ops_monitor")

_REDIS_KEY = "presek:ops_snapshot"
_ALERT_COOLDOWN_KEY = "presek:ops_alert:cockpit"
_ALERT_COOLDOWN_SECONDS = 30 * 60


def _parse_args():
    parser = argparse.ArgumentParser(description="Monitor editorial ops cockpit alerts.")
    parser.add_argument("--write-redis", action="store_true", help="Persist ops snapshot to Redis.")
    parser.add_argument("--notify", action="store_true", help="Send ntfy alert on warn/critical.")
    return parser.parse_args()


def _write_redis(snapshot: dict):
    try:
        from utils import redis_client

        redis_client.set(_REDIS_KEY, json.dumps(snapshot), ex=3600)
    except Exception as exc:
        log.warning(f"[ops-monitor] Redis write failed: {exc}")


def _cooldown_active() -> bool:
    try:
        from utils import redis_client

        return bool(redis_client.get(_ALERT_COOLDOWN_KEY))
    except Exception:
        return False


def _mark_alert_sent():
    try:
        from utils import redis_client

        redis_client.set(_ALERT_COOLDOWN_KEY, "1", ex=_ALERT_COOLDOWN_SECONDS)
    except Exception as exc:
        log.warning(f"[ops-monitor] cooldown write failed: {exc}")


def _notify(snapshot: dict):
    status = snapshot.get("status") or "ok"
    if status == "ok" or _cooldown_active():
        return

    from core.config import NTFY_TOPIC
    from tasks.delivery.core import _send_ntfy_message

    alerts = snapshot.get("alerts") or []
    lines = [f"status={status}"] + [
        f"{item.get('code')}: {item.get('message')}" for item in alerts[:6]
    ]
    tag = "rotating_light" if status == "critical" else "warning"
    if _send_ntfy_message(NTFY_TOPIC, "Presek ops cockpit alert", "\n".join(lines), tags=f"robot,{tag}"):
        _mark_alert_sent()
        log.info("[ops-monitor] Alert sent via ntfy")
    else:
        log.warning("[ops-monitor] Alert not sent (ntfy unavailable)")


async def _main():
    args = _parse_args()
    snapshot = await build_ops_snapshot()
    log.info(
        "[ops-monitor] status=%s alerts=%s stale=%s unsummarized_24h=%s",
        snapshot.get("status"),
        len(snapshot.get("alerts") or []),
        (snapshot.get("stale_clusters") or {}).get("count"),
        (snapshot.get("synthesis") or {}).get("unsummarized_24h"),
    )
    if args.write_redis:
        _write_redis(snapshot)
    if args.notify:
        _notify(snapshot)
    return 0 if snapshot.get("status") != "critical" else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
