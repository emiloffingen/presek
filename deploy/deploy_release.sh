#!/bin/bash
# Production Deployment Script for Presek (Lean Core)
# Usage: bash deploy/deploy_release.sh

set -euo pipefail

# Cleanup lock file on exit
cleanup_lock() {
  [ -n "${LOCK_FILE:-}" ] && rm -f "$LOCK_FILE"
  exec 9>&- 2>/dev/null || true
}
trap cleanup_lock EXIT

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="/opt/presek"
RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
VENV_DIR="$APP_ROOT/venv"

# Logging helpers
info() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"; }
error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2; }
ok() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [OK]   $*"; }

# 1. Environment Validation
info "Validating deployment environment..."
[ -d "$APP_ROOT" ] || { error "APP_ROOT $APP_ROOT does not exist"; exit 1; }
[ -d "$VENV_DIR" ] || { error "VENV_DIR $VENV_DIR does not exist"; exit 1; }

# 2. Release Management
RELEASE_ID=$(date -u +%Y%m%dT%H%M%SZ)
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"

info "Copying release to $RELEASE_DIR..."
mkdir -p "$RELEASE_DIR"
rsync -a \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude 'node_modules/' \
    --exclude 'web/node_modules/' \
    --exclude 'web/dist/' \
    --exclude 'logs/' \
    --exclude 'shared/' \
    --exclude 'releases/' \
    --exclude 'current' \
    "$SOURCE_ROOT/" "$RELEASE_DIR/"

# 3. Build Frontend
info "Building frontend..."
cd "$RELEASE_DIR/web"
npm install --silent
npm run build --silent

# 4. Update Backend dependencies & migrations
info "Updating backend and running migrations..."
cd "$RELEASE_DIR"
"$VENV_DIR/bin/pip" install -r requirements.txt --quiet
"$VENV_DIR/bin/alembic" upgrade head || info "Alembic migrations failed or not configured, skipping..."

# 5. Switch Release
info "Switching to new release..."
ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

# 6. Restart Services
info "Restarting services..."
systemctl restart presek.service presek-worker.service
systemctl reload nginx

ok "Deployment $RELEASE_ID successful!"
