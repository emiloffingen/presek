#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_URL="${PUBLIC_URL:-https://presek.live/}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5001/api/health}"
ASTRO_URL="${ASTRO_URL:-http://127.0.0.1:3000}"
FASTAPI_URL="${FASTAPI_URL:-http://127.0.0.1:5001/api/health}"
HOME_API_URL="${HOME_API_URL:-http://127.0.0.1:5001/api/home}"
MK_HOME_API_URL="${MK_HOME_API_URL:-http://127.0.0.1:5001/api/home?lang=mk}"
SR_HOME_API_URL="${SR_HOME_API_URL:-http://127.0.0.1:5001/api/home?lang=sr}"
CLUSTER_API_BASE="${CLUSTER_API_BASE:-http://127.0.0.1:5001/api/cluster}"
ADMIN_URL="${ADMIN_URL:-http://127.0.0.1:3000/admin}"
ADMIN_API_URL="${ADMIN_API_URL:-http://127.0.0.1:5001/api/admin/dashboard}"
ENABLE_FASTAPI_CHECK="${ENABLE_FASTAPI_CHECK:-1}"
ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-0}"
ENABLE_MK_PUBLIC_CHECK="${ENABLE_MK_PUBLIC_CHECK:-$ENABLE_PUBLIC_CHECK}"
MK_PUBLIC_URL="${MK_PUBLIC_URL:-https://presek.mk/}"
ENABLE_PUBLIC_SECURITY_HEADER_CHECK="${ENABLE_PUBLIC_SECURITY_HEADER_CHECK:-1}"
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
  local _tmp=""

  info "Checking $name at $url"
  for _ in $(seq 1 "$MAX_ATTEMPTS"); do
    _tmp="$(mktemp)"
    code="$(curl -sS -o "$_tmp" -w "%{http_code}" "$url" 2>/dev/null || true)"
    if [ "$code" = "$expected" ]; then
      if [ -z "$body_pattern" ] || grep -Fq "$body_pattern" "$_tmp" 2>/dev/null; then
        rm -f "$_tmp" 2>/dev/null || true
        ok "$name responded with HTTP $code"
        return 0
      fi
    fi
    rm -f "$_tmp" 2>/dev/null || true
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

wait_cluster_api_from_home() {
  local name="$1"
  local home_url="$2"
  local lang="$3"
  local cluster_id=""
  local cluster_url=""
  local code=""
  local body=""

  info "Checking $name via $home_url"
  for _ in $(seq 1 "$MAX_ATTEMPTS"); do
    _tmp="$(mktemp)"
    code="$(curl -sS -o "$_tmp" -w "%{http_code}" "$home_url" 2>/dev/null || true)"
    body="$(cat "$_tmp" 2>/dev/null || true)"
    rm -f "$_tmp" 2>/dev/null || true

    if [ "$code" = "200" ]; then
      cluster_id="$(printf '%s' "$body" | python3 -c "
import json, sys
data = json.load(sys.stdin)
lead = data.get('lead') or {}
cluster_id = str(lead.get('cluster_id') or '').strip()
if not cluster_id:
    sys.exit(1)
print(cluster_id)
")"
      if [ -n "$cluster_id" ]; then
        if [[ "$home_url" == *"/home"* ]]; then
          cluster_url="${home_url%%/home*}/cluster/${cluster_id}?lang=${lang}"
        else
          cluster_url="${CLUSTER_API_BASE}/${cluster_id}?lang=${lang}"
        fi
        if wait_http_ok "$name" "$cluster_url" 200 '"status":"success"'; then
          return 0
        fi
        return 1
      fi
    fi
    sleep "$SLEEP_SECONDS"
  done

  echo -e "${RED}x${RESET}  $name did not resolve a lead cluster (last HTTP code: ${code:-none})" >&2
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

load_shared_env() {
  if [ -n "${APP_ROOT:-}" ] && [ -f "$APP_ROOT/shared/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$APP_ROOT/shared/.env"
    set +a
    return
  fi

  if [ -f "$APP_DIR/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$APP_DIR/.env"
    set +a
  fi
}

mint_admin_jwt() {
  local python_bin="python3"
  local release_root="$APP_DIR"

  if [ -n "${APP_ROOT:-}" ]; then
    if [ -x "$APP_ROOT/venv/bin/python3" ]; then
      python_bin="$APP_ROOT/venv/bin/python3"
    fi
    if [ -d "$APP_ROOT/current" ]; then
      release_root="$(readlink -f "$APP_ROOT/current")"
    fi
  elif [ -x "$APP_DIR/.venv/bin/python3" ]; then
    python_bin="$APP_DIR/.venv/bin/python3"
  fi

  [ -n "${JWT_SECRET:-}" ] || fail "JWT_SECRET is required to mint an admin JWT for smoke checks"

  (
    cd "$release_root"
    PYTHONPATH="$release_root" "$python_bin" -c "from core.auth import create_admin_jwt; print(create_admin_jwt(), end='')"
  )
}

main() {
  need_cmd curl
  need_cmd python3

  load_shared_env

  wait_health_ready "API health" "$HEALTH_URL" 1 1
  wait_http_ok "Astro frontend" "$ASTRO_URL" 200
  wait_http_ok "Astro homepage SSR" "$ASTRO_URL" 200 'home-page-scope'
  wait_http_ok "Astro pulse SSR" "$ASTRO_URL/pulse" 200 'pulse-page-scope'
  wait_http_ok "Astro archive SSR" "$ASTRO_URL/archive" 200 'archive-page-scope'
  wait_http_ok "Astro entity SSR" "$ASTRO_URL/subjekt/__smoke__" 404 'entity-page-scope'
  wait_http_ok "Astro sources SSR" "$ASTRO_URL/izvori" 200 'sources-page-scope'
  wait_http_ok "Astro briefing SSR" "$ASTRO_URL/briefing" 200 'briefing-page-scope'
  wait_http_ok "Astro graph SSR" "$ASTRO_URL/graf" 200 'graph-page-scope'
  wait_http_ok "Astro settings SSR" "$ASTRO_URL/settings" 200 'settings-page-scope'
  wait_http_ok "Astro for-you SSR" "$ASTRO_URL/for-you" 200 'for-you-page-scope'
  wait_http_ok "Astro about SSR" "$ASTRO_URL/about" 200 'about-page-scope'
  wait_http_ok "Astro methodology SSR" "$ASTRO_URL/methodology" 200 'methodology-page-scope'
  wait_http_ok "Astro analize SSR" "$ASTRO_URL/analize" 200 'analize-page-scope'
  wait_http_ok "Astro MK frontend" "$ASTRO_URL/mk" 200
  wait_http_ok "Astro MK homepage SSR" "$ASTRO_URL/mk" 200 'home-page-scope'
  wait_http_ok "Image proxy" "http://127.0.0.1:5001/proxy?url=https://example.com/image.jpg&w=100" 200

  if [ "$ENABLE_FASTAPI_CHECK" = "1" ]; then
    wait_health_ready "FastAPI health" "$FASTAPI_URL" 1 1
    wait_http_ok "Homepage API" "$HOME_API_URL" 200 "\"status\":\"success\""
    wait_cluster_api_from_home "SR cluster API" "$SR_HOME_API_URL" "sr"
    wait_cluster_api_from_home "MK cluster API" "$MK_HOME_API_URL" "mk"
  fi

  if [ "$ENABLE_ADMIN_CHECK" = "1" ]; then
    wait_http_ok "Admin page" "$ADMIN_URL" 200
    wait_http_ok "Admin API without token" "$ADMIN_API_URL" 403

    admin_auth_checked=0
    if [ -n "${JWT_SECRET:-}" ]; then
      admin_jwt="$(mint_admin_jwt)"
      wait_http_ok_header "Admin API with JWT" "$ADMIN_API_URL" "Authorization: Bearer $admin_jwt" 200
      admin_auth_checked=1
    elif [ "${ALLOW_STATIC_ADMIN_TOKEN:-false}" = "true" ] && [ -n "${PRESEK_ADMIN_TOKEN:-}" ]; then
      wait_http_ok_header "Admin API with static token" "$ADMIN_API_URL" "Authorization: Bearer $PRESEK_ADMIN_TOKEN" 200
      admin_auth_checked=1
    fi

    if [ "$admin_auth_checked" = "0" ]; then
      warn "Skipping admin auth smoke check (set JWT_SECRET or ALLOW_STATIC_ADMIN_TOKEN=true with PRESEK_ADMIN_TOKEN)"
    fi
  fi

  if [ "$ENABLE_PUBLIC_CHECK" = "1" ]; then
    public_base="${PUBLIC_URL%/}"
    # Allow 200 or 301 for the root domain as it often redirects to / or www.
    wait_http_ok "Public site" "$PUBLIC_URL" "200" || wait_http_ok "Public site" "$PUBLIC_URL" "301"
    wait_http_ok "Public admin page" "$public_base/admin" 200
    wait_http_ok "Public status page" "$public_base/status" 200
    if [ "$ENABLE_PUBLIC_SECURITY_HEADER_CHECK" = "1" ]; then
      # wait_header_contains "Public site CSP" "$PUBLIC_URL" "Content-Security-Policy" "default-src 'self'"
      wait_header_contains "Public site HSTS" "$PUBLIC_URL" "Strict-Transport-Security" "max-age=63072000"
    else
      warn "Skipping public security header checks (set ENABLE_PUBLIC_SECURITY_HEADER_CHECK=1 to enable)"
    fi
  else
    warn "Skipping public URL check (set ENABLE_PUBLIC_CHECK=1 to enable)"
  fi

  if [ "$ENABLE_MK_PUBLIC_CHECK" = "1" ]; then
    mk_base="${MK_PUBLIC_URL%/}"
    wait_http_ok "MK public site" "$MK_PUBLIC_URL" 200 || wait_http_ok "MK public site" "$MK_PUBLIC_URL" 301
    wait_http_ok "MK briefing" "$mk_base/briefing" 200
    wait_http_ok "MK legacy /mk redirect" "$mk_base/mk/briefing" 301
    wait_health_ready "MK API health" "$mk_base/api/health" 1 1
    wait_cluster_api_from_home "MK public cluster API" "${mk_base}/api/home?lang=mk" "mk"
    if [ "$ENABLE_PUBLIC_SECURITY_HEADER_CHECK" = "1" ]; then
      wait_header_contains "MK site HSTS" "$MK_PUBLIC_URL" "Strict-Transport-Security" "max-age=63072000"
    fi
  else
    warn "Skipping presek.mk public checks (set ENABLE_MK_PUBLIC_CHECK=1 to enable)"
  fi

  ok "Smoke checks passed"
}

main "$@"
