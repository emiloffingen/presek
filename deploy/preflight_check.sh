#!/bin/bash
# Pre-deployment health check script
# Usage: ./deploy/preflight_check.sh

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
log_msg() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
ok()   { log_msg "${GREEN}✓${RESET}  $*"; }
warn() { log_msg "${YELLOW}!${RESET}  $*"; }
fail() { log_msg "${RED}x${RESET}  $*"; exit 1; }
info() { log_msg "${BLUE}>${RESET}  $*"; }

info "Running Pre-Deployment Pre-Flight Checks..."

# 1. Validate Environment
if [ -f "$HOME/presek-runtime/shared/.env" ]; then
    ok "Shared environment file found."
else
    fail "Missing shared environment file at $HOME/presek-runtime/shared/.env"
fi

# 2. Check Required Services
SYSTEMD_TARGET="${SYSTEMD_TARGET:-presek.target}"
SERVICES=()
while IFS= read -r line; do
    [ -n "$line" ] && SERVICES+=("$line")
done < <(systemctl list-dependencies "$SYSTEMD_TARGET" --plain --all | grep '^presek-' | sed 's/^[ \t]*//' || true)

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
if sudo nginx -t >/dev/null 2>&1; then
    ok "Nginx configuration is valid."
else
    fail "Nginx configuration test failed."
fi

# 4. Run Smoke Tests
if [ -f "./deploy/smoke_check.sh" ]; then
    info "Running smoke tests..."
    if bash "./deploy/smoke_check.sh"; then
        ok "Smoke tests passed."
    else
        fail "Smoke tests failed."
    fi
else
    fail "Smoke check script not found."
fi

ok "All pre-flight checks passed. Deployment can proceed."
