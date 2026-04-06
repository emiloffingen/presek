#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="${BRANCH:-main}"
REMOTE="${REMOTE:-origin}"
SYSTEMD_TARGET="${SYSTEMD_TARGET:-presek.target}"
NGINX_SERVICE="${NGINX_SERVICE:-nginx}"
ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-1}"
SMOKE_SCRIPT="$APP_DIR/deploy/smoke_check.sh"
RELEASE_STATE_DIR="$APP_DIR/.deploy"
PREV_COMMIT_FILE="$RELEASE_STATE_DIR/previous_commit"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
info() { echo -e "${BLUE}>${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

require_clean_repo() {
  if ! git diff --quiet || ! git diff --cached --quiet; then
    fail "Working tree is not clean. Commit or stash changes before deploying."
  fi
}

main() {
  need_cmd git
  need_cmd npm
  need_cmd systemctl
  need_cmd nginx
  need_cmd bash

  cd "$APP_DIR"
  require_clean_repo

  install -d "$RELEASE_STATE_DIR"
  git rev-parse HEAD > "$PREV_COMMIT_FILE"
  info "Saved rollback commit: $(cat "$PREV_COMMIT_FILE")"

  info "Fetching $REMOTE/$BRANCH"
  git fetch "$REMOTE" "$BRANCH"

  info "Checking out latest $REMOTE/$BRANCH"
  git reset --hard "$REMOTE/$BRANCH"

  info "Installing backend dependencies"
  ./venv/bin/pip install -r requirements.txt >/dev/null

  info "Building Astro frontend"
  (cd web && npm ci >/dev/null && npm run build)

  info "Validating nginx configuration"
  sudo nginx -t

  info "Reloading $NGINX_SERVICE"
  sudo systemctl reload "$NGINX_SERVICE"

  info "Restarting $SYSTEMD_TARGET"
  sudo systemctl restart "$SYSTEMD_TARGET"

  info "Running smoke checks"
  ENABLE_PUBLIC_CHECK="$ENABLE_PUBLIC_CHECK" bash "$SMOKE_SCRIPT"

  ok "Release deployed successfully"
  ok "Current commit: $(git rev-parse --short HEAD)"
}

main "$@"
