#!/usr/bin/env bash
# Create split API and worker Python environments (Phase 4 resource isolation).
#
# Usage:
#   APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/setup_split_venvs.sh
#
# Then set in shared/.env (and reload systemd):
#   PRESEK_API_VENV=/home/emiloffingen/presek-runtime/venv-api
#   PRESEK_WORKER_VENV=/home/emiloffingen/presek-runtime/venv-worker
#
# API import contract (forbidden worker deps in API surface):
#   deploy/python_env_contract.json
#   scripts/check_api_venv_imports.py
#
# Systemd units already honor PRESEK_API_VENV / PRESEK_WORKER_VENV when present.
set -euo pipefail

SOURCE_ROOT="${SOURCE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
CURRENT="${APP_ROOT}/current"
PYTHON_ENVS_DIR="${PYTHON_ENVS_DIR:-$APP_ROOT/shared/python-envs}"
API_VENV="${APP_ROOT}/venv-api"
WORKER_VENV="${APP_ROOT}/venv-worker"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FORCE_BOOTSTRAP="${FORCE_BOOTSTRAP:-1}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

switch_link() {
  local link_path="$1"
  local target="$2"
  local temp_link="${link_path}.tmp.$$"
  ln -sfn "$target" "$temp_link"
  mv -Tf "$temp_link" "$link_path"
}

install_grouped_venv() {
  local label="$1"
  local link_path="$2"
  shift 2
  local groups=("$@")
  local lock_hash versioned_venv group_args=()

  need_cmd uv
  [ -f "$SOURCE_ROOT/uv.lock" ] || { echo "Missing uv.lock in $SOURCE_ROOT" >&2; exit 1; }

  lock_hash="$(sha256sum "$SOURCE_ROOT/uv.lock" | awk '{print $1}')"
  versioned_venv="$PYTHON_ENVS_DIR/${label}-${lock_hash}"

  for group in "${groups[@]}"; do
    group_args+=(--group "$group")
  done
  group_args=(--no-default-groups "${group_args[@]}")

  if [ -x "$versioned_venv/bin/python3" ] && [ "$FORCE_BOOTSTRAP" != "1" ]; then
    echo "✓  $label venv is already up to date at $versioned_venv"
  else
    rm -rf "$versioned_venv"
    echo "> Creating $label venv at $versioned_venv"
    uv venv "$versioned_venv" --python "$PYTHON_BIN"
    UV_PROJECT_ENVIRONMENT="$versioned_venv" uv sync --frozen --no-dev --no-install-project --directory "$SOURCE_ROOT" "${group_args[@]}"
  fi

  switch_link "$link_path" "$versioned_venv"
  echo "✓  $label venv → $link_path"
}

main() {
  need_cmd "$PYTHON_BIN"
  install -d "$APP_ROOT" "$PYTHON_ENVS_DIR"

  if [ -f "$APP_ROOT/shared/.env" ]; then
    echo "> Loading shared env variables from $APP_ROOT/shared/.env"
    set -a
    source "$APP_ROOT/shared/.env"
    set +a
  fi

  if [ ! -d "$CURRENT" ]; then
    echo "Warning: $CURRENT not found — using SOURCE_ROOT=$SOURCE_ROOT for dependency resolution" >&2
  fi

  # API: shared base + web/search stack (no torch/playwright/llama-cpp).
  install_grouped_venv "venv-api" "$API_VENV" api

  echo "> Verifying API venv import contract"
  if ! CSRF_TOKEN_SECRET=deploy-check ENV=production "$API_VENV/bin/python3" "$SOURCE_ROOT/scripts/check_api_venv_imports.py"; then
    echo "API venv failed import contract (see deploy/python_env_contract.json)" >&2
    exit 1
  fi

  # Workers: shared base + API NLP helpers + full intelligence stack.
  install_grouped_venv "venv-worker" "$WORKER_VENV" api worker

  if "$WORKER_VENV/bin/python3" -c "import playwright" >/dev/null 2>&1; then
    echo "> Ensuring Playwright Chromium browser in worker venv"
    "$WORKER_VENV/bin/python3" -m playwright install chromium
  fi

  cat <<EOF

Split venvs ready:
  API venv:    $API_VENV
  Worker venv: $WORKER_VENV
  Contract:    $SOURCE_ROOT/deploy/python_env_contract.json

Add to $APP_ROOT/shared/.env:
  PRESEK_API_VENV=$API_VENV
  PRESEK_WORKER_VENV=$WORKER_VENV

Then reload and restart:
  sudo systemctl daemon-reload
  sudo systemctl restart presek.target

Compare RSS before/after:
  ps -o rss,cmd -C uvicorn -C celery | awk '{sum+=\$1} END {print sum/1024 \" MB\"}'
EOF
}

main "$@"
