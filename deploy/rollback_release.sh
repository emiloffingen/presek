#!/bin/bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
SHARED_DIR="$APP_ROOT/shared"
VENV_DIR="${VENV_DIR:-$APP_ROOT/venv}"
SHARED_WEB_NODE_MODULES="${SHARED_WEB_NODE_MODULES:-$SHARED_DIR/web-node_modules}"
SYSTEMD_TARGET="${SYSTEMD_TARGET:-presek.target}"
ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-1}"
SKIP_RESTART="${SKIP_RESTART:-0}"
SMOKE_SCRIPT="$SOURCE_ROOT/deploy/smoke_check.sh"
APP_SERVICES=(
  presek-fastapi.service
  presek-astro.service
  presek-worker.service
  presek-worker-ingestion.service
  presek-worker-delivery.service
  presek-beat.service
)

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
info() { echo -e "${BLUE}>${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

cleanup_listener_port() {
  local port="$1"
  local label="$2"
  local pids=""
  pids="$(sudo lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  [ -n "$pids" ] || return 0

  info "Stopping existing $label listener(s) on port $port: $pids"
  sudo kill $pids 2>/dev/null || true
  sleep 1

  local remaining=""
  remaining="$(sudo lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  if [ -n "$remaining" ]; then
    info "Force killing stubborn $label listener(s) on port $port: $remaining"
    sudo kill -9 $remaining 2>/dev/null || true
    sleep 1
  fi
}

cleanup_orphaned_runtime_listeners() {
  info "Clearing any orphaned runtime listeners before restart"
  cleanup_listener_port 5001 "FastAPI"
  cleanup_listener_port 3000 "Astro"
}

switch_link() {
  local link_path="$1"
  local target="$2"
  local temp_link="${link_path}.tmp.$$"
  ln -sfn "$target" "$temp_link"
  mv -Tf "$temp_link" "$link_path"
}

read_release_runtime_meta() {
  local target_dir="$1"
  local key="$2"
  local meta_path="$target_dir/.runtime-meta"
  [ -f "$meta_path" ] || return 1
  sed -n "s/^${key}=//p" "$meta_path" | tail -n 1
}

main() {
  need_cmd sudo
  need_cmd bash
  need_cmd flock

  [ -L "$CURRENT_LINK" ] || fail "Missing current release symlink at $CURRENT_LINK"
  [ -L "$PREVIOUS_LINK" ] || fail "Missing previous release symlink at $PREVIOUS_LINK"

  LOCK_FILE="$APP_ROOT/.deploy.lock"
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "Another deploy or rollback is already in progress (lock: $LOCK_FILE)"

  local current_target rollback_target
  current_target="$(readlink -f "$CURRENT_LINK")"
  rollback_target="$(readlink -f "$PREVIOUS_LINK")"

  [ -d "$rollback_target" ] || fail "Previous release target is missing: $rollback_target"

  local rollback_venv_target rollback_web_target current_venv_target current_web_target
  rollback_venv_target="$(read_release_runtime_meta "$rollback_target" "VENV_TARGET" || true)"
  rollback_web_target="$(read_release_runtime_meta "$rollback_target" "WEB_NODE_MODULES_TARGET" || true)"
  current_venv_target="$(readlink -f "$VENV_DIR" || true)"
  current_web_target="$(readlink -f "$SHARED_WEB_NODE_MODULES" || true)"

  [ -n "$rollback_venv_target" ] || fail "Missing rollback Python runtime metadata in $rollback_target/.runtime-meta"
  [ -n "$rollback_web_target" ] || fail "Missing rollback web dependency metadata in $rollback_target/.runtime-meta"
  [ -d "$rollback_venv_target" ] || fail "Rollback Python runtime is missing: $rollback_venv_target"
  [ -d "$rollback_web_target" ] || fail "Rollback web dependencies are missing: $rollback_web_target"

  info "Rolling back from $(basename "$current_target") to $(basename "$rollback_target")"
  switch_link "$CURRENT_LINK" "$rollback_target"
  switch_link "$PREVIOUS_LINK" "$current_target"
  switch_link "$VENV_DIR" "$rollback_venv_target"
  switch_link "$SHARED_WEB_NODE_MODULES" "$rollback_web_target"

  if [ -n "$current_venv_target" ] && [ -n "$current_web_target" ] && [ -d "$current_target" ]; then
    cat > "$current_target/.runtime-meta" <<EOF
VENV_TARGET=$current_venv_target
WEB_NODE_MODULES_TARGET=$current_web_target
EOF
  fi

  if [ "$SKIP_RESTART" = "1" ]; then
    info "Skipping service restart and smoke checks"
    ok "Rollback completed"
    ok "Current release: $(basename "$(readlink -f "$CURRENT_LINK")")"
    return 0
  fi

  info "Restarting application services"
  cleanup_orphaned_runtime_listeners
  sudo systemctl restart "${APP_SERVICES[@]}"
  sudo systemctl start "$SYSTEMD_TARGET"

  info "Running smoke checks"
  ENABLE_PUBLIC_CHECK="$ENABLE_PUBLIC_CHECK" APP_ROOT="$APP_ROOT" bash "$SMOKE_SCRIPT"

  ok "Rollback completed"
  ok "Current release: $(basename "$(readlink -f "$CURRENT_LINK")")"
}

main "$@"
