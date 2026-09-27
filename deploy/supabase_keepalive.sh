#!/bin/bash
# supabase_keepalive.sh — keep the Supabase free-tier project from being paused
# for inactivity (~7 days of no activity). A trivial query counts as activity.
#
# Runs from a host that can reach Supabase (the phone). Loop: ping every 6 hours.
#
# Usage:  deploy/supabase_keepalive.sh            # run the loop foreground
#         setsid deploy/supabase_keepalive.sh &   # detach
set -u

APP_DIR="${PRESEK_APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
LOG="${SUPABASE_KEEPALIVE_LOG:-$APP_DIR/logs/supabase_keepalive.log}"
INTERVAL="${SUPABASE_KEEPALIVE_INTERVAL:-21600}"   # 6 hours
mkdir -p "$(dirname "$LOG")"

# Load DATABASE_URL from .env if present.
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$ENV_FILE"
  set +a
fi

# Only run against Supabase (skip if we're pointed at a local DB).
case "${DATABASE_URL:-}" in
  *supabase*|*supabase.co*|*pooler.supabase.com*) ;;
  *) echo "[$(date '+%F %T')] DATABASE_URL is not Supabase; exiting" >> "$LOG"; exit 0 ;;
esac

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

log "keepalive started (interval ${INTERVAL}s)"
while true; do
  if PSQL="$(command -v psql)"; then
    if "$PSQL" "$DATABASE_URL" -tAc 'select 1' >/dev/null 2>&1; then
      log "ping ok"
    else
      log "ping FAILED"
    fi
  else
    # fall back to the app's python driver
    "$APP_DIR/.venv/bin/python" -c '
import os, psycopg
with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as c:
    c.execute("select 1")
' >/dev/null 2>&1 && log "ping ok (python)" || log "ping FAILED (python)"
  fi
  sleep "$INTERVAL"
done
