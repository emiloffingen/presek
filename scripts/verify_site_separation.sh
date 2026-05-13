#!/bin/bash
# Verify that Serbian and Macedonian frontends are properly separated

set -e

echo "=========================================="
echo "Verifying Site Separation"
echo "=========================================="
echo ""

ERRORS=0

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
RESET='\033[0m'

ok() {
    echo -e "${GREEN}✓${RESET} $1"
}

fail() {
    echo -e "${RED}✗${RESET} $1"
    ERRORS=$((ERRORS + 1))
}

# Check for .site-identifier files
echo "Checking .site-identifier files..."
if [ -f "web/.site-identifier" ]; then
    ok "web/.site-identifier exists"
else
    fail "web/.site-identifier missing"
fi

if [ -f "web-mk/.site-identifier" ]; then
    ok "web-mk/.site-identifier exists"
else
    fail "web-mk/.site-identifier missing"
fi

# Check package.json names
echo ""
echo "Checking package.json names..."
WEB_NAME=$(grep '"name"' web/package.json | head -1 | cut -d'"' -f4)
if [ "$WEB_NAME" = "presek-web-serbian" ]; then
    ok "web/package.json name is 'presek-web-serbian'"
else
    fail "web/package.json name is '$WEB_NAME', expected 'presek-web-serbian'"
fi

WEB_MK_NAME=$(grep '"name"' web-mk/package.json | head -1 | cut -d'"' -f4)
if [ "$WEB_MK_NAME" = "presek-web-macedonian" ]; then
    ok "web-mk/package.json name is 'presek-web-macedonian'"
else
    fail "web-mk/package.json name is '$WEB_MK_NAME', expected 'presek-web-macedonian'"
fi

# Check README files
echo ""
echo "Checking README files..."
if grep -q "SERBIAN" web/README.md && grep -q "presek.live" web/README.md; then
    ok "web/README.md identifies as Serbian site"
else
    fail "web/README.md doesn't properly identify as Serbian"
fi

if grep -q "MACEDONIAN" web-mk/README.md && grep -q "пресек.мк" web-mk/README.md; then
    ok "web-mk/README.md identifies as Macedonian site"
else
    fail "web-mk/README.md doesn't properly identify as Macedonian"
fi

# Check Layout.astro for warnings
echo ""
echo "Checking Layout.astro warnings..."
if grep -q "SERBIAN SITE" web/src/layouts/Layout.astro; then
    ok "web/src/layouts/Layout.astro has Serbian warning"
else
    fail "web/src/layouts/Layout.astro missing Serbian warning"
fi

if grep -q "MACEDONIAN SITE" web-mk/src/layouts/Layout.astro; then
    ok "web-mk/src/layouts/Layout.astro has Macedonian warning"
else
    fail "web-mk/src/layouts/Layout.astro missing Macedonian warning"
fi

# Check for Cyrillic in Macedonian site
echo ""
echo "Checking Cyrillic usage in Macedonian site..."
if grep -q "пресек\|ПРЕСЕК\|пресек.мк\|ПРЕСЕК.мк" web-mk/src/layouts/Layout.astro; then
    ok "web-mk uses Macedonian Cyrillic"
else
    fail "web-mk missing Cyrillic text"
fi

# Check Serbian site doesn't use Cyrillic
echo ""
echo "Checking Serbian site doesn't use Cyrillic..."
if grep -q "пресек\|ПРЕСЕК" web/src/layouts/Layout.astro; then
    fail "web (Serbian) incorrectly contains Cyrillic text"
else
    ok "web (Serbian) doesn't contain Cyrillic text"
fi

# Check astro.config.mjs
echo ""
echo "Checking astro.config.mjs..."
if grep -q "presek.live" web/astro.config.mjs; then
    ok "web/astro.config.mjs uses presek.live"
else
    fail "web/astro.config.mjs doesn't use presek.live"
fi

if grep -q "presek.mk" web-mk/astro.config.mjs; then
    ok "web-mk/astro.config.mjs uses presek.mk"
else
    fail "web-mk/astro.config.mjs doesn't use presek.mk"
fi

echo ""
echo "=========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}All checks passed! Sites are properly separated.${RESET}"
    exit 0
else
    echo -e "${RED}Found $ERRORS issue(s). Please fix them.${RESET}"
    exit 1
fi
