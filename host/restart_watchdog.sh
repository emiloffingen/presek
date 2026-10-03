#!/bin/bash
# Clean restart of the Presek watchdog.
#
# The watchdog holds a flock (fd 8) for as long as it runs. A naive
# "kill && start" race lets the new instance hit the lock while the old one is
# still shutting down, so it exits and nothing restarts it promptly. This stops
# the old instance, waits for the lock to actually release (killing any stray
# fd-8 holder as a last resort), then starts a new one and verifies it took over.

set -u

APP_DIR="/root/presek"
LOG_DIR="$APP_DIR/logs"
LOCKFILE="$LOG_DIR/presek_watchdog.lock"
PIDFILE="$LOG_DIR/presek_watchdog.pid"
WATCHDOG="/root/scripts/presek_watchdog.sh"
WAIT_SECONDS="${WAIT_SECONDS:-30}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

lock_free() { flock -n "$LOCKFILE" -c true 2>/dev/null; }

log "stopping watchdog..."
pkill -f "$WATCHDOG" 2>/dev/null

for _ in $(seq 1 "$WAIT_SECONDS"); do
  lock_free && break
  sleep 1
done

if ! lock_free; then
  log "lock still held after ${WAIT_SECONDS}s; killing fd-8 holders"
  for proc in /proc/[0-9]*; do
    for fd in "$proc"/fd/*; do
      if [ "$(readlink "$fd" 2>/dev/null)" = "$LOCKFILE" ]; then
        pid="${proc##*/}"
        [ "$pid" = "$$" ] && continue
        log "killing lock holder pid $pid: $(tr '\0' ' ' < "$proc/cmdline" 2>/dev/null | cut -c1-80)"
        kill -9 "$pid" 2>/dev/null
      fi
    done
  done
  sleep 1
fi

log "starting watchdog..."
setsid "$WATCHDOG" </dev/null >>"$LOG_DIR/watchdog.out" 2>&1 &
sleep 3

if pgrep -f "$WATCHDOG" >/dev/null 2>&1; then
  log "watchdog running (pid $(cat "$PIDFILE" 2>/dev/null || echo '?'))"
else
  log "ERROR: watchdog did not start"
  exit 1
fi
