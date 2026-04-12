#!/bin/bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
KEEP_EXTRA="${KEEP_EXTRA:-2}"
DRY_RUN="${DRY_RUN:-1}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }
info() { echo -e "${BLUE}>${RESET}  $*"; }

main() {
  [ -d "$RELEASES_DIR" ] || fail "Missing releases directory: $RELEASES_DIR"
  [ -L "$CURRENT_LINK" ] || fail "Missing current symlink: $CURRENT_LINK"

  local current_target previous_target
  current_target="$(readlink -f "$CURRENT_LINK")"
  previous_target=""
  if [ -L "$PREVIOUS_LINK" ]; then
    previous_target="$(readlink -f "$PREVIOUS_LINK")"
  fi

  mapfile -t all_releases < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d | sort -r)
  [ "${#all_releases[@]}" -gt 0 ] || { warn "No releases found"; exit 0; }

  local -A keep_map=()
  keep_map["$current_target"]=1
  if [ -n "$previous_target" ]; then
    keep_map["$previous_target"]=1
  fi

  local kept_extra=0
  local release
  for release in "${all_releases[@]}"; do
    if [ -n "${keep_map[$release]:-}" ]; then
      continue
    fi
    if [ "$kept_extra" -lt "$KEEP_EXTRA" ]; then
      keep_map["$release"]=1
      kept_extra=$((kept_extra + 1))
    fi
  done

  info "Release retention plan"
  echo "APP_ROOT: $APP_ROOT"
  echo "KEEP_EXTRA: $KEEP_EXTRA"
  echo "DRY_RUN: $DRY_RUN"

  for release in "${all_releases[@]}"; do
    if [ "$release" = "$current_target" ]; then
      ok "keep current   $(basename "$release")"
    elif [ -n "$previous_target" ] && [ "$release" = "$previous_target" ]; then
      ok "keep previous  $(basename "$release")"
    elif [ -n "${keep_map[$release]:-}" ]; then
      ok "keep extra     $(basename "$release")"
    else
      warn "prune         $(basename "$release")"
      if [ "$DRY_RUN" = "0" ]; then
        rm -rf "$release"
      fi
    fi
  done

  if [ "$DRY_RUN" = "1" ]; then
    info "Dry run only; no releases were deleted"
  else
    ok "Release pruning complete"
  fi
}

main "$@"
