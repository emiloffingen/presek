#!/bin/bash
# Pre-deployment health check script
# Usage: APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/preflight_check.sh
# Set SKIP_SMOKE=1 to skip live smoke tests (used automatically by deploy_release.sh)

set -euo pipefail

APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
SHARED_ENV="$APP_ROOT/shared/.env"
SKIP_SMOKE="${SKIP_SMOKE:-0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
log_msg() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
ok()   { log_msg "${GREEN}✓${RESET}  $*"; }
warn() { log_msg "${YELLOW}!${RESET}  $*"; }
fail() { log_msg "${RED}x${RESET}  $*"; exit 1; }
info() { log_msg "${BLUE}>${RESET}  $*"; }

info "Running pre-deployment pre-flight checks..."

# 1. Validate Environment
if [ -f "$SHARED_ENV" ]; then
    ok "Shared environment file found at $SHARED_ENV"
else
    fail "Missing shared environment file at $SHARED_ENV"
fi

if [ -x "$APP_ROOT/venv/bin/python3" ]; then
    ok "Runtime virtualenv found at $APP_ROOT/venv"
else
    fail "Missing runtime virtualenv at $APP_ROOT/venv (run bootstrap_runtime_root.sh)"
fi

# 1b. Verify release-critical Python imports
if [ -f "$SCRIPT_DIR/verify_release_imports.sh" ]; then
    info "Verifying release-critical Python imports..."
    if APP_ROOT="$APP_ROOT" bash "$SCRIPT_DIR/verify_release_imports.sh"; then
        ok "Release import verification passed."
    else
        fail "Release import verification failed."
    fi
else
    warn "Release import verifier not found; skipping module import check"
fi

# 2. Check Required Services
SYSTEMD_TARGET="${SYSTEMD_TARGET:-presek.target}"
SERVICES=()
while IFS= read -r line; do
    [ -n "$line" ] && SERVICES+=("$line")
done < <(systemctl list-dependencies "$SYSTEMD_TARGET" --plain --all 2>/dev/null | grep '^presek-' | sed 's/^[ \t]*//' || true)

if [ "${#SERVICES[@]}" -eq 0 ]; then
    warn "No services found for target $SYSTEMD_TARGET"
else
    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$service"; then
            ok "Service $service is active."
        else
            warn "Service $service is NOT active."
        fi
    done
fi

# 3. Check Nginx configuration
if command -v nginx >/dev/null 2>&1; then
    if sudo nginx -t >/dev/null 2>&1; then
        ok "Nginx configuration is valid."
    else
        fail "Nginx configuration test failed."
    fi
else
    warn "nginx not installed; skipping nginx -t"
fi

# 4. Optional smoke tests (full manual preflight)
if [ "$SKIP_SMOKE" = "1" ]; then
    warn "Skipping smoke tests (SKIP_SMOKE=1)"
elif [ -f "$SCRIPT_DIR/smoke_check.sh" ]; then
    info "Running smoke tests..."
    if APP_ROOT="$APP_ROOT" bash "$SCRIPT_DIR/smoke_check.sh"; then
        ok "Smoke tests passed."
    else
        fail "Smoke tests failed."
    fi
else
    fail "Smoke check script not found."
fi

ok "All pre-flight checks passed. Deployment can proceed."
