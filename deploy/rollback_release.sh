#!/bin/bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
SYSTEMD_TARGET="${SYSTEMD_TARGET:-presek.target}"
ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-1}"
SKIP_RESTART="${SKIP_RESTART:-0}"
SMOKE_SCRIPT="$SOURCE_ROOT/deploy/smoke_check.sh"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
info() { echo -e "${BLUE}>${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

switch_link() {
  local link_path="$1"
  local target="$2"
  local temp_link="${link_path}.tmp.$$"
  ln -sfn "$target" "$temp_link"
  mv -Tf "$temp_link" "$link_path"
}

main() {
  need_cmd sudo
  need_cmd bash

  [ -L "$CURRENT_LINK" ] || fail "Missing current release symlink at $CURRENT_LINK"
  [ -L "$PREVIOUS_LINK" ] || fail "Missing previous release symlink at $PREVIOUS_LINK"

  local current_target rollback_target
  current_target="$(readlink -f "$CURRENT_LINK")"
  rollback_target="$(readlink -f "$PREVIOUS_LINK")"

  [ -d "$rollback_target" ] || fail "Previous release target is missing: $rollback_target"

  info "Rolling back from $(basename "$current_target") to $(basename "$rollback_target")"
  switch_link "$CURRENT_LINK" "$rollback_target"
  switch_link "$PREVIOUS_LINK" "$current_target"

  if [ "$SKIP_RESTART" = "1" ]; then
    info "Skipping service restart and smoke checks"
    ok "Rollback completed"
    ok "Current release: $(basename "$(readlink -f "$CURRENT_LINK")")"
    return 0
  fi

  info "Restarting $SYSTEMD_TARGET"
  sudo systemctl restart "$SYSTEMD_TARGET"

  info "Running smoke checks"
  ENABLE_PUBLIC_CHECK="$ENABLE_PUBLIC_CHECK" APP_ROOT="$APP_ROOT" bash "$SMOKE_SCRIPT"

  ok "Rollback completed"
  ok "Current release: $(basename "$(readlink -f "$CURRENT_LINK")")"
}

main "$@"
