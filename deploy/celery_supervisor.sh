#!/bin/bash
# celery_supervisor.sh - keep the phone's Celery worker + beat (and the Redis
# broker they use) running. The Shield is serve-only, so the phone is the sole
# ingestion/synthesis worker host.
#
# Standalone on purpose: the full presek_watchdog.sh additionally runs a standby
# origin and a Shield health probe that needs the Android adb binary, which
# cannot start its server inside this proot container. This loop keeps only the
# pieces ingestion needs.
set -u

APP_DIR="${PRESEK_APP_DIR:-/root/presek}"
LOG="$APP_DIR/logs/celery_supervisor.log"
LOCK="$APP_DIR/logs/.celery_supervisor.lock"
INTERVAL="${CELERY_SUPERVISOR_INTERVAL:-60}"
CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-2}"
REDIS_PASS="$(sed -n 's%^REDIS_URL=redis://:\([^@]*\)@.*%\1%p' "$APP_DIR/.env" 2>/dev/null | head -1)"
mkdir -p "$(dirname "$LOG")"

exec 9>"$LOCK"
flock -n 9 || exit 0

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

cmd_worker="exec $APP_DIR/.venv/bin/celery -A core.celery_app worker --loglevel=info --concurrency=$CONCURRENCY --logfile=$APP_DIR/logs/worker.log"
cmd_beat="exec $APP_DIR/.venv/bin/celery -A core.celery_app beat --loglevel=info --logfile=$APP_DIR/logs/beat.log"

spawn() {
  local name="$1" marker="$2" cmd="$3"
  if pgrep -f "$marker" >/dev/null 2>&1; then
    return 0
  fi
  log "starting $name"
  setsid bash -c "exec 9>&-; set -a; . '$APP_DIR/.env'; set +a; cd '$APP_DIR'; export PYTHONPATH='$APP_DIR'; $cmd" \
    </dev/null >>"$APP_DIR/logs/$name.out" 2>&1 &
}

PGB_INI=/etc/pgbouncer/pgbouncer.ini

# DATABASE_URL points at the local pgbouncer; a hard kill leaves its pidfile
# behind and the next start then refuses to run.
ensure_pgbouncer() {
  [ -f "$PGB_INI" ] && command -v pgbouncer >/dev/null 2>&1 || return 0
  pgrep -x pgbouncer >/dev/null 2>&1 && return 0
  log "pgbouncer down -> starting"
  rm -f "$(sed -n 's/^pidfile *= *//p' "$PGB_INI" | head -1)"
  ( exec 9>&-; setsid su postgres -s /bin/bash -c "pgbouncer -d $PGB_INI --daemon" </dev/null >/dev/null 2>&1 & )
  sleep 2
}

log "celery supervisor started (interval ${INTERVAL}s, concurrency ${CONCURRENCY})"
while true; do
  ensure_pgbouncer
  if ! redis-cli -a "$REDIS_PASS" --no-auth-warning ping >/dev/null 2>&1; then
    log "redis down -> starting"
    ( exec 9>&-; redis-server --daemonize yes --bind "127.0.0.1 -::1" --dir /root --requirepass "$REDIS_PASS" --logfile "$APP_DIR/logs/redis.log" )
    sleep 1
  fi
  spawn worker 'celery -A core.celery_app worker' "$cmd_worker"
  spawn beat   'celery -A core.celery_app beat'   "$cmd_beat"
  sleep "$INTERVAL" 9>&-
done
