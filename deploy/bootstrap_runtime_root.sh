#!/bin/bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
SHARED_DIR="$APP_ROOT/shared"
VENV_DIR="${VENV_DIR:-$APP_ROOT/venv}"
SHARED_WEB_DEPS_DIR="${SHARED_WEB_DEPS_DIR:-$SHARED_DIR/web-deps}"
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

ensure_layout() {
  install -d "$APP_ROOT" "$APP_ROOT/releases" "$SHARED_DIR" "$SHARED_DIR/logs" "$SHARED_DIR/backups"
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
  if [ -x "$VENV_DIR/bin/python3" ] && [ "$FORCE_BOOTSTRAP" != "1" ]; then
    ok "Runtime venv already exists"
    return 0
  fi

  rm -rf "$VENV_DIR"
  info "Creating runtime venv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python3" -m pip install --upgrade pip
  "$VENV_DIR/bin/python3" -m pip install -r "$SOURCE_ROOT/requirements.txt"
  ok "Runtime venv installed"
}

ensure_shared_web_deps() {
  if [ -d "$SHARED_WEB_DEPS_DIR/node_modules" ] && [ "$FORCE_BOOTSTRAP" != "1" ]; then
    ok "Shared web dependencies already exist"
  else
    rm -rf "$SHARED_WEB_DEPS_DIR"
    install -d "$SHARED_WEB_DEPS_DIR"
    cp "$SOURCE_ROOT/web/package.json" "$SOURCE_ROOT/web/package-lock.json" "$SHARED_WEB_DEPS_DIR/"
    info "Installing shared Astro dependencies"
    (cd "$SHARED_WEB_DEPS_DIR" && npm ci)
    ok "Shared Astro dependencies installed"
  fi

  ln -sfn "$SHARED_WEB_DEPS_DIR/node_modules" "$SHARED_WEB_NODE_MODULES"
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
