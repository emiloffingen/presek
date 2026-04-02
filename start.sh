#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# start.sh — Пресек  |  PostgreSQL + Redis + Celery + Gunicorn
# ─────────────────────────────────────────────────────────────────

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION="presek"
LOG_FILE="$APP_DIR/presek.log"
VENV="$APP_DIR/venv"
PYTHON="$VENV/bin/python3"
GUNICORN="$VENV/bin/gunicorn"
CELERY="$VENV/bin/celery"

# ── Colours ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()      { echo -e "${GREEN}✓${RESET}  $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET}  $*"; }
info()    { echo -e "${BLUE}→${RESET}  $*"; }
fail()    { echo -e "${RED}✗  $*${RESET}"; exit 1; }
divider() { echo -e "${BOLD}────────────────────────────────────${RESET}"; }

echo ""
echo -e "${BOLD}  ПРЕСЕК — Македонски Вести${RESET}"
divider

# ── Load .env ────────────────────────────────────────────────────
if [ -f "$APP_DIR/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$APP_DIR/.env"
  set +a
  ok "Loaded .env"
else
  warn ".env not found — relying on environment variables"
fi

# ── --stop mode ──────────────────────────────────────────────────
if [ "$1" = "--stop" ]; then
  info "Stopping all Пресек components..."
  screen -S "$SESSION" -X quit 2>/dev/null && ok "Stopped screen session '$SESSION'" || warn "No screen session found"
  echo ""
  exit 0
fi

# ── Preflight checks ─────────────────────────────────────────────
info "Running preflight checks..."

[ -d "$VENV" ]      || fail "Virtualenv not found at $VENV. Run: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
[ -x "$GUNICORN" ]  || fail "Gunicorn not found at $GUNICORN."
[ -x "$CELERY" ]    || fail "Celery not found at $CELERY."

[ -n "$SECRET_KEY" ]   || fail "SECRET_KEY is not set. Add it to .env before starting."
[ -n "$DATABASE_URL" ] || fail "DATABASE_URL is not set. Add it to .env before starting."
[ -n "$REDIS_URL" ]    || { REDIS_URL="redis://localhost:6379/0"; warn "REDIS_URL not set, defaulting to $REDIS_URL"; }

if pg_isready -q 2>/dev/null; then
  ok "PostgreSQL is ready"
else
  warn "PostgreSQL may not be running (pg_isready failed)"
fi

if redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1; then
  ok "Redis is ready"
else
  warn "Redis may not be running"
fi

ok "Preflight complete"

# ── Kill existing ────────────────────────────────────────────────
info "Cleaning up old processes..."
screen -S "$SESSION" -X quit 2>/dev/null
# Also kill any stray gunicorn processes holding the port
pkill -f "gunicorn.*app:app" 2>/dev/null || true
sleep 3

# ── Init DB schema ───────────────────────────────────────────────
info "Verifying database schema..."
cd "$APP_DIR" && $PYTHON -c "from database import init_db; init_db()" && ok "Schema OK" || warn "Schema init had errors (check logs)"

# ── Start components in screen ───────────────────────────────────
info "Starting components in screen session '$SESSION'..."

# Window 1: Gunicorn (Flask app)
screen -dmS "$SESSION" -t "web" bash -c "
  cd $APP_DIR
  $GUNICORN app:app \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --threads 4 \
    --worker-class gthread \
    --timeout 60 \
    --keep-alive 5 \
    --access-logfile $LOG_FILE \
    --error-logfile $LOG_FILE \
    --log-level info
  exec bash"
sleep 1

# Window 2: Celery Worker
screen -S "$SESSION" -X screen -t "worker" bash -c "
  cd $APP_DIR
  $CELERY -A celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --logfile=$LOG_FILE 2>&1
  exec bash"
sleep 1

# Window 3: Celery Beat (scheduler)
screen -S "$SESSION" -X screen -t "beat" bash -c "
  cd $APP_DIR
  $CELERY -A celery_app beat \
    --loglevel=info \
    --logfile=$LOG_FILE 2>&1
  exec bash"
sleep 1

# Window 4: Trending Backfill
screen -S "$SESSION" -X screen -t "backfill" bash -c "
  cd $APP_DIR
  $PYTHON trending_backfill.py
  exec bash"

ok "All components launched"

# ── Health check ─────────────────────────────────────────────────
info "Waiting for API to respond..."
HEALTHY=0
for i in {1..15}; do
  sleep 2
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/api/health 2>/dev/null || echo "000")
  if [ "$HTTP" = "200" ]; then
    ok "API is UP (HTTP 200)"
    HEALTHY=1
    break
  fi
  echo -n "."
done
echo ""

if [ "$HEALTHY" = "0" ]; then
  warn "API did not respond after 30s — check: tail -f $LOG_FILE"
fi

divider
echo -e "  ${CYAN}App:${RESET}       http://localhost:5000"
echo -e "  ${CYAN}Health:${RESET}    http://localhost:5000/api/health"
echo -e "  ${CYAN}Log:${RESET}       tail -f $LOG_FILE"
echo -e "  ${CYAN}Reattach:${RESET}  screen -r $SESSION"
echo -e "  ${CYAN}Windows:${RESET}   Ctrl+A then \" — web / worker / beat / backfill"
echo -e "  ${CYAN}Stop:${RESET}      ./start.sh --stop"
divider
echo ""
