#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_URL="${PUBLIC_URL:-https://presek.live/}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5001/api/health}"
ASTRO_URL="${ASTRO_URL:-http://127.0.0.1:3000}"
FASTAPI_URL="${FASTAPI_URL:-http://127.0.0.1:5001/api/health}"
HOME_API_URL="${HOME_API_URL:-http://127.0.0.1:5001/api/home}"
ADMIN_URL="${ADMIN_URL:-http://127.0.0.1:3000/admin}"
ADMIN_API_URL="${ADMIN_API_URL:-http://127.0.0.1:5001/api/admin/dashboard}"
ENABLE_FASTAPI_CHECK="${ENABLE_FASTAPI_CHECK:-1}"
ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-0}"
ENABLE_PUBLIC_SECURITY_HEADER_CHECK="${ENABLE_PUBLIC_SECURITY_HEADER_CHECK:-0}"
ENABLE_ADMIN_CHECK="${ENABLE_ADMIN_CHECK:-1}"
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
    _tmp="$(mktemp)"
    code="$(curl -sS -o "$_tmp" -w "%{http_code}" "$url" 2>/dev/null || true)"
    body="$(cat "$_tmp" 2>/dev/null || true)"
    rm -f "$_tmp" 2>/dev/null || true
    if [ "$code" = "$expected" ]; then
      if [ -z "$body_pattern" ] || printf "%s" "$body" | grep -Fq "$body_pattern"; then
        ok "$name responded with HTTP $code"
        return 0
      fi
    fi
    sleep "$SLEEP_SECONDS"
  done

  echo -e "${RED}x${RESET}  $name did not become healthy (last HTTP code: ${code:-none})" >&2
  return 1
}

wait_http_ok_header() {
  local name="$1"
  local url="$2"
  local header="$3"
  local expected="${4:-200}"
  local code=""

  info "Checking $name at $url"
  for _ in $(seq 1 "$MAX_ATTEMPTS"); do
    code="$(curl -sS -o /dev/null -w "%{http_code}" -H "$header" "$url" 2>/dev/null || true)"
    if [ "$code" = "$expected" ]; then
      ok "$name responded with HTTP $code"
      return 0
    fi
    sleep "$SLEEP_SECONDS"
  done

  echo -e "${RED}x${RESET}  $name did not become healthy (last HTTP code: ${code:-none})" >&2
  return 1
}

wait_header_contains() {
  local name="$1"
  local url="$2"
  local header_name="$3"
  local expected_fragment="$4"
  local headers=""

  info "Checking $name header at $url"
  for _ in $(seq 1 "$MAX_ATTEMPTS"); do
    headers="$(curl -sSI "$url" 2>/dev/null || true)"
    if printf "%s" "$headers" | grep -i "^${header_name}:" | grep -q "$expected_fragment"; then
      ok "$name header present"
      return 0
    fi
    sleep "$SLEEP_SECONDS"
  done

  echo -e "${RED}x${RESET}  $name header check failed for ${header_name}: ${expected_fragment}" >&2
  return 1
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
    _tmp="$(mktemp)"
    code="$(curl -sS -o "$_tmp" -w "%{http_code}" "$url" 2>/dev/null || true)"
    body="$(cat "$_tmp" 2>/dev/null || true)"
    rm -f "$_tmp" 2>/dev/null || true

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

  echo -e "${RED}x${RESET}  $name did not become healthy (last HTTP code: ${code:-none})" >&2
  return 1
}

main() {
  need_cmd curl
  need_cmd python3

  if [ -z "${PRESEK_ADMIN_TOKEN:-}" ] && [ -n "${APP_ROOT:-}" ] && [ -f "$APP_ROOT/shared/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$APP_ROOT/shared/.env"
    set +a
  fi

  wait_health_ready "API health" "$HEALTH_URL" 1 1
  wait_http_ok "Astro frontend" "$ASTRO_URL" 200

  if [ "$ENABLE_FASTAPI_CHECK" = "1" ]; then
    wait_health_ready "FastAPI health" "$FASTAPI_URL" 1 1
    wait_http_ok "Homepage API" "$HOME_API_URL" 200 "\"status\":\"success\""
  fi

  if [ "$ENABLE_ADMIN_CHECK" = "1" ]; then
    wait_http_ok "Admin page" "$ADMIN_URL" 200
    wait_http_ok "Admin API without token" "$ADMIN_API_URL" 403
    if [ -n "${PRESEK_ADMIN_TOKEN:-}" ]; then
      wait_http_ok_header "Admin API with token" "$ADMIN_API_URL" "X-Admin-Token: $PRESEK_ADMIN_TOKEN" 200
    else
      warn "Skipping admin token smoke check because PRESEK_ADMIN_TOKEN is not available"
    fi
  fi

  if [ "$ENABLE_PUBLIC_CHECK" = "1" ]; then
    public_base="${PUBLIC_URL%/}"
    # Allow 200 or 301 for the root domain as it often redirects to / or www.
    wait_http_ok "Public site" "$PUBLIC_URL" "200" || wait_http_ok "Public site" "$PUBLIC_URL" "301"
    wait_http_ok "Public admin page" "$public_base/admin" 200
    wait_http_ok "Public status page removed" "$public_base/status" 404
    if [ "$ENABLE_PUBLIC_SECURITY_HEADER_CHECK" = "1" ]; then
      wait_header_contains "Public site CSP" "$PUBLIC_URL" "Content-Security-Policy" "default-src 'self'"
      wait_header_contains "Public site HSTS" "$PUBLIC_URL" "Strict-Transport-Security" "max-age=63072000"
    else
      warn "Skipping public security header checks (set ENABLE_PUBLIC_SECURITY_HEADER_CHECK=1 to enable)"
    fi
  else
    warn "Skipping public URL check (set ENABLE_PUBLIC_CHECK=1 to enable)"
  fi

  ok "Smoke checks passed"
}

main "$@"
