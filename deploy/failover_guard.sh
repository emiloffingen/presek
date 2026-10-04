#!/bin/bash
# failover_guard.sh - automatic origin failover between the Shield (primary) and
# the phone (standby).
#
# Both hosts run cloudflared connectors to the same tunnel. This loop keeps the
# phone's standby origin warm (Redis + FastAPI + Astro) and connects the phone's
# connector only while the Shield is unhealthy, with 2-check hysteresis so a
# single blip cannot flap the origin.
#
# The Shield is probed over SSH (Tailscale) rather than adb port-forwards: the
# Android adb binary cannot start its server inside this proot container, which
# is why the full presek_watchdog.sh could never run here.
set -u

APP_DIR="${PRESEK_APP_DIR:-/root/presek}"
LOG="$APP_DIR/logs/failover_guard.log"
LOCK="$APP_DIR/logs/.failover_guard.lock"
CF_LOG="$APP_DIR/logs/cloudflared.log"
INTERVAL="${FAILOVER_INTERVAL:-30}"
SYNC_SCRIPT="$APP_DIR/deploy/sync_shield.sh"
SYNC_INTERVAL="${SHIELD_SYNC_INTERVAL:-300}"
SHIELD_SSH="${SHIELD_SSH:-u0_a106@100.77.135.12}"
SHIELD_PORT="${SHIELD_PORT:-8022}"
SSH_KEY="${SSH_KEY:-/root/.ssh/termux_test}"
TUNNEL_MATCH="/root/.cloudflared/config.yml run"
REDIS_PASS="$(sed -n 's%^REDIS_URL=redis://:\([^@]*\)@.*%\1%p' "$APP_DIR/.env" 2>/dev/null | head -1)"

mkdir -p "$(dirname "$LOG")"
exec 9>"$LOCK"
flock -n 9 || exit 0

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

ssh_shield() {
  timeout 15 ssh -i "$SSH_KEY" -p "$SHIELD_PORT" \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o BatchMode=yes -o ConnectTimeout=6 "$SHIELD_SSH" "$@"
}

# Healthy = Shield astro + api answer AND its tunnel has ready connections.
shield_healthy() {
  ssh_shield 'curl -sf -m4 -o /dev/null http://127.0.0.1:3000/ && \
              curl -sf -m4 -o /dev/null http://127.0.0.1:5001/api/health && \
              curl -s  -m4 http://127.0.0.1:20241/ready' 2>/dev/null \
    | grep -q '"readyConnections":[1-9]'
}

tunnel_up() { pgrep -f "$TUNNEL_MATCH" >/dev/null 2>&1; }

stop_tunnel() {
  tunnel_up || return 0
  log "shield healthy -> phone connector standby (stopping)"
  pkill -f "$TUNNEL_MATCH" 2>/dev/null
  sleep 3
  pkill -9 -f "$TUNNEL_MATCH" 2>/dev/null
}

start_tunnel() {
  tunnel_up && return 0
  log "shield unhealthy -> phone connector UP"
  setsid bash -c "exec 9>&-; exec cloudflared tunnel --config /root/.cloudflared/config.yml run" \
    </dev/null >>"$CF_LOG" 2>&1 &
}

spawn() { # name marker cmd
  local name="$1" marker="$2" cmd="$3"
  pgrep -f "$marker" >/dev/null 2>&1 && return 0
  log "starting standby origin: $name"
  setsid bash -c "exec 9>&-; set -a; . '$APP_DIR/.env'; set +a; cd '$APP_DIR'; export PYTHONPATH='$APP_DIR'; $cmd" \
    </dev/null >>"$APP_DIR/logs/$name.out" 2>&1 &
}

ensure_standby_origin() {
  if ! redis-cli -a "$REDIS_PASS" --no-auth-warning ping >/dev/null 2>&1; then
    log "redis down -> starting"
    ( exec 9>&-; redis-server --daemonize yes --dir /root --requirepass "$REDIS_PASS" --logfile "$APP_DIR/logs/redis.log" )
    sleep 1
  fi
  curl -sf -m3 -o /dev/null http://127.0.0.1:5001/api/health || \
    spawn fastapi 'uvicorn core.api_fast' \
      "exec $APP_DIR/.venv/bin/uvicorn core.api_fast:app --host 127.0.0.1 --port 5001 --workers ${UVICORN_WORKERS:-1}"
  curl -sf -m3 -o /dev/null http://127.0.0.1:3000/ || \
    spawn astro 'node ./dist/server/entry.mjs' \
      "cd $APP_DIR/web && PORT=3000 HOST=127.0.0.1 exec node ./dist/server/entry.mjs"
}

ok_streak=0; fail_streak=0; last_sync=0
log "failover guard started (interval ${INTERVAL}s, shield ${SHIELD_SSH})"
while true; do
  now=$(date +%s)
  ensure_standby_origin
  if shield_healthy; then
    ok_streak=$((ok_streak + 1)); fail_streak=0
    [ "$ok_streak" -ge 2 ] && stop_tunnel
    # Ship the current build to the Shield (throttled, detached) so a return
    # from failover cannot leave it on a stale dist.
    if [ -x "$SYNC_SCRIPT" ] && [ $((now - last_sync)) -ge "$SYNC_INTERVAL" ]; then
      last_sync=$now
      setsid bash -c "exec 9>&-; exec '$SYNC_SCRIPT'" </dev/null >>"$APP_DIR/logs/shield_sync.out" 2>&1 &
    fi
  else
    fail_streak=$((fail_streak + 1)); ok_streak=0
    [ "$fail_streak" -ge 2 ] && start_tunnel
  fi
  sleep "$INTERVAL"
done
