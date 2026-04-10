#!/bin/bash
set -euo pipefail

# start.sh — Presek local/manual fallback launcher

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION="${SCREEN_SESSION_NAME:-presek}"
VENV="$APP_DIR/venv"
PYTHON="$VENV/bin/python3"
CELERY="$VENV/bin/celery"
UVICORN="$VENV/bin/uvicorn"
LOG_DIR="$APP_DIR/logs"
WEB_DIR="$APP_DIR/web"
ROOT_PYTHON="${ROOT_PYTHON:-python3}"
BOOTSTRAP="${BOOTSTRAP:-1}"
FORCE_PY_DEPS="${FORCE_PY_DEPS:-0}"
FORCE_WEB_BUILD="${FORCE_WEB_BUILD:-0}"
ENSURE_ASTRO_BUILD="$APP_DIR/deploy/ensure_astro_build.sh"

WEB_LOG="$LOG_DIR/web.log"
WORKER_LOG="$LOG_DIR/worker.log"
BEAT_LOG="$LOG_DIR/beat.log"
FASTAPI_LOG="$LOG_DIR/fastapi.log"
ASTRO_LOG="$LOG_DIR/astro.log"
BACKFILL_LOG="$LOG_DIR/backfill.log"

ENABLE_FASTAPI="${ENABLE_FASTAPI:-1}"
ENABLE_ASTRO="${ENABLE_ASTRO:-1}"
ENABLE_BACKFILL="${ENABLE_BACKFILL:-0}"
PUBLIC_URL="${PUBLIC_URL:-https://presek.live}"
FASTAPI_BIND_HOST="${FASTAPI_BIND_HOST:-127.0.0.1}"
ASTRO_BIND_HOST="${ASTRO_BIND_HOST:-127.0.0.1}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()      { echo -e "${GREEN}✓${RESET}  $*"; }
warn()    { echo -e "${YELLOW}!${RESET}  $*"; }
info()    { echo -e "${BLUE}>${RESET}  $*"; }
fail()    { echo -e "${RED}x${RESET}  $*"; exit 1; }
divider() { echo -e "${BOLD}────────────────────────────────────${RESET}"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

stop_matching_processes() {
  local pattern="$1"
  if pkill -f "$pattern" >/dev/null 2>&1; then
    ok "Stopped processes matching: $pattern"
  else
    warn "No running processes matched: $pattern"
  fi
}

maybe_npm_install() {
  if [ -f "$WEB_DIR/package-lock.json" ]; then
    (cd "$WEB_DIR" && npm ci)
  else
    (cd "$WEB_DIR" && npm install)
  fi
}

ensure_astro_build() {
  if [ "$ENABLE_ASTRO" != "1" ]; then
    return
  fi

  [ -x "$ENSURE_ASTRO_BUILD" ] || chmod 755 "$ENSURE_ASTRO_BUILD"
  APP_ROOT="$APP_DIR" WEB_DIR="$WEB_DIR" FORCE_WEB_BUILD="$FORCE_WEB_BUILD" "$ENSURE_ASTRO_BUILD"
}

bootstrap_runtime() {
  if [ "$BOOTSTRAP" != "1" ]; then
    return
  fi

  info "Bootstrapping runtime dependencies..."

  require_cmd "$ROOT_PYTHON"

  if [ ! -d "$VENV" ]; then
    info "Creating Python virtualenv at $VENV"
    "$ROOT_PYTHON" -m venv "$VENV"
  fi

  if [ ! -x "$PYTHON" ]; then
    fail "Python virtualenv exists but $PYTHON is missing"
  fi

  if [ "$FORCE_PY_DEPS" = "1" ] || [ ! -x "$CELERY" ] || [ ! -x "$UVICORN" ]; then
    info "Installing Python dependencies"
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -r "$APP_DIR/requirements.txt"
  fi

  if [ "$ENABLE_ASTRO" = "1" ]; then
    require_cmd node
    require_cmd npm
    [ -f "$WEB_DIR/package.json" ] || fail "Missing Astro package.json in $WEB_DIR"

    if [ ! -d "$WEB_DIR/node_modules" ]; then
      info "Installing frontend dependencies"
      maybe_npm_install
    fi

    ensure_astro_build
  fi

  ok "Bootstrap complete"
}

screen_session_exists() {
  screen -list 2>/dev/null | grep -q "[[:space:]]${SESSION}[[:space:]]"
}

list_screen_sessions() {
  (screen -list 2>/dev/null || true) | awk -v session="$SESSION" '$1 ~ ("\\." session "$") { print $1 }'
}

load_env() {
  if [ -f "$APP_DIR/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$APP_DIR/.env"
    set +a
    ok "Loaded .env"
  else
    warn ".env not found, relying on environment variables"
  fi
}

show_port_usage() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -lptn "sport = :$port" 2>/dev/null || true
  fi
}

systemd_unit_active() {
  local unit="$1"
  command -v systemctl >/dev/null 2>&1 || return 1
  [ "$(systemctl is-active "$unit" 2>/dev/null || true)" = "active" ]
}

assert_manual_mode_safe() {
  local active_units=()
  local units=(
    presek.target
    presek-fastapi.service
    presek-astro.service
    presek-worker.service
    presek-beat.service
  )
  local unit

  for unit in "${units[@]}"; do
    if systemd_unit_active "$unit"; then
      active_units+=("$unit")
    fi
  done

  if [ "${#active_units[@]}" -gt 0 ]; then
    fail "Refusing to run start.sh while production systemd units are active: ${active_units[*]}. Stop them with systemctl first, or manage the app through systemd + nginx."
  fi
}

port_pids() {
  local port="$1"
  if ! command -v ss >/dev/null 2>&1; then
    return 0
  fi

  (
    ss -lptn "sport = :$port" 2>/dev/null \
      | grep -o 'pid=[0-9]\+' \
      | cut -d= -f2 \
      | sort -u
  ) || true
}

force_free_port() {
  local port="$1"
  local pids
  pids="$(port_pids "$port")"

  if [ -z "$pids" ]; then
    warn "No listening process found on port $port"
    return 0
  fi

  warn "Port $port is busy; stopping owning processes:"
  show_port_usage "$port"

  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    kill "$pid" >/dev/null 2>&1 || true
  done <<< "$pids"

  sleep 2

  pids="$(port_pids "$port")"
  if [ -n "$pids" ]; then
    warn "Some processes on port $port ignored SIGTERM; sending SIGKILL"
    while IFS= read -r pid; do
      [ -n "$pid" ] || continue
      kill -9 "$pid" >/dev/null 2>&1 || true
    done <<< "$pids"
    sleep 1
  fi

  if [ -n "$(port_pids "$port")" ]; then
    fail "Could not free port $port"
  fi

  ok "Freed port $port"
}

ensure_port_free() {
  local port="$1"
  if ! command -v ss >/dev/null 2>&1; then
    warn "ss not available; skipping port ownership check for $port"
    return
  fi

  if ss -lptn "sport = :$port" 2>/dev/null | tail -n +2 | grep -q .; then
    warn "Port $port is already in use:"
    show_port_usage "$port"
    fail "Refusing to start while port $port belongs to another process"
  fi
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local expected="${3:-200}"
  local attempts="${4:-15}"
  local delay="${5:-2}"
  local code=""

  info "Waiting for $name at $url"
  for _ in $(seq 1 "$attempts"); do
    code="$(curl -sS -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || true)"
    if [ "$code" = "$expected" ]; then
      ok "$name is UP (HTTP $code)"
      return 0
    fi
    sleep "$delay"
  done

  warn "$name did not become healthy (last HTTP code: ${code:-none})"
  return 1
}

start_window() {
  local title="$1"
  local command="$2"

  if ! screen_session_exists; then
    screen -dmS "$SESSION" -t "$title" bash -lc "$command"
  else
    screen -S "$SESSION" -X screen -t "$title" bash -lc "$command"
  fi
}

stop_session() {
  local sessions
  sessions="$(list_screen_sessions)"

  if [ -n "$sessions" ]; then
    info "Stopping screen sessions for '$SESSION'..."
    while IFS= read -r session_id; do
      [ -n "$session_id" ] || continue
      screen -S "$session_id" -X quit || true
    done <<< "$sessions"
    sleep 2
    ok "Stopped screen sessions for '$SESSION'"
  else
    warn "No screen session named '$SESSION' was found"
  fi
}

cleanup_stale_processes() {
  info "Cleaning up stale app processes..."
  stop_matching_processes "uvicorn.*api_fast:app"
  stop_matching_processes "entry.mjs"
  [ "$ENABLE_FASTAPI" = "1" ] && force_free_port 5001
  [ "$ENABLE_ASTRO" = "1" ] && force_free_port 3000
  sleep 2
}

print_summary() {
  divider
  echo -e "  ${CYAN}Public URL:${RESET}      $PUBLIC_URL"
  if [ "$ENABLE_FASTAPI" = "1" ]; then
    echo -e "  ${CYAN}FastAPI:${RESET}         http://127.0.0.1:5001"
  fi
  if [ "$ENABLE_ASTRO" = "1" ]; then
    echo -e "  ${CYAN}Astro Frontend:${RESET}  http://127.0.0.1:3000"
  fi
  echo -e "  ${CYAN}Logs:${RESET}            $LOG_DIR"
  echo -e "  ${CYAN}Reattach:${RESET}        screen -r $SESSION"
  echo -e "  ${CYAN}Stop:${RESET}            ./start.sh --stop"
  echo -e "  ${CYAN}Production:${RESET}      systemd + nginx (see deploy/)"
  divider
}

echo ""
echo -e "${BOLD}  PRESEK${RESET}"
divider

mkdir -p "$LOG_DIR"
touch "$WEB_LOG" "$WORKER_LOG" "$BEAT_LOG"

load_env

warn "start.sh is a local/manual fallback launcher. Supported production runtime is systemd + nginx."
assert_manual_mode_safe

case "${1:-}" in
  --stop)
    stop_session
    exit 0
    ;;
  --restart)
    stop_session
    cleanup_stale_processes
    ;;
  --status)
    if screen_session_exists; then
      ok "Screen session '$SESSION' is running"
      screen -S "$SESSION" -Q windows || true
    else
      warn "Screen session '$SESSION' is not running"
    fi
    exit 0
    ;;
  --build)
    load_env
    bootstrap_runtime
    exit 0
    ;;
esac

bootstrap_runtime

info "Running preflight checks..."

require_cmd screen
require_cmd curl
require_cmd ss
[ -x "$PYTHON" ] || fail "Python not found at $PYTHON"
[ -x "$CELERY" ] || fail "Celery not found at $CELERY"
[ -f "$APP_DIR/celery_app.py" ] || fail "Missing Celery entrypoint: $APP_DIR/celery_app.py"

[ -n "${SECRET_KEY:-}" ] || fail "SECRET_KEY is not set"
[ -n "${DATABASE_URL:-}" ] || fail "DATABASE_URL is not set"
[ -n "${REDIS_URL:-}" ] || { export REDIS_URL="redis://localhost:6379/0"; warn "REDIS_URL not set, defaulting to $REDIS_URL"; }

if command -v pg_isready >/dev/null 2>&1; then
  if pg_isready -q; then
    ok "PostgreSQL is ready"
  else
    warn "pg_isready reported that PostgreSQL is not ready"
  fi
else
  warn "pg_isready not found; skipping PostgreSQL readiness probe"
fi

if command -v redis-cli >/dev/null 2>&1; then
  if redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1; then
    ok "Redis is ready"
  else
    warn "Redis ping failed for $REDIS_URL"
  fi
else
  warn "redis-cli not found; skipping Redis readiness probe"
fi

if [ "$ENABLE_FASTAPI" = "1" ]; then
  [ -x "$UVICORN" ] || fail "Uvicorn not found at $UVICORN"
  [ -f "$APP_DIR/api_fast.py" ] || fail "Missing FastAPI entrypoint: $APP_DIR/api_fast.py"
  touch "$FASTAPI_LOG"
fi

if [ "$ENABLE_ASTRO" = "1" ]; then
  require_cmd node
  require_cmd npm
  [ -f "$WEB_DIR/package.json" ] || fail "Missing Astro package.json in $WEB_DIR"
  ensure_astro_build
  [ -f "$WEB_DIR/dist/server/entry.mjs" ] || fail "Missing Astro server build after ensure step"
  touch "$ASTRO_LOG"
fi

if [ "$ENABLE_BACKFILL" = "1" ]; then
  [ -f "$APP_DIR/trending_backfill.py" ] || fail "ENABLE_BACKFILL=1 but trending_backfill.py is missing"
  touch "$BACKFILL_LOG"
fi

ok "Preflight complete"

if screen_session_exists; then
  info "Existing session detected; stopping it first"
  stop_session
fi

[ "$ENABLE_FASTAPI" = "1" ] && ensure_port_free 5001
[ "$ENABLE_ASTRO" = "1" ] && ensure_port_free 3000

info "Verifying database schema..."
if (cd "$APP_DIR" && "$PYTHON" -c "from database import init_db; init_db()"); then
  ok "Schema OK"
else
  fail "Database schema verification failed"
fi

info "Starting services in screen session '$SESSION'..."

start_window "worker" "cd '$APP_DIR' && exec '$CELERY' -A celery_app worker --loglevel=info --concurrency=4 --logfile='$WORKER_LOG'"
sleep 1

start_window "beat" "cd '$APP_DIR' && exec '$CELERY' -A celery_app beat --loglevel=info --logfile='$BEAT_LOG'"
sleep 1

if [ "$ENABLE_FASTAPI" = "1" ]; then
  start_window "fastapi" "cd '$APP_DIR' && exec '$UVICORN' api_fast:app --host '$FASTAPI_BIND_HOST' --port 5001 --workers 2 >> '$FASTAPI_LOG' 2>&1"
  sleep 1
fi

if [ "$ENABLE_ASTRO" = "1" ]; then
  start_window "astro" "cd '$WEB_DIR' && PORT=3000 HOST='$ASTRO_BIND_HOST' exec node ./dist/server/entry.mjs >> '$ASTRO_LOG' 2>&1"
  sleep 1
fi

if [ "$ENABLE_BACKFILL" = "1" ]; then
  start_window "backfill" "cd '$APP_DIR' && exec '$PYTHON' trending_backfill.py >> '$BACKFILL_LOG' 2>&1"
  sleep 1
fi

ok "Launch commands submitted"

if [ "$ENABLE_FASTAPI" = "1" ]; then
  wait_for_http "FastAPI" "http://127.0.0.1:5001/api/health"
fi

if [ "$ENABLE_ASTRO" = "1" ]; then
  wait_for_http "Astro frontend" "http://127.0.0.1:3000"
fi

print_summary
echo ""
