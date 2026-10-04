#!/bin/bash
# shield_keepawake_loop.sh - enforce the Shield's never-sleep policy from the
# phone on a fixed interval, independent of presek_watchdog.sh.
#
# The watchdog's Shield health probe needs the Android `adb` binary, which
# cannot start its server inside this proot container ("proot error: tcp:5037"),
# so it can never stand the phone connector down. This loop only needs the
# keepawake helper (pure-Python adb_shell over TCP), which works in proot.
set -u

HELPER="/root/scripts/shield_keepawake_phone.sh"
LOG="/root/presek/logs/shield_keepawake_loop.log"
LOCK="/root/presek/logs/.shield_keepawake_loop.lock"
INTERVAL="${SHIELD_KEEP_INTERVAL:-300}"
mkdir -p "$(dirname "$LOG")"

exec 9>"$LOCK"
flock -n 9 || exit 0

echo "[$(date '+%F %T')] keepawake loop started (interval ${INTERVAL}s)" >> "$LOG"
while true; do
  "$HELPER" >/dev/null 2>&1
  sleep "$INTERVAL"
done
