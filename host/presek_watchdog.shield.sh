#!/bin/bash
# presek_watchdog.sh - keep Presek production services alive (tmux-free).
# Supervises Redis, FastAPI, Astro, Celery worker/beat and the Cloudflare tunnel
# using plain detached processes (setsid) and http/pgrep liveness checks. This
# avoids the fragile tmux socket permissions inside the proot container.
# Idempotent; only one instance runs (flock).

set -u

APP_DIR="/root/presek"
ENV_FILE="$APP_DIR/.env"
LOG_DIR="$APP_DIR/logs"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
PIDFILE="$LOG_DIR/presek_watchdog_v2.pid"
LOCKFILE="$LOG_DIR/presek_watchdog_v2.lock"
REDIS_PASS="${PRESEK_REDIS_PASS:-$(sed -n 's%^REDIS_URL=redis://:\([^@]*\)@.*%\1%p' "$ENV_FILE" 2>/dev/null | head -1)}"
INTERVAL="${WATCHDOG_INTERVAL:-30}"
DEPLOY_SCRIPT="/root/scripts/presek_deploy.sh"
POLL_INTERVAL="${POLL_INTERVAL:-120}"
MAX_LOG_BYTES="${MAX_LOG_BYTES:-26214400}"
TUNNEL_START_FILE="$LOG_DIR/.tunnel_started"
TUNNEL_MAX_AGE="${TUNNEL_MAX_AGE:-21600}"   # recycle the connector every 6h
# Match only the MAIN cloudflared tunnel. A bare 'cloudflared tunnel' also
# matches the separate SSH tunnel (ssh-config.yml), so liveness/restart would
# be fooled into thinking the main connector is up while it is dead.
TUNNEL_MATCH="/root/.cloudflared/config.yml run"

mkdir -p "$LOG_DIR"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$WATCHDOG_LOG"; }

# --- single instance guard (flock) ------------------------------------------
exec 8>"$LOCKFILE"
if ! flock -n 8; then
  exit 0
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

# --- helpers ----------------------------------------------------------------
http_ok() {
  local url="$1" expected="${2:-200}" code
  code="$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$url" 2>/dev/null || true)"
  [ "$code" = "$expected" ]
}

rotate_logs() {
  local f size
  for f in "$LOG_DIR"/*.log; do
    [ -f "$f" ] || continue
    size="$(wc -c < "$f" 2>/dev/null || echo 0)"
    if [ "$size" -ge "$MAX_LOG_BYTES" ]; then
      cp -f "$f" "$f.1" 2>/dev/null && : > "$f"
      log "rotated log: $(basename "$f") (${size} bytes)"
    fi
  done
}

ensure_redis() {
  if ! redis-cli -a "$REDIS_PASS" --no-auth-warning ping >/dev/null 2>&1; then
    log "redis down -> starting"
    # Close the flock fd in the daemon: redis would otherwise inherit fd 8,
    # leak presek_watchdog_v2.lock, and block any future watchdog from starting.
    ( exec 8>&-; redis-server --daemonize yes --bind 127.0.0.1 --protected-mode yes --dir /root \
      --requirepass "$REDIS_PASS" --maxmemory 64mb --maxmemory-policy allkeys-lru --save "" --appendonly no --logfile "$LOG_DIR/redis.log" )
    sleep 1
  fi
}

# Spawn a detached service with the .env loaded (no tmux). Guarded so we never
# accumulate duplicates: only start if no process matches the service marker.
spawn() {
  local name="$1" cmd="$2" marker="$3"
  if [ -n "$marker" ] && pgrep -f "$marker" >/dev/null 2>&1; then
    log "skip spawn '$name' (already running)"
    return
  fi
  log "spawned '$name'"
  # Close the flock fd (8) in the child so the lock is released when the
  # watchdog exits; otherwise the lock leaks and no new watchdog can start.
  setsid bash -c "exec 8>&-; exec bash -lc \"set -a; . '$ENV_FILE'; set +a; $cmd\"" \
    </dev/null >>"$LOG_DIR/$name.out" 2>&1 &
}


ensure_postgres() {
  # Local Termux-native PostgreSQL 18.6 (data dir under the termux home).
  if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
    return 0
  fi
  log "postgres down -> starting"
  local TZ_BIN=/data/data/com.termux/files/usr/bin
  local PGDATA=/data/data/com.termux/files/home/pgdata
  "$TZ_BIN/pg_ctl" -D "$PGDATA" -l /data/data/com.termux/files/home/pg.log start >/dev/null 2>&1
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 2
    pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1 && { log "postgres ready"; return 0; }
  done
  log "postgres failed to start"
  return 1
}

# --- service commands -------------------------------------------------------
cmd_fastapi="cd $APP_DIR && export PYTHONPATH=$APP_DIR && exec $APP_DIR/.venv/bin/uvicorn core.api_fast:app --host 127.0.0.1 --port 5001 --workers ${UVICORN_WORKERS:-2} >> $LOG_DIR/fastapi.log 2>&1"
cmd_astro="cd $APP_DIR/web && PORT=3000 HOST=127.0.0.1 NODE_ENV=production NODE_OPTIONS=--max-old-space-size=384 exec node ./dist/server/entry.mjs >> $LOG_DIR/astro.log 2>&1"
cmd_worker="cd $APP_DIR && export PYTHONPATH=$APP_DIR && exec $APP_DIR/.venv/bin/celery -A core.celery_app worker --loglevel=info --concurrency=1 --logfile=$LOG_DIR/worker.log"
cmd_beat="cd $APP_DIR && export PYTHONPATH=$APP_DIR && exec $APP_DIR/.venv/bin/celery -A core.celery_app beat --loglevel=info --logfile=$LOG_DIR/beat.log"
cmd_tunnel="exec cloudflared tunnel --config /root/.cloudflared/config.yml run >> $LOG_DIR/cloudflared.log 2>&1"

# A cloudflared process can be alive yet have zero live connections, or be in a
# data-plane stall (/ready shows ready connections but every stream is canceled
# by the edge and clients get 000). Verify ready connections AND recycle the
# connector periodically so a silent stall cannot persist.
tunnel_healthy() {
  pgrep -f "$TUNNEL_MATCH" >/dev/null 2>&1 || return 1
  local started now
  started="$(cat "$TUNNEL_START_FILE" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  if [ "$started" = "0" ] || [ $((now - started)) -ge "$TUNNEL_MAX_AGE" ]; then
    return 1
  fi
  local ready
  ready="$(curl -s -m 5 http://127.0.0.1:20241/ready 2>/dev/null)"
  case "$ready" in
    *'"readyConnections":0'*) return 1 ;;
    *'"readyConnections"'*) return 0 ;;
    *) return 0 ;;
  esac
}

restart_tunnel() {
  # spawn() refuses to start a second instance, so kill first.
  pkill -f "$TUNNEL_MATCH" 2>/dev/null
  sleep 2
  spawn tunnel "$cmd_tunnel" "$TUNNEL_MATCH"
  date +%s > "$TUNNEL_START_FILE"
}

log "watchdog started (pid $$, interval ${INTERVAL}s, tmux-free)"

# --- supervisor loop --------------------------------------------------------
# Adopt the currently-running tunnel into the age tracker (avoid a restart on
# the first loop after this watchdog is (re)started).
if [ ! -f "$TUNNEL_START_FILE" ] && pgrep -f "$TUNNEL_MATCH" >/dev/null 2>&1; then
  date +%s > "$TUNNEL_START_FILE"
fi

# --- apply a staged web dist pushed over adb (phone -> /sdcard) -------------
# The phone ships web_dist.tgz + web_dist.fp to /sdcard/presek_stage/ over adb
# (works even when this host's sshd is wedged). Apply whenever the fp changes.
apply_staged_dist() {
  local stage="/sdcard/presek_stage"
  local tgz="$stage/web_dist.tgz"
  local fpfile="$stage/web_dist.fp"
  local stamp="$LOG_DIR/.dist_applied_fp"
  [ -f "$tgz" ] || return 0
  local fp
  fp="$(cat "$fpfile" 2>/dev/null)"
  [ -n "$fp" ] || fp="$(stat -c '%Y-%s' "$tgz" 2>/dev/null)"
  [ -n "$fp" ] || return 0
  [ -f "$stamp" ] && [ "$(cat "$stamp" 2>/dev/null)" = "$fp" ] && return 0
  local tmp
  tmp="$(mktemp -d "$APP_DIR/web/.dist_stage.XXXXXX" 2>/dev/null)" || return 0
  if tar xzf "$tgz" -C "$tmp" 2>/dev/null && [ -f "$tmp/dist/server/entry.mjs" ]; then
    rm -rf "$APP_DIR/web/dist" && mv "$tmp/dist" "$APP_DIR/web/dist"
    printf '%s' "$fp" > "$stamp"
    printf '%s' "$fp" > "$stage/web_dist.applied"
    log "applied staged dist ($fp) -> restarting astro"
    pkill -f 'dist/server/entry[.]mjs' 2>/dev/null
  else
    log "staged dist invalid, not applied"
  fi
  rm -rf "$tmp"
}

last_poll=0
while true; do
  now="$(date +%s)"
  if [ -x "$DEPLOY_SCRIPT" ] && [ $((now - last_poll)) -ge "$POLL_INTERVAL" ]; then
    last_poll="$now"
    setsid "$DEPLOY_SCRIPT" </dev/null >>"$LOG_DIR/deploy.out" 2>&1 &
  fi

  # postgres supervised by Termux-host keepalive (pg_ctl refuses root)
  ensure_redis
  rotate_logs

  # Apply a web dist the phone pushed to /sdcard over adb (if changed).
  apply_staged_dist

  http_ok "http://127.0.0.1:5001/api/health" || spawn fastapi "$cmd_fastapi" "uvicorn core.api_fast"
  http_ok "http://127.0.0.1:3000/" || spawn astro "$cmd_astro" "node ./dist/server/entry.mjs"
  # Serve-only mode: ingestion/synthesis runs on the phone only,
  # avoiding duplicate work and AI spend on the 3GB Shield.
  # Set PRESEK_SERVE_ONLY=0 to re-enable worker/beat on this host.
  if [ "${PRESEK_SERVE_ONLY:-1}" != "1" ]; then
    pgrep -f 'celery -A core.celery_app worker' >/dev/null 2>&1 || spawn worker "$cmd_worker" "celery -A core.celery_app worker"
    pgrep -f 'celery -A core.celery_app beat'   >/dev/null 2>&1 || spawn beat "$cmd_beat" "celery -A core.celery_app beat"
  fi
  if ! tunnel_healthy; then
    log "tunnel unhealthy/stale -> recycling cloudflared"
    restart_tunnel
  fi

  sleep "$INTERVAL"
done
