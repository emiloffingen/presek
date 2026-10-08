#!/bin/bash
# presek_watchdog.sh - keep Presek production services alive on Termux.
# Idempotent supervisor for Redis, FastAPI, Astro, Celery worker/beat and the
# Cloudflare tunnel. Safe to run repeatedly; only one instance runs at a time.

set -u

APP_DIR="/root/presek"
SESSION="presek"
ENV_FILE="$APP_DIR/.env"
LOG_DIR="$APP_DIR/logs"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
PIDFILE="$LOG_DIR/presek_watchdog.pid"
REDIS_PASS="${PRESEK_REDIS_PASS:-}"  # never hardcode; derived from the app .env below
# The app authenticates with the password from .env REDIS_URL (rotated
# 2026-10-04). Derive it so the server we start always matches what the
# clients send; otherwise workers crash-loop with "invalid username-password".
_ENV_REDIS_PASS="$(grep -E '^REDIS_URL=' "$ENV_FILE" 2>/dev/null | sed -n 's#.*://:\([^@]*\)@.*#\1#p' | tail -n 1)"
[ -n "$_ENV_REDIS_PASS" ] && REDIS_PASS="$_ENV_REDIS_PASS"
INTERVAL="${WATCHDOG_INTERVAL:-30}"
DEPLOY_SCRIPT="/root/scripts/presek_deploy.sh"
SHIELD_KEEPER_SCRIPT="/root/scripts/shield_keepawake_phone.sh"
SHIELD_KEEP_INTERVAL="${SHIELD_KEEP_INTERVAL:-300}"
# Scheduled homepage synthesis refresh (homepage clusters only). The runner is
# staleness-gated, so it only regenerates what the homepage currently flags.
HOMEPAGE_SYNTH_SCRIPT="$APP_DIR/scripts/synthesize_homepage.py"
HOMEPAGE_SYNTH_PY="$APP_DIR/.venv/bin/python"
HOMEPAGE_SYNTH_LOG="$LOG_DIR/homepage_synth.log"
HOMEPAGE_SYNTH_PID="$LOG_DIR/.homepage_synth.pid"
HOMEPAGE_SYNTH_STAMP="$LOG_DIR/.homepage_synth_last"
HOMEPAGE_SYNTH_INTERVAL="${HOMEPAGE_SYNTH_INTERVAL:-7200}"
# The Shield is the PRIMARY origin; the phone's cloudflared is STANDBY (runs
# only while the Shield is unhealthy). Set SHIELD_PRIMARY=0 to revert to the
# old always-on behavior.
SHIELD_PRIMARY="${SHIELD_PRIMARY:-1}"
POLL_INTERVAL="${POLL_INTERVAL:-120}"
MAX_LOG_BYTES="${MAX_LOG_BYTES:-26214400}"
# Match only the MAIN cloudflared tunnel. A bare 'cloudflared tunnel' also
# matches the separate SSH tunnel (ssh-config.yml), so liveness/restart would
# be fooled into thinking the main connector is up while it is dead.
TUNNEL_MATCH="/root/.cloudflared/config.yml run"

mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$WATCHDOG_LOG"; }

# Truncate logs that grow past MAX_LOG_BYTES, keeping one previous copy. Safe
# for O_APPEND writers and Celery's append-mode FileHandler.
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

# --- single instance guard (flock) -----------------------------------------
# Proot remaps PIDs between sessions, so a pidfile + kill -0 check lets duplicate
# watchdogs slip through. flock is tied to the lock file, not a pid, and is
# reliable across proot sessions. Every long-lived child closes fd 8 so the lock
# is held only for as long as the watchdog itself runs.
LOCKFILE="$LOG_DIR/presek_watchdog.lock"
exec 8>"$LOCKFILE"
if ! flock -w 5 8; then
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

ensure_redis() {
  if ! redis-cli -a "$REDIS_PASS" --no-auth-warning ping >/dev/null 2>&1; then
    log "redis down -> starting"
    ( exec 8>&-; redis-server --daemonize yes --bind "127.0.0.1 -::1" --dir /root \
      --requirepass "$REDIS_PASS" --logfile "$LOG_DIR/redis.log" )
    sleep 1
  fi
}

ensure_pgbouncer() {
  # Aiven PgBouncer on 127.0.0.1:6543. Must be (re)started by this watchdog:
  # processes spawned from transient proot sessions are reaped when that
  # session exits, so a manually started pgbouncer dies quickly. Spawned
  # here (persistent session) it survives.
  if pgrep -f "pgbouncer -d /etc/pgbouncer/pgbouncer.ini" >/dev/null 2>&1; then
    return 0
  fi
  log "pgbouncer down -> starting"
  rm -f /var/run/pgbouncer/pgbouncer.pid
  ( exec 8>&-; setsid su postgres -s /bin/bash -c "pgbouncer -d /etc/pgbouncer/pgbouncer.ini --daemon" </dev/null >/dev/null 2>&1 & )
  sleep 2
}

ensure_session() { :; }   # tmux is not used; spawning is via setsid
window_exists() { return 1; }
drop_window() { :; }

spawn_window() {
  local name="$1" cmd="$2"
  # Only one instance per marker: derive a pgrep marker from the command.
  case "$name" in
    fastapi) pgrep -f 'uvicorn core.api_fast' >/dev/null && return 0 ;;
    astro)   pgrep -f 'dist/server/entry.mjs' >/dev/null && return 0 ;;
    worker)  pgrep -f 'celery -A core.celery_app worker' >/dev/null && return 0 ;;
    beat)    pgrep -f 'celery -A core.celery_app beat' >/dev/null && return 0 ;;
    tunnel)  pgrep -f "$TUNNEL_MATCH" >/dev/null && return 0 ;;
  esac
  # Close fd 8 so the flock is released when this watchdog exits.
  setsid bash -c "exec 8>&-; set -a; . '$ENV_FILE'; set +a; $cmd" \
    </dev/null >>"$LOG_DIR/$name.out" 2>&1 &
  log "spawned '$name' (setsid)"
}


# A cloudflared process can be alive yet have ZERO live connections (QUIC stall).
# When that happens Cloudflare silently serves another connector's stale build.
# Verify the connector actually has ready connections, not just that it exists.
#
# /ready can also lie during a *data-plane* stall (connections registered but all
# streams canceled by the edge, clients get 000). We therefore also force a
# periodic refresh: a tunnel older than TUNNEL_MAX_AGE is recycled, which clears
# silent stalls that /ready never surfaces.
TUNNEL_START_FILE="$LOG_DIR/.tunnel_started"
TUNNEL_MAX_AGE="${TUNNEL_MAX_AGE:-21600}"   # recycle the connector every 6h

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
    *) return 0 ;;  # endpoint missing: fall back to process check
  esac
}

kill_tunnel() {
  # cloudflared can linger in graceful shutdown for a long time after SIGTERM.
  # If it is still alive, spawn_window's pgrep guard would silently skip a
  # respawn (or standby would not actually disconnect), so wait, then SIGKILL.
  pkill -f "$TUNNEL_MATCH" 2>/dev/null
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    pgrep -f "$TUNNEL_MATCH" >/dev/null 2>&1 || break
    sleep 1
  done
  if pgrep -f "$TUNNEL_MATCH" >/dev/null 2>&1; then
    log "cloudflared ignored SIGTERM; sending SIGKILL"
    pkill -9 -f "$TUNNEL_MATCH" 2>/dev/null
    sleep 1
  fi
}

restart_tunnel() {
  # /ready-only health checks miss data-plane stalls, and spawn_window refuses to
  # start a second instance; kill first so the respawn actually happens.
  kill_tunnel
  spawn_window tunnel "$cmd_tunnel"
  date +%s > "$TUNNEL_START_FILE"
}

# --- service commands -------------------------------------------------------
# Multiple uvicorn workers give headroom on Cloudflare cache-miss bursts (the
# app has no heavy in-process state; hot reads are Redis-cached). Override with
# UVICORN_WORKERS in the environment before launching the watchdog.
UVICORN_WORKERS="${UVICORN_WORKERS:-2}"
cmd_fastapi="cd $APP_DIR && export PYTHONPATH=$APP_DIR && exec $APP_DIR/.venv/bin/uvicorn core.api_fast:app --host 127.0.0.1 --port 5001 --workers $UVICORN_WORKERS >> $LOG_DIR/fastapi.log 2>&1"
cmd_astro="cd $APP_DIR/web && PORT=3000 HOST=127.0.0.1 exec node ./dist/server/entry.mjs >> $LOG_DIR/astro.log 2>&1"
# The worker must name every queue it serves. Without --queues, Celery consumes
# only task_default_queue ("celery"), so tasks routed to the other queues (for
# example tasks.maintenance.* -> "maintenance") were enqueued and never executed.
# Keep this list in sync with celery_app.conf.task_queues in core/celery_app.py.
CELERY_QUEUES="${CELERY_QUEUES:-celery,ingestion,ingestion-crawl,fast-track,synthesis,intel-heavy,delivery,maintenance}"
cmd_worker="cd $APP_DIR && export PYTHONPATH=$APP_DIR && exec $APP_DIR/.venv/bin/celery -A core.celery_app worker --loglevel=info --concurrency=${CELERY_WORKER_CONCURRENCY:-2} --queues=$CELERY_QUEUES --logfile=$LOG_DIR/worker.log"
cmd_beat="cd $APP_DIR && export PYTHONPATH=$APP_DIR && exec $APP_DIR/.venv/bin/celery -A core.celery_app beat --loglevel=info --logfile=$LOG_DIR/beat.log"
cmd_tunnel="exec cloudflared tunnel --config /root/.cloudflared/config.yml run >> $LOG_DIR/cloudflared.log 2>&1"

log "watchdog started (pid $$, interval ${INTERVAL}s)"


# --- shield sync guard -------------------------------------------------------
# The Cloudflare tunnel has two connectors (phone + shield). The phone is the
# only builder, so whenever the shield (re)appears on the network it must be
# handed the current dist or it will serve a stale build (split-brain). We run
# the go-live once per presence: a marker records the last successful sync.
SHIELD_MARKER="$LOG_DIR/.shield_synced"
SHIELD_SYNC_LOCK="$LOG_DIR/.shield_sync.lock"
SHIELD_PROBE="u0_a106@192.168.0.62"
SHIELD_PORT="${SHIELD_PORT:-8022}"
SSH_KEY="/root/.ssh/termux_test"
# Dist sync ships over adb (robust when the Shield's sshd is wedged). The
# Shield's watchdog self-applies from /sdcard/presek_stage.
SHIELD_ADB="${SHIELD_ADB:-192.168.0.62:5555}"
ADB_BIN="${ADB_BIN:-/data/data/com.termux/files/usr/bin/adb}"

sync_shield_if_present() {
  # IMPORTANT: never block the supervision loop. All the work (adb push, wait
  # for the shield to apply) happens in a detached subshell. A lock file
  # prevents pile-ups. Shipping over adb means a wedged Shield sshd can no
  # longer block deploys; the Shield's watchdog self-applies from /sdcard.
  [ -f "$SHIELD_SYNC_LOCK" ] && return 0
  touch "$SHIELD_SYNC_LOCK"
  setsid bash -c '
    exec 8>&-  # do not hold the watchdog lock while syncing the shield
    LOG="$1"; MARKER="$2"; APP="$3"; LOCK="$4"; ADB="$5"; SHIELD_ADB="$6"
    SYNCING="${MARKER%/*}/.shield_syncing"
    trap "rm -f \"$LOCK\"; rm -f \"$SYNCING\"" EXIT
    FP="$(git -C "$APP" rev-parse HEAD 2>/dev/null)-$(stat -c %Y "$APP/web/dist/server/entry.mjs" 2>/dev/null)"
    [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$FP" ] && exit 0
    [ -f "$APP/web/dist/server/entry.mjs" ] || exit 0
    TMP="$(mktemp -d)"; DIST="$TMP/web_dist.tgz"
    tar czf "$DIST" -C "$APP/web" dist 2>/dev/null || { rm -rf "$TMP"; exit 0; }
    printf "%s" "$FP" > "$TMP/web_dist.fp"
    # Hold the phone connector up while the shield swaps the dist (avoids a gap).
    touch "$SYNCING"
    echo "[$(date "+%F %T")] shield sync (adb): pushing build $FP" >> "$LOG"
    "$ADB" connect "$SHIELD_ADB" >/dev/null 2>&1
    if "$ADB" -s "$SHIELD_ADB" push "$DIST" /sdcard/presek_stage/web_dist.tgz >/dev/null 2>&1 && \
       "$ADB" -s "$SHIELD_ADB" push "$TMP/web_dist.fp" /sdcard/presek_stage/web_dist.fp >/dev/null 2>&1; then
      ok=0; i=0
      while [ "$i" -lt 10 ]; do
        sleep 5; i=$((i + 1))
        if [ "$("$ADB" -s "$SHIELD_ADB" shell cat /sdcard/presek_stage/web_dist.applied 2>/dev/null | tr -d "\r\n")" = "$FP" ]; then ok=1; break; fi
      done
      if [ "$ok" = 1 ]; then
        echo "$FP" > "$MARKER"
        echo "[$(date "+%F %T")] shield sync complete ($FP)" >> "$LOG"
      else
        echo "[$(date "+%F %T")] shield pushed but not applied yet (will retry)" >> "$LOG"
      fi
    else
      echo "[$(date "+%F %T")] shield adb push failed (will retry)" >> "$LOG"
    fi
    rm -f "$SYNCING"
    rm -rf "$TMP"
  ' _ "$LOG_DIR/shield_sync.log" "$SHIELD_MARKER" "$APP_DIR" "$SHIELD_SYNC_LOCK" "$ADB_BIN" "$SHIELD_ADB" </dev/null >/dev/null 2>&1 &
}

# --- origin role: Shield primary, phone connector standby -------------------
# Healthy = the Shield's origin (astro + api) answers AND its tunnel connector
# has ready connections. Probed over HTTP through adb port-forwards, no SSH (the
# Shield's sshd has wedged repeatedly), so the Shield keeps astro :3000, api
# :5001 and cloudflared metrics :20241 on 127.0.0.1 instead of exposing them on
# every interface. Local ports 33000/35001/30241 forward to the Shield's.
shield_forwards_ok() {  local spec
  for spec in "tcp:33000 tcp:3000" "tcp:35001 tcp:5001" "tcp:30241 tcp:20241"; do
    # shellcheck disable=SC2086
    timeout 6 "$ADB_BIN" -s "$SHIELD_ADB" forward $spec >/dev/null 2>&1 || {
      timeout 8 "$ADB_BIN" connect "$SHIELD_ADB" >/dev/null 2>&1
      # shellcheck disable=SC2086
      timeout 6 "$ADB_BIN" -s "$SHIELD_ADB" forward $spec >/dev/null 2>&1 || return 1
    }
  done
}
# SSH origin probe (Tailscale). ADB port-forwards cannot run inside proot, so
# the Shield health check goes over SSH (sshd recovered after the reboot).
# Kept fast so a dead Shield never stalls the 30s supervision loop.
SHIELD_SSH_HOST="${SHIELD_SSH_HOST:-u0_a106@100.77.135.12}"
SHIELD_SSH_PORT="${SHIELD_SSH_PORT:-8022}"
# Multiplexed SSH: one persistent master connection, all probes ride it.
# Without this, every probe forks a full auth (zombie sshd-auth pile up on
# the Shield until its sshd wedges and banner-times-out).
_SSH_SOCK_DIR="${TMPDIR:-/tmp}/presek-ssh-mux"
_SSH_MUX="ControlMaster=auto,ControlPath=${_SSH_SOCK_DIR}/%r@%h:%p,ControlPersist=300"
_shield_ssh() {
  mkdir -p "$_SSH_SOCK_DIR" 2>/dev/null
  timeout 12 ssh -i "$SSH_KEY" -p "$SHIELD_SSH_PORT" \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o BatchMode=yes -o ConnectTimeout=4 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 "$SHIELD_SSH_HOST" "$@" 2>/dev/null
}
shield_origin_ok_ssh() {
  _shield_ssh "proot-distro login debian -- curl -s -m 3 -o /dev/null http://127.0.0.1:5001/api/health"
}
# Shield workers presence: the phone stands its workers down only when the
# Shield actually runs its own (API-up alone is not enough — the Shield has
# run API-only for days while the phone did all ingestion/synthesis).
shield_workers_ok_ssh() {
  # NOTE: bracket pattern avoids matching the probe's own remote command line.
  _shield_ssh "pgrep -f 'celery -A core.celery_ap[p] worker' >/dev/null 2>&1"
}
shield_origin_ok() {
  shield_origin_ok_ssh && return 0
  shield_forwards_ok &&
  curl -s -o /dev/null -m 4 "http://127.0.0.1:33000/" &&
  curl -s -o /dev/null -m 4 "http://127.0.0.1:35001/api/health" &&
  curl -s -m 4 "http://127.0.0.1:30241/ready" 2>/dev/null | grep -q '"readyConnections":[1-9]'
}
shield_ok_streak=0
shield_fail_streak=0

# --- supervisor loop --------------------------------------------------------
# Adopt the currently-running tunnel into the age tracker (avoid a restart on
# the first loop after this watchdog is (re)started).
if [ ! -f "$TUNNEL_START_FILE" ] && pgrep -f "$TUNNEL_MATCH" >/dev/null 2>&1; then
  date +%s > "$TUNNEL_START_FILE"
fi

# --- daily backup -----------------------------------------------------------
# The Shield host is unreliable (WiFi power-save drops it off the LAN), so the
# phone performs the authoritative PostgreSQL backup. Runs once per successful
# day, retried at most hourly, detached so a ~1 min pg_dump never blocks service
# supervision. Offsite (R2) sync runs only after a successful local dump.
BACKUP_DONE_STAMP="$LOG_DIR/.backup_done_day"
BACKUP_ATTEMPT_STAMP="$LOG_DIR/.backup_last_attempt"

maybe_backup() {
  [ -x "$APP_DIR/deploy/backup_postgres.sh" ] || return 0
  local today now last
  today="$(date +%F)"; now="$(date +%s)"
  [ -f "$BACKUP_DONE_STAMP" ] && [ "$(cat "$BACKUP_DONE_STAMP" 2>/dev/null)" = "$today" ] && return 0
  last="$(cat "$BACKUP_ATTEMPT_STAMP" 2>/dev/null || echo 0)"
  [ $((now - last)) -lt 3600 ] && return 0
  echo "$now" > "$BACKUP_ATTEMPT_STAMP"
  setsid bash -c "
    exec 8>&-  # do not hold the watchdog lock during a ~1 min dump
    APP_ROOT='$APP_DIR' bash '$APP_DIR/deploy/backup_postgres.sh' >> '$LOG_DIR/backup.log' 2>&1 &&
    APP_ROOT='$APP_DIR' bash '$APP_DIR/deploy/sync_backups_offsite.sh' >> '$LOG_DIR/backup_sync.log' 2>&1 &&
    date +%F > '$BACKUP_DONE_STAMP'
  " </dev/null >/dev/null 2>&1 &
}

# --- public site alerting ---------------------------------------------------
# Push an ntfy alert when the public site goes down and when it recovers.
# Two consecutive failed checks are required before alerting (avoids a single
# transient blip), and only transitions alert (no repeat spam). This runs in
# the supervised watchdog, unlike the old detached shield_watch_phone.sh which
# silently died on 2026-09-26.
NTFY_URL="${NTFY_URL:-https://ntfy.sh/presek-alerts-09c4417ba2ed}"
SITE_CHECK_FILE="$LOG_DIR/.site_last_check"
SITE_MISS_FILE="$LOG_DIR/.site_miss"
SITE_ALERTED_FILE="$LOG_DIR/.site_alerted"
SITE_STALE_MISS_FILE="$LOG_DIR/.site_stale_miss"
SITE_STALE_ALERTED_FILE="$LOG_DIR/.site_stale_alerted"
SITE_CHECK_INTERVAL="${SITE_CHECK_INTERVAL:-60}"

notify() { curl -s -m 10 -H "Title: $1" -H "Tags: $2" -d "$3" "$NTFY_URL" >/dev/null 2>&1; }

check_site_health() {
  local now last code miss alerted lbody
  now="$(date +%s)"; last="$(cat "$SITE_CHECK_FILE" 2>/dev/null || echo 0)"
  [ $((now - last)) -lt "$SITE_CHECK_INTERVAL" ] && return 0
  echo "$now" > "$SITE_CHECK_FILE"

  code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' https://presek.mk/api/health 2>/dev/null)"

  if [ "$code" != "200" ]; then
    miss="$(cat "$SITE_MISS_FILE" 2>/dev/null || echo 0)"; miss=$((miss + 1))
    echo "$miss" > "$SITE_MISS_FILE"
    alerted="$(cat "$SITE_ALERTED_FILE" 2>/dev/null || echo 0)"
    if [ "$miss" -ge 2 ] && [ "$alerted" != "1" ]; then
      log "PUBLIC DOWN ($code) -> alert"
      notify "presek.mk DOWN" "rotating_light" "presek.mk/api/health returned $code (2 checks). $code=000 often means the tunnel is down."
      echo 1 > "$SITE_ALERTED_FILE"
    fi
    return 0
  fi

  # Site answered: clear the outage state.
  alerted="$(cat "$SITE_ALERTED_FILE" 2>/dev/null || echo 0)"
  if [ "$alerted" = "1" ]; then
    log "PUBLIC UP (200) -> alert recovered"
    notify "presek.mk recovered" "white_check_mark" "presek.mk is serving again (HTTP 200)."
    echo 0 > "$SITE_ALERTED_FILE"
  fi
  echo 0 > "$SITE_MISS_FILE"

  # Ingestion-health signal: the public /api/health is a trimmed summary with
  # no freshness field, so query the LOCAL API. Prolonged staleness means the
  # phone's ingestion/Celery is stalled (the Shield is serve-only).
  lbody="$(curl -s -m 8 http://127.0.0.1:5001/api/health 2>/dev/null)"
  case "$lbody" in
    *'"freshness":{"status":"fresh"'*)
      alerted="$(cat "$SITE_STALE_ALERTED_FILE" 2>/dev/null || echo 0)"
      if [ "$alerted" = "1" ]; then
        log "FRESHNESS recovered -> alert"
        notify "presek freshness recovered" "white_check_mark" "Content freshness is healthy again."
        echo 0 > "$SITE_STALE_ALERTED_FILE"
      fi
      echo 0 > "$SITE_STALE_MISS_FILE"
      ;;
    *)
      miss="$(cat "$SITE_STALE_MISS_FILE" 2>/dev/null || echo 0)"; miss=$((miss + 1))
      echo "$miss" > "$SITE_STALE_MISS_FILE"
      alerted="$(cat "$SITE_STALE_ALERTED_FILE" 2>/dev/null || echo 0)"
      if [ "$miss" -ge 5 ] && [ "$alerted" != "1" ]; then
        log "FRESHNESS stale ($miss) -> alert"
        notify "presek ingestion stale" "hourglass" "Content freshness has been stale for ~5 checks; ingestion (phone) may be stalled."
        echo 1 > "$SITE_STALE_ALERTED_FILE"
      fi
      ;;
  esac
}

last_poll=0
last_shieldkeep=0
last_homepage_synth="$(cat "$HOMEPAGE_SYNTH_STAMP" 2>/dev/null || echo 0)"
ASTRO_FP_FILE="$LOG_DIR/.phone_dist_fp"
HEAD_FP_FILE="$LOG_DIR/.phone_head_fp"
# Shield SSH probes are throttled (every 4th loop ≈ 2 min): each probe opens a
# fresh SSH + proot session, and rapid probing piles up zombie sshd-sessions
# until the Shield's sshd wedges (banner timeouts). Streak logic is unchanged,
# just evaluated less often.
_loop_n=0
while true; do
  _loop_n=$((_loop_n + 1))
  # Git auto-deploy poll. Non-blocking: the deploy script self-locks, so a slow
  # build never stalls service supervision.
  now="$(date +%s)"
  if [ -x "$DEPLOY_SCRIPT" ] && [ $((now - last_poll)) -ge "$POLL_INTERVAL" ]; then
    last_poll="$now"
    setsid bash -c "exec 8>&-; exec '$DEPLOY_SCRIPT'" </dev/null >>"$LOG_DIR/deploy.out" 2>&1 &
  fi

  ensure_redis
  ensure_pgbouncer
  ensure_session
  rotate_logs
  maybe_backup
  check_site_health

  if window_exists _init && [ "$(tmux list-windows -t "$SESSION" 2>/dev/null | wc -l)" -gt 1 ]; then
    drop_window _init
  fi

  http_ok "http://127.0.0.1:5001/api/health" || spawn_window fastapi "$cmd_fastapi"
  http_ok "http://127.0.0.1:3000/" || spawn_window astro "$cmd_astro"
  # Standby workers: while the Shield is confirmed healthy AND runs its own
  # workers, the phone's worker/beat stay down to save AI quota and
  # Supabase pool connections. Any single failed shield check re-enables
  # them immediately (failover); standing down needs 2 consecutive OKs.
  if [ "$SHIELD_PRIMARY" = "1" ] && [ "$shield_ok_streak" -ge 2 ] && shield_workers_ok_ssh; then
    if pgrep -f 'celery -A core.celery_app worker' >/dev/null 2>&1; then
      log "shield healthy -> phone workers standby (stopping worker/beat)"
      pkill -f 'celery -A core.celery_ap[p] worker' 2>/dev/null
      pkill -f 'celery -A core.celery_ap[p] beat' 2>/dev/null
    fi
  else
    pgrep -f 'celery -A core.celery_app worker' >/dev/null 2>&1 || spawn_window worker "$cmd_worker"
    pgrep -f 'celery -A core.celery_app beat'   >/dev/null 2>&1 || spawn_window beat "$cmd_beat"
  fi

  # Keep the standby stack on the current build. Astro serves the build it
  # started with, so replacing dist without a restart would 404 the new asset
  # hashes on failover; a new HEAD likewise needs a fresh uvicorn.
  dist_fp="$(stat -c %Y "$APP_DIR/web/dist/server/entry.mjs" 2>/dev/null)"
  if [ -n "$dist_fp" ]; then
    if [ ! -f "$ASTRO_FP_FILE" ]; then echo "$dist_fp" > "$ASTRO_FP_FILE"
    elif [ "$(cat "$ASTRO_FP_FILE" 2>/dev/null)" != "$dist_fp" ]; then
      echo "$dist_fp" > "$ASTRO_FP_FILE"
      pgrep -f 'dist/server/entry.mjs' >/dev/null 2>&1 && { log "phone dist changed -> restarting standby astro"; pkill -f 'dist/server/entry[.]mjs' 2>/dev/null; }
    fi
  fi
  head_fp="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null)"
  if [ -n "$head_fp" ]; then
    if [ ! -f "$HEAD_FP_FILE" ]; then echo "$head_fp" > "$HEAD_FP_FILE"
    elif [ "$(cat "$HEAD_FP_FILE" 2>/dev/null)" != "$head_fp" ]; then
      echo "$head_fp" > "$HEAD_FP_FILE"
      pgrep -f 'uvicorn core.api_fast' >/dev/null 2>&1 && { log "phone HEAD changed -> restarting standby api"; pkill -f 'uvicorn core.api_fa[s]t' 2>/dev/null; }
    fi
  fi

  # Shield health evaluation runs every 2nd loop (≈1 min): each evaluation
  # opens fresh SSH sessions and the Shield's sshd wedges under rapid probing.
  if [ "$SHIELD_PRIMARY" = "1" ] && [ $((_loop_n % 2)) -eq 0 ]; then
    # Shield primary, phone connector standby. Take over on 2 consecutive
    # shield failures; stand down after 2 consecutive healthy checks.
    if [ -f "$LOG_DIR/.shield_syncing" ]; then
      # go-live restarts the Shield; hold the phone connector up during the gap.
      shield_ok_streak=0; shield_fail_streak=0
      tunnel_healthy || { log "shield syncing -> phone tunnel held UP"; restart_tunnel; }
    elif shield_origin_ok; then
      shield_ok_streak=$((shield_ok_streak + 1)); shield_fail_streak=0
      if [ "$shield_ok_streak" -ge 2 ] && pgrep -f "$TUNNEL_MATCH" >/dev/null 2>&1; then
        log "shield healthy -> phone tunnel standby (stopping connector)"
        kill_tunnel
        rm -f "$TUNNEL_START_FILE"
      fi
    else
      shield_fail_streak=$((shield_fail_streak + 1)); shield_ok_streak=0
      if [ "$shield_fail_streak" -ge 2 ] && ! tunnel_healthy; then
        log "shield unhealthy -> phone tunnel fallback UP"
        restart_tunnel
      fi
    fi
  elif [ "$SHIELD_PRIMARY" != "1" ]; then
    if ! tunnel_healthy; then
      log "tunnel unhealthy/stale -> recycling cloudflared"
      restart_tunnel
    fi
  fi

  # Throttle shield sync to once per minute.
  if [ $((now % 60)) -lt "$INTERVAL" ]; then
    sync_shield_if_present
  fi

  # Enforce the Shield's never-sleep power policy from the phone (adb shell
  # uid), since the Shield's own keepawake service lacks the privileges to
  # apply settings/dumpsys/input. Non-blocking, self-locking.
  if [ -x "$SHIELD_KEEPER_SCRIPT" ] && [ $((now - last_shieldkeep)) -ge "$SHIELD_KEEP_INTERVAL" ]; then
    last_shieldkeep="$now"
    setsid bash -c "exec 8>&-; exec '$SHIELD_KEEPER_SCRIPT'" </dev/null >/dev/null 2>&1 &
  fi

  # Keep homepage syntheses fresh: regenerate only the clusters the homepage
  # currently flags as stale/missing, via the real LLM cascade. Non-blocking;
  # skipped while a previous run is still alive.
  if [ -f "$HOMEPAGE_SYNTH_SCRIPT" ] && [ -x "$HOMEPAGE_SYNTH_PY" ] && [ $((now - last_homepage_synth)) -ge "$HOMEPAGE_SYNTH_INTERVAL" ]; then
    last_homepage_synth="$now"
    echo "$now" > "$HOMEPAGE_SYNTH_STAMP"
    if ! { [ -f "$HOMEPAGE_SYNTH_PID" ] && kill -0 "$(cat "$HOMEPAGE_SYNTH_PID" 2>/dev/null)" 2>/dev/null; }; then
      log "homepage synthesis: starting scheduled refresh"
      setsid bash -c "exec 8>&-; exec '$HOMEPAGE_SYNTH_PY' '$HOMEPAGE_SYNTH_SCRIPT'" </dev/null >>"$HOMEPAGE_SYNTH_LOG" 2>&1 &
      echo "$!" > "$HOMEPAGE_SYNTH_PID"
    fi
  fi

  # Close the flock fd on the sleep child too, otherwise it holds the lock for
  # up to INTERVAL seconds after this watchdog exits and blocks a clean restart.
  sleep "$INTERVAL" 8>&-
done
