#!/bin/bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
SHARED_DIR="$APP_ROOT/shared"
VENV_DIR="${VENV_DIR:-$APP_ROOT/venv}"
PYTHON_ENVS_DIR="${PYTHON_ENVS_DIR:-$SHARED_DIR/python-envs}"
SHARED_WEB_DEPS_ROOT="${SHARED_WEB_DEPS_ROOT:-$SHARED_DIR/web-deps}"
SHARED_WEB_NODE_MODULES="${SHARED_WEB_NODE_MODULES:-$SHARED_DIR/web-node_modules}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ENV_SOURCE_FILE="${ENV_SOURCE_FILE:-$SOURCE_ROOT/.env}"
FORCE_BOOTSTRAP="${FORCE_BOOTSTRAP:-0}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
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

ensure_layout() {
  install -d "$APP_ROOT" "$APP_ROOT/releases" "$SHARED_DIR" "$SHARED_DIR/logs" "$SHARED_DIR/backups" "$PYTHON_ENVS_DIR" "$SHARED_WEB_DEPS_ROOT"
}

ensure_shared_env() {
  if [ -f "$SHARED_DIR/.env" ] && [ "$FORCE_BOOTSTRAP" != "1" ]; then
    ok "Shared env already exists"
    return 0
  fi

  [ -f "$ENV_SOURCE_FILE" ] || fail "Missing env source file: $ENV_SOURCE_FILE"
  cp "$ENV_SOURCE_FILE" "$SHARED_DIR/.env"
  ok "Seeded shared env from $ENV_SOURCE_FILE"
}

ensure_runtime_venv() {
  local requirements_hash versioned_venv
  requirements_hash="$(sha256sum "$SOURCE_ROOT/requirements.txt" | awk '{print $1}')"
  versioned_venv="$PYTHON_ENVS_DIR/$requirements_hash"

  if [ -d "$VENV_DIR" ] && [ ! -L "$VENV_DIR" ] && [ "$VENV_DIR" != "$versioned_venv" ]; then
    local legacy_venv="$PYTHON_ENVS_DIR/legacy-bootstrap"
    [ -e "$legacy_venv" ] || mv "$VENV_DIR" "$legacy_venv"
  fi

  if [ -x "$versioned_venv/bin/python3" ] && [ "$FORCE_BOOTSTRAP" != "1" ]; then
    ok "Runtime venv already exists"
  else
    rm -rf "$versioned_venv"
    info "Creating runtime venv at $versioned_venv"
    "$PYTHON_BIN" -m venv "$versioned_venv"
    "$versioned_venv/bin/python3" -m pip install --upgrade pip
    "$versioned_venv/bin/python3" -m pip install -r "$SOURCE_ROOT/requirements.txt"
    ok "Runtime venv installed"
  fi

  if [ -L "$VENV_DIR" ]; then
    switch_link "$VENV_DIR" "$versioned_venv"
  else
    ln -sfn "$versioned_venv" "$VENV_DIR"
  fi
}

ensure_shared_web_deps() {
  local lock_source deps_hash versioned_web_deps
  lock_source="$SOURCE_ROOT/web/package-lock.json"
  [ -f "$lock_source" ] || lock_source="$SOURCE_ROOT/web/package.json"
  deps_hash="$(sha256sum "$lock_source" | awk '{print $1}')"
  versioned_web_deps="$SHARED_WEB_DEPS_ROOT/$deps_hash"

  if [ -d "$versioned_web_deps/node_modules" ] && [ "$FORCE_BOOTSTRAP" != "1" ]; then
    ok "Shared web dependencies already exist"
  else
    rm -rf "$versioned_web_deps"
    install -d "$versioned_web_deps"
    cp "$SOURCE_ROOT/web/package.json" "$versioned_web_deps/"
    [ ! -f "$SOURCE_ROOT/web/package-lock.json" ] || cp "$SOURCE_ROOT/web/package-lock.json" "$versioned_web_deps/"
    info "Installing shared Astro dependencies"
    (cd "$versioned_web_deps" && npm ci) || fail "npm ci failed — Astro dependencies not installed"
    ok "Shared Astro dependencies installed"
  fi

  if [ -L "$SHARED_WEB_NODE_MODULES" ]; then
    switch_link "$SHARED_WEB_NODE_MODULES" "$versioned_web_deps/node_modules"
  else
    ln -sfn "$versioned_web_deps/node_modules" "$SHARED_WEB_NODE_MODULES"
  fi
}

main() {
  need_cmd "$PYTHON_BIN"
  need_cmd npm

  ensure_layout
  ensure_shared_env
  ensure_runtime_venv
  ensure_shared_web_deps

  echo ""
  echo "Runtime bootstrap complete."
  echo "APP_ROOT: $APP_ROOT"
  echo "Shared env: $SHARED_DIR/.env"
  echo "Runtime venv: $VENV_DIR"
  echo "Shared Astro deps: $SHARED_WEB_NODE_MODULES"
}

main "$@"
