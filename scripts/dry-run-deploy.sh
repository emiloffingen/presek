#!/bin/bash
# Dry-run deployment validation script
# Tests deployment without affecting production

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
RESET='\033[0m'

ok() { echo -e "${GREEN}✓${RESET} $1"; }
fail() { echo -e "${RED}✗${RESET} $1"; exit 1; }
warn() { echo -e "${YELLOW}!${RESET} $1"; }
info() { echo -e "${BLUE}>${RESET} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "DRY-RUN DEPLOYMENT VALIDATION"
echo "=========================================="
echo ""
echo "Source: $SOURCE_ROOT"
echo "This script validates deployment without affecting production"
echo ""

# 1. Verify site separation
echo "---"
echo "1. Verifying site separation..."
echo ""

if [ -f "$SCRIPT_DIR/verify_site_separation.sh" ]; then
    bash "$SCRIPT_DIR/verify_site_separation.sh" || fail "Site separation check failed"
    echo ""
else
    warn "verify_site_separation.sh not found, skipping"
fi

# 2. Check required files exist
echo "---"
echo "2. Checking required files..."
echo ""

REQUIRED_FILES=(
    "api_fast.py"
    "celery_app.py"
    "web/package.json"
    "web-mk/package.json"
    "deploy/deploy_release.sh"
    "deploy/nginx/presek.live.conf"
    "deploy/nginx/presek-mk.conf"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$SOURCE_ROOT/$file" ]; then
        ok "$file exists"
    else
        fail "$file is missing"
    fi
done

echo ""

# 3. Validate web/ and web-mk/ can be built
echo "---"
echo "3. Checking build prerequisites..."
echo ""

# Check npm is available
if command -v npm &>/dev/null; then
    ok "npm is available"
else
    fail "npm is required for building frontends"
fi

# Check node is available
if command -v node &>/dev/null; then
    ok "node is available"
else
    fail "node is required for building frontends"
fi

# Check web/package.json is valid JSON
if node -e "const p = require('$SOURCE_ROOT/web/package.json'); JSON.stringify(p);" 2>/dev/null; then
    ok "web/package.json is valid"
else
    fail "web/package.json is invalid"
fi

# Check web-mk/package.json is valid JSON
if node -e "const p = require('$SOURCE_ROOT/web-mk/package.json'); JSON.stringify(p);" 2>/dev/null; then
    ok "web-mk/package.json is valid"
else
    fail "web-mk/package.json is invalid"
fi

echo ""

# 4. Check for syntax errors in config files
echo "---"
echo "4. Checking configuration files..."
echo ""

# Check astro.config.mjs syntax
for config in "$SOURCE_ROOT/web/astro.config.mjs" "$SOURCE_ROOT/web-mk/astro.config.mjs"; do
    if node --check "$config" 2>/dev/null; then
        ok "$(basename $config) syntax OK"
    else
        fail "$(basename $config) has syntax errors"
    fi
done

echo ""

# 5. Simulate copy and validation
echo "---"
echo "5. Simulating release tree copy..."
echo ""

TMP_RELEASE_DIR="$(mktemp -d)"
trap "rm -rf $TMP_RELEASE_DIR" EXIT

info "Creating temporary release directory: $TMP_RELEASE_DIR"

# Copy essential files (simulating rsync in deploy script)
rsync -a \
    --exclude '.git/' \
    --exclude 'node_modules/' \
    --exclude 'dist/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude '.pytest_cache/' \
    --exclude '__pycache__/' \
    --exclude '.mypy_cache/' \
    "$SOURCE_ROOT/" "$TMP_RELEASE_DIR/" || fail "Failed to copy source tree"

# Validate copied structure
for file in api_fast.py celery_app.py web/package.json web-mk/package.json; do
    if [ -f "$TMP_RELEASE_DIR/$file" ]; then
        ok "$file copied successfully"
    else
        fail "$file missing in release tree"
    fi
done

echo ""

# 6. Check Macedonian site has Cyrillic
echo "---"
echo "6. Verifying Macedonian Cyrillic conversion..."
echo ""

if grep -q "пресек\|ПРЕСЕК\|пресек.мк\|ПРЕСЕК.мк" "$TMP_RELEASE_DIR/web-mk/src/layouts/Layout.astro"; then
    ok "web-mk Layout.astro contains Macedonian Cyrillic"
else
    fail "web-mk Layout.astro missing Cyrillic text"
fi

if grep -q "ПРЕСЕК.мк" "$TMP_RELEASE_DIR/web-mk/src/layouts/Layout.astro"; then
    ok "web-mk uses ПРЕСЕК.мк branding"
else
    warn "web-mk missing ПРЕСЕК.мк branding"
fi

# 7. Check Serbian site does NOT have Cyrillic
echo ""
echo "---"
echo "7. Verifying Serbian site doesn't use Cyrillic..."
echo ""

if ! grep -q "пресек\|ПРЕСЕК" "$TMP_RELEASE_DIR/web/src/layouts/Layout.astro"; then
    ok "web (Serbian) doesn't contain Cyrillic"
else
    fail "web (Serbian) incorrectly contains Cyrillic text"
fi

# 8. Check nginx configs exist
echo ""
echo "---"
echo "8. Checking nginx configurations..."
echo ""

for config in presek.live.conf presek-mk.conf; do
    if [ -f "$TMP_RELEASE_DIR/deploy/nginx/$config" ]; then
        ok "deploy/nginx/$config exists"
    else
        fail "deploy/nginx/$config is missing"
    fi
done

# 9. Display summary
echo ""
echo "=========================================="
echo "DRY-RUN VALIDATION COMPLETE"
echo "=========================================="
echo ""
echo "All checks passed!"
echo ""
echo "To deploy for real, run:"
echo "  APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/deploy_release.sh"
echo ""
echo "Temporary directory cleaned up: $TMP_RELEASE_DIR"
echo ""
