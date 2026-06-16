#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
RELEASE_ROOT="${RELEASE_ROOT:-$APP_ROOT/current}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$APP_ROOT/venv/bin/python3" ]; then
    PYTHON_BIN="$APP_ROOT/venv/bin/python3"
  elif [ -x "$SCRIPT_DIR/../.venv/bin/python3" ]; then
    PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python3"
  else
    PYTHON_BIN="python3"
  fi
fi

if [ -d "$RELEASE_ROOT" ]; then
  cd "$RELEASE_ROOT"
else
  cd "$SCRIPT_DIR/.."
fi

export PYTHONPATH="${PYTHONPATH:-$PWD}"
export CSRF_TOKEN_SECRET="${CSRF_TOKEN_SECRET:-release-import-check}"
export ENV="${ENV:-test}"
exec "$PYTHON_BIN" "$SCRIPT_DIR/verify_release_imports.py"
