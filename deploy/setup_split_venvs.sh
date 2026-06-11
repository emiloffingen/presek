#!/usr/bin/env bash
# Scaffold: split API and worker Python environments (optional future optimization).
#
# Today production uses one venv at $APP_ROOT/venv. When ready to split:
#   APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/setup_split_venvs.sh
#
# Then point systemd units:
#   presek-fastapi-unified → venv-api
#   presek-worker*         → venv-worker
set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/emiloffingen/presek-runtime}"
CURRENT="${APP_ROOT}/current"
API_VENV="${APP_ROOT}/venv-api"
WORKER_VENV="${APP_ROOT}/venv-worker"

python3 -m venv "$API_VENV"
python3 -m venv "$WORKER_VENV"

"$API_VENV/bin/pip" install -U pip wheel
"$WORKER_VENV/bin/pip" install -U pip wheel

# API: web-facing stack without heavy ML wheels.
"$API_VENV/bin/pip" install -e "${CURRENT}[api]"

# Workers: full intelligence / NLP stack.
"$WORKER_VENV/bin/pip" install -e "${CURRENT}[worker]"

echo "Created:"
echo "  API venv:    $API_VENV"
echo "  Worker venv: $WORKER_VENV"
echo "Update deploy/systemd/*.service ExecStart paths before switching."
