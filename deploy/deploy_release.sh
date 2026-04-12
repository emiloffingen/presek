#!/bin/bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
RELEASES_DIR="$APP_ROOT/releases"
SHARED_DIR="$APP_ROOT/shared"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
VENV_DIR="${VENV_DIR:-$APP_ROOT/venv}"
SHARED_WEB_NODE_MODULES="${SHARED_WEB_NODE_MODULES:-$SHARED_DIR/web-node_modules}"
SYSTEMD_TARGET="${SYSTEMD_TARGET:-presek.target}"
NGINX_SERVICE="${NGINX_SERVICE:-nginx}"
ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-1}"
SKIP_RESTART="${SKIP_RESTART:-0}"
SMOKE_SCRIPT="$SOURCE_ROOT/deploy/smoke_check.sh"
RELEASE_ID="${RELEASE_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
RUN_TESTS="${RUN_TESTS:-0}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
info() { echo -e "${BLUE}>${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

assert_paths_safe() {
  local source_real app_real
  source_real="$(cd "$SOURCE_ROOT" && pwd -P)"
  app_real="$(mkdir -p "$APP_ROOT" && cd "$APP_ROOT" && pwd -P)"
  [ "$source_real" != "$app_real" ] || fail "APP_ROOT must differ from SOURCE_ROOT for release-based deploys"
}

ensure_layout() {
  install -d "$RELEASES_DIR" "$SHARED_DIR" "$SHARED_DIR/logs" "$SHARED_DIR/backups"
  [ -f "$SHARED_DIR/.env" ] || fail "Missing shared env file at $SHARED_DIR/.env"
  [ -x "$VENV_DIR/bin/uvicorn" ] || fail "Missing Python runtime at $VENV_DIR/bin/uvicorn"
  [ -d "$SHARED_WEB_NODE_MODULES" ] || fail "Missing shared Astro dependencies at $SHARED_WEB_NODE_MODULES. Run deploy/bootstrap_runtime_root.sh first."
  [ -f "$SOURCE_ROOT/web/package.json" ] || fail "Missing Astro app at $SOURCE_ROOT/web/package.json"
}

copy_release_tree() {
  info "Copying source tree into $RELEASE_DIR"
  rsync -a \
    --exclude '.git/' \
    --exclude '.pytest_cache/' \
    --exclude '__pycache__/' \
    --exclude '.mypy_cache/' \
    --exclude '.ruff_cache/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude 'node_modules/' \
    --exclude 'web/node_modules/' \
    --exclude 'web/dist/' \
    --exclude 'logs/' \
    --exclude 'backups/' \
    --exclude 'screenshots/' \
    --exclude 'shared/' \
    --exclude 'releases/' \
    --exclude 'current' \
    --exclude 'previous' \
    --exclude 'presek.db' \
    "$SOURCE_ROOT/" "$RELEASE_DIR/"
}

prepare_release_runtime_links() {
  ln -sfn "$SHARED_DIR/.env" "$RELEASE_DIR/.env"
}

build_release() {
  ln -sfn "$SHARED_WEB_NODE_MODULES" "$RELEASE_DIR/web/node_modules"

  info "Building Astro release"
  (cd "$RELEASE_DIR/web" && npm run build)
  [ -f "$RELEASE_DIR/web/dist/server/entry.mjs" ] || fail "Release build did not produce web/dist/server/entry.mjs"
}

run_release_checks() {
  if [ "$RUN_TESTS" = "1" ]; then
    [ -n "${DATABASE_URL:-}" ] || fail "DATABASE_URL must be set when RUN_TESTS=1"
    info "Running pytest before switch"
    (cd "$SOURCE_ROOT" && pytest -q)
  fi
}

switch_current_link() {
  local target="$1"
  local temp_link="$APP_ROOT/.current.$$"
  ln -sfn "$target" "$temp_link"
  mv -Tf "$temp_link" "$CURRENT_LINK"
}

restart_and_smoke() {
  if [ "$SKIP_RESTART" = "1" ]; then
    info "Skipping nginx reload, service restart, and smoke checks"
    return 0
  fi

  info "Validating nginx configuration"
  sudo nginx -t

  info "Reloading $NGINX_SERVICE"
  sudo systemctl reload "$NGINX_SERVICE"

  info "Restarting $SYSTEMD_TARGET"
  sudo systemctl restart "$SYSTEMD_TARGET"

  info "Running smoke checks"
  ENABLE_PUBLIC_CHECK="$ENABLE_PUBLIC_CHECK" APP_ROOT="$APP_ROOT" bash "$SMOKE_SCRIPT"
}

main() {
  need_cmd rsync
  need_cmd npm
  need_cmd sudo
  need_cmd bash
  need_cmd flock

  assert_paths_safe
  ensure_layout

  # Acquire exclusive deploy lock to prevent concurrent deploys
  LOCK_FILE="$APP_ROOT/.deploy.lock"
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "Another deploy is already in progress (lock: $LOCK_FILE)"

  [ ! -e "$RELEASE_DIR" ] || fail "Release already exists: $RELEASE_DIR"

  local previous_target=""
  if [ -L "$CURRENT_LINK" ]; then
    previous_target="$(readlink -f "$CURRENT_LINK" || true)"
  fi

  copy_release_tree
  prepare_release_runtime_links
  build_release
  run_release_checks

  info "Switching current release to $RELEASE_ID"
  switch_current_link "$RELEASE_DIR"
  if [ -n "$previous_target" ] && [ -d "$previous_target" ]; then
    ln -sfn "$previous_target" "$PREVIOUS_LINK"
  fi

  if ! restart_and_smoke; then
    if [ -n "$previous_target" ] && [ -d "$previous_target" ]; then
      warn "Deploy failed smoke checks; restoring previous release"
      switch_current_link "$previous_target"
      ln -sfn "$RELEASE_DIR" "$PREVIOUS_LINK"
      sudo systemctl restart "$SYSTEMD_TARGET"
      info "Running post-rollback smoke checks"
      ENABLE_PUBLIC_CHECK="$ENABLE_PUBLIC_CHECK" APP_ROOT="$APP_ROOT" bash "$SMOKE_SCRIPT" || warn "Post-rollback smoke checks also failed"
    fi
    fail "Release deploy failed"
  fi

  ok "Release deployed successfully"
  ok "Current release: $RELEASE_ID"
}

main "$@"
