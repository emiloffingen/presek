#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# start.sh — Пресек  |  Safe restart script for Termux / Shield TV
#
# Usage:
#   ./start.sh           normal restart
#   ./start.sh --fresh   kill screen session and start completely clean
#   ./start.sh --stop    stop the app without restarting
#   ./start.sh --status  show current status and exit
# ─────────────────────────────────────────────────────────────────

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP="app.py"
SESSION="presek"
DIGESTS_DIR="$APP_DIR/digests"
LOG_FILE="$APP_DIR/presek.log"
LOG_MAX_KB=2048   # rotate log when it exceeds 2 MB

# Load environment variables if .env exists
if [ -f "$APP_DIR/.env" ]; then
    export $(grep -v '^#' "$APP_DIR/.env" | xargs)
fi

# ── Colours ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
info() { echo -e "${BLUE}→${RESET}  $*"; }
fail() { echo -e "${RED}✗  $*${RESET}"; exit 1; }
dim()  { echo -e "\033[2m   $*${RESET}"; }
divider() { echo -e "${BOLD}────────────────────────────────────${RESET}"; }

echo ""
echo -e "${BOLD}  ПРЕСЕК — Македонски Вести${RESET}"
divider

# ── --status mode ────────────────────────────────────────────────
if [ "$1" = "--status" ]; then
  info "Session:"
  if screen -list 2>/dev/null | grep -q "$SESSION"; then
    ok "Screen session '$SESSION' is running"
  else
    warn "Screen session '$SESSION' is NOT running"
  fi
  info "Health:"
  if command -v curl &>/dev/null; then
    RESP=$(curl -s http://localhost:5000/api/health 2>/dev/null)
    if [ -n "$RESP" ]; then
      ok "Flask is responding"
      echo "$RESP" | python3 -c "
import sys, json
try:
  d = json.load(sys.stdin)
  print(f'   Status  : {d.get(\"status\",\"?\")}')
  print(f'   Uptime  : {d.get(\"uptime\",\"?\")}')
  print(f'   Articles: {d.get(\"database\",{}).get(\"article_count\",\"?\")}')
except: pass
" 2>/dev/null || true
    else
      warn "Flask is not responding"
    fi
  fi
  echo ""
  exit 0
fi

# ── --stop mode ──────────────────────────────────────────────────
if [ "$1" = "--stop" ]; then
  info "Stopping Пресек..."
  if screen -list 2>/dev/null | grep -q "$SESSION"; then
    screen -S "$SESSION" -X quit 2>/dev/null || true
    sleep 1
    ok "Session '$SESSION' stopped"
  else
    warn "No session '$SESSION' found"
  fi
  PIDS=$(pgrep -f "python3 $APP" 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    kill $PIDS 2>/dev/null || true
    ok "Killed process(es): $PIDS"
  fi
  echo ""
  exit 0
fi

# ═══════════════════════════════════════════════════════════════════
# NORMAL / --fresh START
# ═══════════════════════════════════════════════════════════════════

cd "$APP_DIR" || fail "Cannot cd to $APP_DIR"

# ── 0. Termux wake lock (keep alive on Android) ─────────────────
if command -v termux-wake-lock &>/dev/null; then
  termux-wake-lock 2>/dev/null && ok "Wake lock acquired — Android won't kill Termux" \
    || warn "Wake lock failed — app may be killed in background"
else
  warn "termux-wake-lock not found — install termux-api package for background persistence"
fi

# ── 1. File checks ───────────────────────────────────────────────
info "Checking files..."

[ -f "$APP" ]                       || fail "$APP not found in $APP_DIR"
[ -f "clustering.py" ]              || warn "clustering.py missing"
[ -f "categories.py" ]              || warn "categories.py missing"
[ -f "trending.py" ]                || warn "trending.py missing"
[ -f "health.py" ]                  || warn "health.py missing"
[ -f "notifier.py" ]                || warn "notifier.py missing"
[ -f "digest.py" ]                  || warn "digest.py missing"
[ -f "templates/index.html" ]       || warn "templates/index.html missing"
[ -f "templates/stats.html" ]       || warn "templates/stats.html missing"
[ -f "templates/cluster.html" ]     || warn "templates/cluster.html missing"
[ -f "templates/izvori.html" ]      || warn "templates/izvori.html missing"
[ -f "sw.js" ]                      || warn "sw.js missing — PWA offline disabled"
[ -f "static/manifest.json" ]       || warn "static/manifest.json missing — PWA install disabled"

ok "File check complete"

# ── 2. Environment checks ────────────────────────────────────────
info "Checking environment..."
MISSING_KEYS=0

if [ -z "$GOOGLE_API_KEY" ]; then
  warn "GOOGLE_API_KEY not set — Gemini summaries unavailable"
  MISSING_KEYS=$((MISSING_KEYS+1))
else
  ok "GOOGLE_API_KEY is set"
fi

if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
  warn "CLOUDFLARE_API_TOKEN not set — Workers AI unavailable"
  MISSING_KEYS=$((MISSING_KEYS+1))
else
  ok "CLOUDFLARE_API_TOKEN is set"
fi

if [ -z "$CLOUDFLARE_ACCOUNT_ID" ]; then
  warn "CLOUDFLARE_ACCOUNT_ID not set — Workers AI URL may be invalid"
else
  ok "CLOUDFLARE_ACCOUNT_ID = $CLOUDFLARE_ACCOUNT_ID"
fi

if [ -z "$NTFY_TOPIC" ]; then
  warn "NTFY_TOPIC not set — push notifications disabled"
else
  ok "NTFY_TOPIC = $NTFY_TOPIC"
fi

[ $MISSING_KEYS -eq 1 ] && warn "Gemini key missing — AI features unavailable"

# ── 3. Python & syntax check ─────────────────────────────────────
info "Checking Python..."
PYTHON_VER=$(python3 --version 2>&1)
ok "$PYTHON_VER"
python3 -m py_compile "$APP" 2>/dev/null \
  && ok "app.py syntax OK" \
  || fail "app.py has syntax errors — run 'python3 -m py_compile app.py' to see them"

# ── 4. Kill orphaned processes ───────────────────────────────────
info "Checking for orphaned processes..."
PIDS=$(pgrep -f "python3 $APP" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  info "Killing orphaned process(es): $PIDS"
  kill $PIDS 2>/dev/null || true
  sleep 1
  ok "Orphan(s) killed"
else
  ok "No orphaned processes"
fi

# ── 5. Free port 5000 ───────────────────────────────────────────
info "Checking port 5000..."
if command -v fuser &>/dev/null 2>&1; then
  if fuser 5000/tcp &>/dev/null 2>&1; then
    warn "Port 5000 in use — freeing..."
    fuser -k 5000/tcp 2>/dev/null || true
    sleep 1
    ok "Port 5000 freed"
  else
    ok "Port 5000 is free"
  fi
else
  ok "Port 5000 check skipped (fuser unavailable)"
fi

# ── 6. Directories ──────────────────────────────────────────────
mkdir -p "$DIGESTS_DIR" "$APP_DIR/static" "$APP_DIR/templates"
ok "Directories ready"

# ── 7. Log rotation ─────────────────────────────────────────────
if [ -f "$LOG_FILE" ]; then
  LOG_KB=$(du -k "$LOG_FILE" 2>/dev/null | cut -f1 || echo 0)
  if [ "${LOG_KB:-0}" -gt "$LOG_MAX_KB" ]; then
    mv "$LOG_FILE" "${LOG_FILE}.old"
    ok "Log rotated (was ${LOG_KB}kB) → presek.log.old"
  else
    dim "Log is ${LOG_KB:-?}kB (max ${LOG_MAX_KB}kB)"
  fi
fi

# ── 8. DB quick stats ───────────────────────────────────────────
if [ -f "presek.db" ]; then
  DB_KB=$(du -k presek.db 2>/dev/null | cut -f1 || echo "?")
  ARTICLE_COUNT=$(python3 -c "
import sqlite3
try:
    c = sqlite3.connect('presek.db', timeout=3)
    n = c.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
    c.close()
    print(n)
except: print('?')
" 2>/dev/null)
  ok "DB: ${ARTICLE_COUNT} articles · ${DB_KB:-?}kB"
else
  warn "presek.db not found — will be created on first run"
fi

# ── 9. Screen session ───────────────────────────────────────────
info "Managing screen session..."

if screen -list 2>/dev/null | grep -q "$SESSION"; then
  if [ "$1" = "--fresh" ]; then
    info "Killing existing session '$SESSION' (--fresh)..."
    screen -S "$SESSION" -X quit 2>/dev/null || true
    sleep 1
    ok "Old session removed"
  else
    info "Session '$SESSION' exists — restarting app inside it..."
    screen -S "$SESSION" -X stuff $'\003'
    sleep 2
    screen -S "$SESSION" -X stuff "python3 $APP\n"
    sleep 3

    if command -v curl &>/dev/null; then
      HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/api/health 2>/dev/null || echo "000")
      if [ "$HTTP" = "200" ]; then
        ok "Flask responding (HTTP 200)"
      else
        warn "Flask not yet responding (HTTP $HTTP) — still loading feeds"
      fi
    fi

    echo ""
    echo -e "${GREEN}${BOLD}Пресек е активен.${RESET}"
    divider
    echo -e "  ${CYAN}App:${RESET}       http://localhost:5000"
    echo -e "  ${CYAN}Stats:${RESET}     http://localhost:5000/stats"
    echo -e "  ${CYAN}Извори:${RESET}    http://localhost:5000/izvori"
    echo -e "  ${CYAN}Log:${RESET}       tail -f $LOG_FILE"
    echo -e "  ${CYAN}Reattach:${RESET}  screen -r $SESSION"
    echo -e "  ${CYAN}Status:${RESET}    ./start.sh --status"
    echo -e "  ${CYAN}Stop:${RESET}      ./start.sh --stop"
    echo ""
    exit 0
  fi
fi

# ── 10. Fresh screen session ────────────────────────────────────
info "Starting new screen session '$SESSION'..."
screen -dmS "$SESSION" bash -c "cd $APP_DIR && python3 $APP; exec bash"
sleep 2

if screen -list 2>/dev/null | grep -q "$SESSION"; then
  ok "Screen session '$SESSION' started"
else
  fail "Screen session failed — run 'python3 $APP' manually to see the error"
fi

# ── 11. Health check with retries ───────────────────────────────
info "Waiting for Flask to come up..."
FLASK_UP=0
for i in 1 2 3 4 5; do
  sleep 2
  if command -v curl &>/dev/null; then
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/api/health 2>/dev/null || echo "000")
    if [ "$HTTP" = "200" ]; then
      ok "Flask is up (HTTP 200) — attempt $i/5"
      FLASK_UP=1
      break
    else
      dim "Attempt $i/5 — HTTP $HTTP"
    fi
  else
    dim "curl not available — skipping health check"
    FLASK_UP=1
    break
  fi
done

[ "$FLASK_UP" = "0" ] && warn "Flask not responding after 10s — check 'screen -r $SESSION' for errors"

# ── Done ────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Пресек е активен.${RESET}"
divider
echo -e "  ${CYAN}App:${RESET}       http://localhost:5000"
echo -e "  ${CYAN}Stats:${RESET}     http://localhost:5000/stats"
echo -e "  ${CYAN}Извори:${RESET}    http://localhost:5000/izvori"
echo -e "  ${CYAN}Log:${RESET}       tail -f $LOG_FILE"
echo -e "  ${CYAN}Reattach:${RESET}  screen -r $SESSION"
echo -e "  ${CYAN}Status:${RESET}    ./start.sh --status"
echo -e "  ${CYAN}Stop:${RESET}      ./start.sh --stop"
echo -e "  ${CYAN}Detach:${RESET}    Ctrl+A, D"
echo ""
