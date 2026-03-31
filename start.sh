#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# start.sh — Пресек  |  Modernized for PostgreSQL + Redis + Celery
# ─────────────────────────────────────────────────────────────────

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP="app.py"
SESSION="presek"
LOG_FILE="$APP_DIR/presek.log"
VENV="$APP_DIR/venv"
PYTHON="$VENV/bin/python3"
CELERY="$VENV/bin/celery"

# Load environment variables
if [ -f "$APP_DIR/.env" ]; then
  while read -r line || [ -n "$line" ]; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    export "$line"
  done < "$APP_DIR/.env"
fi

# ── Colours ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
info() { echo -e "${BLUE}→${RESET}  $*"; }
fail() { echo -e "${RED}✗  $*${RESET}"; exit 1; }
divider() { echo -e "${BOLD}────────────────────────────────────${RESET}"; }

echo ""
echo -e "${BOLD}  ПРЕСЕК — Македонски Вести (V2)${RESET}"
divider

# ── 1. Venv check ───────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  fail "Virtual environment not found at $VENV. Please create it first."
fi

# ── 2. Service checks ───────────────────────────────────────────
info "Checking required services..."
if ! pg_isready >/dev/null 2>&1; then
  warn "PostgreSQL does not seem to be running or accessible."
else
  ok "PostgreSQL is ready"
fi

if ! redis-cli ping >/dev/null 2>&1; then
  warn "Redis does not seem to be running or accessible."
else
  ok "Redis is ready"
fi

# ── --stop mode ──────────────────────────────────────────────────
if [ "$1" = "--stop" ]; then
  info "Stopping all Пресек components..."
  screen -S "$SESSION" -X quit 2>/dev/null && ok "Stopped screen session '$SESSION'"
  pkill -f "celery" && ok "Stopped Celery workers"
  pkill -f "trending_backfill.py" && ok "Stopped backfill"
  echo ""
  exit 0
fi

# ── 3. Kill existing ────────────────────────────────────────────
info "Cleaning up old processes..."
screen -S "$SESSION" -X quit 2>/dev/null
pkill -f "celery" 2>/dev/null
pkill -f "trending_backfill.py" 2>/dev/null
sleep 1

# ── 4. Start components in screen ───────────────────────────────
info "Starting components in screen session '$SESSION'..."

# Create the session and start the Flask app in the first window
screen -dmS "$SESSION" -t "app" bash -c "cd $APP_DIR && $PYTHON $APP; exec bash"
sleep 1

# Start Celery Worker
screen -S "$SESSION" -X screen -t "worker" bash -c "cd $APP_DIR && $CELERY -A tasks worker --loglevel=info >> $LOG_FILE 2>&1; exec bash"
sleep 1

# Start Celery Beat
screen -S "$SESSION" -X screen -t "beat" bash -c "cd $APP_DIR && $CELERY -A celery_app beat --loglevel=info >> $LOG_FILE 2>&1; exec bash"
sleep 1

# Start Trending Backfill
screen -S "$SESSION" -X screen -t "backfill" bash -c "cd $APP_DIR && $PYTHON trending_backfill.py; exec bash"

ok "All components started in screen session."

# ── 5. Health check ─────────────────────────────────────────────
info "Waiting for API to respond..."
for i in {1..10}; do
  sleep 2
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/api/news 2>/dev/null || echo "000")
  if [ "$HTTP" = "200" ]; then
    ok "Flask API is UP (HTTP 200)"
    break
  fi
  echo -n "."
done
echo ""

divider
echo -e "  ${CYAN}App:${RESET}       http://localhost:5000"
echo -e "  ${CYAN}Log:${RESET}       tail -f $LOG_FILE"
echo -e "  ${CYAN}Reattach:${RESET}  screen -r $SESSION"
echo -e "  ${CYAN}Windows:${RESET}   Ctrl+A, \" to switch between App/Worker/Beat/Backfill"
echo -e "  ${CYAN}Stop:${RESET}      ./start.sh --stop"
divider
echo ""
