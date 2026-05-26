#!/bin/bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
SHARED_DIR="$APP_ROOT/shared"
VENV_DIR="$APP_ROOT/venv"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; }
info() { echo -e "${BLUE}>${RESET}  $*"; }

# Discover service units dynamically
discover_service_units() {
    local SYSTEMD_DIR="$SOURCE_ROOT/deploy/systemd"
    local services=()
    while IFS= read -r -d '' file; do
        local unit="$(basename "$file")"
        if [[ "$unit" == *.service ]]; then
            services+=("$unit")
        fi
    done < <(find "$SYSTEMD_DIR" -maxdepth 1 -type f -name "*.service" -print0 2>/dev/null || true)
    echo "${services[@]}"
}

SERVICE_UNITS=($(discover_service_units))

show_path_state() {
  local label="$1"
  local path="$2"

  if [ -L "$path" ]; then
    ok "$label: $(readlink -f "$path")"
    return
  fi

  if [ -e "$path" ]; then
    ok "$label: $path"
    return
  fi

  fail "$label: missing ($path)"
}

show_service_state() {
  local unit="$1"
  local state
  local service_type
  local result

  if ! command -v systemctl >/dev/null 2>&1; then
    warn "$unit: systemctl unavailable"
    return
  fi

  state="$(systemctl is-active "$unit" 2>/dev/null || true)"
  case "$state" in
    active) ok "$unit: active" ;;
    *)
      service_type="$(systemctl show "$unit" -p Type --value 2>/dev/null || true)"
      result="$(systemctl show "$unit" -p Result --value 2>/dev/null || true)"
      if [ "$service_type" = "oneshot" ] && [ "$result" = "success" ]; then
        ok "$unit: completed successfully"
        return
      fi
      warn "$unit: ${state:-unknown}" ;;
  esac
}

main() {
  echo ""
  info "Presek runtime status"
  echo "APP_ROOT: $APP_ROOT"

  show_path_state "current" "$CURRENT_LINK"
  if [ -L "$PREVIOUS_LINK" ]; then
    ok "previous: $(readlink -f "$PREVIOUS_LINK")"
  else
    warn "previous: not set"
  fi

  show_path_state "shared env" "$SHARED_DIR/.env"
  show_path_state "runtime venv" "$VENV_DIR"
  show_path_state "shared Astro deps" "$SHARED_DIR/web-node_modules"

  if [ -L "$CURRENT_LINK" ]; then
    local current_root
    current_root="$(readlink -f "$CURRENT_LINK")"
    show_path_state "current release web dist" "$current_root/web/dist/server/entry.mjs"
    show_path_state "current release web node_modules" "$current_root/web/node_modules"
  fi

  # Show state for all discovered services
  for unit in "${SERVICE_UNITS[@]}"; do
    show_service_state "$unit"
  done
}

main "$@"
