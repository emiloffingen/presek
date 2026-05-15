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

# 1. Check required files exist
echo "---"
echo "1. Checking required files..."
echo ""

REQUIRED_FILES=(
    "core/api_fast.py"
    "core/celery_app.py"
    "web/package.json"
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

# 2. Checking build prerequisites
echo "---"
echo "2. Checking build prerequisites..."
echo ""

# Check npm is available
if command -v npm &>/dev/null; then
    ok "npm is available"
else
    fail "npm is required for building frontend"
fi

# Check node is available
if command -v node &>/dev/null; then
    ok "node is available"
else
    fail "node is required for building frontend"
fi

# Check web/package.json is valid JSON
if node -e "const p = require('$SOURCE_ROOT/web/package.json'); JSON.stringify(p);" 2>/dev/null; then
    ok "web/package.json is valid"
else
    fail "web/package.json is invalid"
fi

echo ""

# 3. Check for syntax errors in config files
echo "---"
echo "3. Checking configuration files..."
echo ""

# Check astro.config.mjs syntax
if node --check "$SOURCE_ROOT/web/astro.config.mjs" 2>/dev/null; then
    ok "web/astro.config.mjs syntax OK"
else
    fail "web/astro.config.mjs has syntax errors"
fi

echo ""

# 4. Simulate copy and validation
echo "---"
echo "4. Simulating release tree copy..."
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
for file in core/api_fast.py core/celery_app.py web/package.json; do
    if [ -f "$TMP_RELEASE_DIR/$file" ]; then
        ok "$file copied successfully"
    else
        fail "$file missing in release tree"
    fi
done

echo ""

# 5. Check i18n routing in Layout.astro
echo "---"
echo "5. Verifying i18n support in Layout.astro..."
echo ""

if grep -q "getLangFromUrl" "$TMP_RELEASE_DIR/web/src/layouts/Layout.astro" && \
   grep -q "useTranslations" "$TMP_RELEASE_DIR/web/src/layouts/Layout.astro"; then
    ok "web/src/layouts/Layout.astro supports i18n"
else
    fail "web/src/layouts/Layout.astro missing i18n imports"
fi

if [ -d "$TMP_RELEASE_DIR/web/src/pages/mk" ]; then
    ok "Macedonian localized pages exist in web/src/pages/mk/"
else
    fail "Macedonian localized pages are missing"
fi

# 6. Check nginx configs exist
echo ""
echo "---"
echo "6. Checking nginx configurations..."
echo ""

for config in presek.live.conf presek-mk.conf; do
    if [ -f "$TMP_RELEASE_DIR/deploy/nginx/$config" ]; then
        ok "deploy/nginx/$config exists"
    else
        fail "deploy/nginx/$config is missing"
    fi
done

# 7. Display summary
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
