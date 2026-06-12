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

  if ! build_outputs_intact; then
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

build_outputs_intact() {
  local server_dir="$WEB_DIR/dist/server"

  [ -d "$server_dir" ] || return 1

  node --input-type=module - "$server_dir" <<'EOF'
import fs from 'node:fs';
import path from 'node:path';

const root = process.argv[2];
const importPattern =
  /\b(?:import|export)\b[\s\S]*?\bfrom\s*['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)/g;

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(fullPath);
      continue;
    }
    if (!entry.isFile() || !fullPath.endsWith('.mjs')) {
      continue;
    }

    const source = fs.readFileSync(fullPath, 'utf8');
    for (const match of source.matchAll(importPattern)) {
      const specifier = match[1] ?? match[2];
      if (!specifier || !specifier.startsWith('.')) {
        continue;
      }

      // Client-hydration scripts may embed source paths in strings; not runtime imports.
      if (/\.tsx?$/i.test(specifier)) {
        continue;
      }

      const target = path.resolve(path.dirname(fullPath), specifier);
      if (!fs.existsSync(target)) {
        console.error(`Missing Astro server import: ${path.relative(root, fullPath)} -> ${specifier}`);
        process.exit(1);
      }
    }
  }
}

walk(root);
EOF
}

rebuild_dist() {
  local dist_dir="$WEB_DIR/dist"
  local backup_dir="$WEB_DIR/.dist-backup.$$"

  rm -rf "$backup_dir"
  mkdir -p "$WEB_DIR/.astro/collections"
  if [ -d "$dist_dir" ]; then
    mv "$dist_dir" "$backup_dir"
  fi

  if (cd "$WEB_DIR" && npm run build); then
    rm -rf "$backup_dir"
    return 0
  fi

  echo "Astro rebuild failed; restoring previous dist/" >&2
  if [ -d "$backup_dir" ]; then
    rm -rf "$dist_dir"
    mv "$backup_dir" "$dist_dir"
  else
    echo "No previous dist/ backup was available to restore" >&2
  fi
  return 1
}

main() {
  need_cmd npm
  need_cmd node

  if build_required; then
    echo "Astro build is missing or stale; rebuilding..." >&2
    rebuild_dist
  fi
}

main "$@"
