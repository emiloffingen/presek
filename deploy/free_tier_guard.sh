#!/bin/bash
# free_tier_guard.sh - keep the Supabase free project active and safely backed up.
#
# Runs on the phone (repo + venv + pg_dump live here). One infinite loop:
#   - every CHECK_INTERVAL seconds: query the database size. That query is
#     itself activity, so it also stops the free project pausing for inactivity
#     (~7 days) - it subsumes deploy/supabase_keepalive.sh.
#   - ntfy alert once per day when the DB crosses FREE_TIER_ALERT_MB (the
#     Supabase free cap is 500 MB).
#   - optional (FREE_TIER_DUMP=1, off by default): once per day at DUMP_HOUR a
#     full pg_dump | gzip into FREE_TIER_BACKUP_DIR, pruning copies older than
#     KEEP_DAYS. Off because the watchdog already runs deploy/backup_postgres.sh
#     and every full dump spends ~250 MB of the 5 GB monthly Supabase egress.
#     Dumps use the session pooler (5432); the transaction pooler does not
#     support pg_dump.
#
# Env overrides: FREE_TIER_DUMP, FREE_TIER_CHECK_INTERVAL, FREE_TIER_DUMP_HOUR,
# FREE_TIER_KEEP_DAYS, FREE_TIER_ALERT_MB, FREE_TIER_BACKUP_DIR, NTFY_TOPIC_URL,
# PRESEK_APP_DIR, ENV_FILE.
set -uo pipefail

APP_DIR="${PRESEK_APP_DIR:-/root/presek}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
LOG="${FREE_TIER_GUARD_LOG:-$APP_DIR/logs/free_tier_guard.log}"
STATE="${FREE_TIER_GUARD_STATE:-$APP_DIR/logs/.free_tier_guard_state}"
BACKUP_DIR="${FREE_TIER_BACKUP_DIR:-/root/presek-backups}"
NTFY="${NTFY_TOPIC_URL:-}"
NTFY_TOKEN="${NTFY_TOKEN:-}"
CHECK_INTERVAL="${FREE_TIER_CHECK_INTERVAL:-1800}"
DUMP="${FREE_TIER_DUMP:-0}"
DUMP_HOUR="${FREE_TIER_DUMP_HOUR:-3}"
KEEP_DAYS="${FREE_TIER_KEEP_DAYS:-7}"
ALERT_MB="${FREE_TIER_ALERT_MB:-400}"
PY="$APP_DIR/.venv/bin/python"

# One instance only.
LOCK="$APP_DIR/logs/free_tier_guard.lock"
exec 9>"$LOCK"
flock -n 9 || exit 0

mkdir -p "$(dirname "$LOG")" "$BACKUP_DIR"
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
notify() {
  [ -n "$NTFY" ] || return 0
  local auth=()
  [ -n "$NTFY_TOKEN" ] && auth=(-H "Authorization: Bearer $NTFY_TOKEN")
  curl -s -m 12 -H "Title: $1" -H "Tags: $2" "${auth[@]}" -d "$3" "$NTFY" >/dev/null 2>&1
}

if [ -z "${DATABASE_URL:-}" ]; then log "DATABASE_URL missing; exiting"; exit 1; fi
DUMP_URL="${DATABASE_URL/6543/5432}"

db_size_mb() {
  "$PY" - <<'PY' 2>/dev/null
import os, psycopg
with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as c:
    print(int(c.execute("select pg_database_size(current_database())").fetchone()[0]) // 1048576)
PY
}

last_dump=""
log "guard started (interval ${CHECK_INTERVAL}s, alert ${ALERT_MB}MB, dump ${DUMP} hour ${DUMP_HOUR}, keep ${KEEP_DAYS}d)"
while true; do
  mb="$(db_size_mb || true)"
  if [ -n "${mb:-}" ]; then
    log "db size ${mb} MB"
    if [ "$mb" -ge "$ALERT_MB" ]; then
      today="$(date +%F)"
      if [ "$(cat "$STATE" 2>/dev/null || true)" != "$today" ]; then
        notify "Presek DB ${mb} MB" "warning" "Supabase free cap is 500 MB; now ${mb} MB. Plan the move or trim (legacy embedding columns ~28 MB)."
        echo "$today" > "$STATE"
      fi
    fi
  else
    log "db size check FAILED"
  fi

  hour="$(date +%H)"; today="$(date +%F)"
  if [ "$DUMP" = "1" ] && [ "$((10#$hour))" -eq "$DUMP_HOUR" ] && [ "$last_dump" != "$today" ]; then
    out="$BACKUP_DIR/presek-$today.sql.gz"
    if timeout 900 pg_dump --no-owner --no-privileges "$DUMP_URL" 2>>"$LOG" | gzip > "$out"; then
      log "backup ok: $out ($(du -h "$out" 2>/dev/null | cut -f1))"
      find "$BACKUP_DIR" -maxdepth 1 -name 'presek-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
    else
      log "backup FAILED"; rm -f "$out"
    fi
    last_dump="$today"
  fi

  sleep "$CHECK_INTERVAL"
done
