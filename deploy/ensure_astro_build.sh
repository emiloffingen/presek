#!/bin/bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
WEB_DIR="${WEB_DIR:-$APP_ROOT/web}"
ENTRY="$WEB_DIR/dist/server/entry.mjs"
FORCE_WEB_BUILD="${FORCE_WEB_BUILD:-0}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

build_required() {
  if [ "$FORCE_WEB_BUILD" = "1" ] || [ ! -f "$ENTRY" ]; then
    return 0
  fi

  local path
  for path in \
    "$WEB_DIR/src" \
    "$WEB_DIR/public" \
    "$WEB_DIR/package.json" \
    "$WEB_DIR/package-lock.json" \
    "$WEB_DIR/astro.config.mjs" \
    "$WEB_DIR/tsconfig.json"
  do
    [ -e "$path" ] || continue
    if find "$path" -type f -newer "$ENTRY" -print -quit 2>/dev/null | grep -q .; then
      return 0
    fi
  done

  return 1
}

main() {
  need_cmd npm

  if build_required; then
    echo "Astro build is missing or stale; rebuilding..." >&2
    rm -rf "$WEB_DIR/dist"
    (cd "$WEB_DIR" && npm run build)
  fi
}

main "$@"
