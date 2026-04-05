#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_URL="${PUBLIC_URL:-https://presek.live}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5000/api/health}"
ASTRO_URL="${ASTRO_URL:-http://127.0.0.1:3000}"
FASTAPI_URL="${FASTAPI_URL:-http://127.0.0.1:5001/api/health}"
ENABLE_FASTAPI_CHECK="${ENABLE_FASTAPI_CHECK:-1}"
ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-0}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-15}"
SLEEP_SECONDS="${SLEEP_SECONDS:-2}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
info() { echo -e "${BLUE}>${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

wait_http_ok() {
  local name="$1"
  local url="$2"
  local expected="${3:-200}"
  local body_pattern="${4:-}"
  local code=""
  local body=""

  info "Checking $name at $url"
  for _ in $(seq 1 "$MAX_ATTEMPTS"); do
    code="$(curl -sS -o /tmp/presek-smoke-body.$$ -w "%{http_code}" "$url" 2>/dev/null || true)"
    body="$(cat /tmp/presek-smoke-body.$$ 2>/dev/null || true)"
    rm -f /tmp/presek-smoke-body.$$ 2>/dev/null || true
    if [ "$code" = "$expected" ]; then
      if [ -z "$body_pattern" ] || printf "%s" "$body" | grep -q "$body_pattern"; then
        ok "$name responded with HTTP $code"
        return 0
      fi
    fi
    sleep "$SLEEP_SECONDS"
  done

  fail "$name did not become healthy (last HTTP code: ${code:-none})"
}

wait_health_ready() {
  local name="$1"
  local url="$2"
  local expect_db="${3:-1}"
  local expect_redis="${4:-1}"
  local code=""
  local body=""

  info "Checking $name at $url"
  for _ in $(seq 1 "$MAX_ATTEMPTS"); do
    code="$(curl -sS -o /tmp/presek-smoke-body.$$ -w "%{http_code}" "$url" 2>/dev/null || true)"
    body="$(cat /tmp/presek-smoke-body.$$ 2>/dev/null || true)"
    rm -f /tmp/presek-smoke-body.$$ 2>/dev/null || true

    if [ "$code" = "200" ]; then
      if BODY="$body" EXPECT_DB="$expect_db" EXPECT_REDIS="$expect_redis" python3 - <<'PY'
import json, os, sys
body = os.environ.get("BODY", "")
expect_db = os.environ.get("EXPECT_DB") == "1"
expect_redis = os.environ.get("EXPECT_REDIS") == "1"
try:
    data = json.loads(body)
except Exception:
    sys.exit(1)
if "status" not in data:
    sys.exit(1)
if expect_db and not data.get("database", {}).get("ok"):
    sys.exit(1)
if expect_redis and not data.get("redis", {}).get("ok"):
    sys.exit(1)
sys.exit(0)
PY
      then
        ok "$name responded healthy"
        return 0
      fi
    fi
    sleep "$SLEEP_SECONDS"
  done

  fail "$name did not become healthy (last HTTP code: ${code:-none})"
}

main() {
  need_cmd curl
  need_cmd python3

  wait_health_ready "Flask health" "$HEALTH_URL" 1 1
  wait_http_ok "Astro frontend" "$ASTRO_URL" 200 "Пресек"

  if [ "$ENABLE_FASTAPI_CHECK" = "1" ]; then
    wait_health_ready "FastAPI health" "$FASTAPI_URL" 1 1
  fi

  if [ "$ENABLE_PUBLIC_CHECK" = "1" ]; then
    wait_http_ok "Public site" "$PUBLIC_URL" 200 "Пресек"
  else
    warn "Skipping public URL check (set ENABLE_PUBLIC_CHECK=1 to enable)"
  fi

  ok "Smoke checks passed"
}

main "$@"
