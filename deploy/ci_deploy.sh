#!/bin/bash
# CI/CD entrypoint for remote SSH deploys.
# Pulls latest code from the server-side git checkout, then runs deploy_release.sh.
#
# Usage:
#   APP_ROOT=/home/emiloffingen/presek-runtime DEPLOY_GIT_DIR=/home/emiloffingen/presek bash deploy/ci_deploy.sh
#
# Environment:
#   APP_ROOT         Runtime root (default: $HOME/presek-runtime)
#   DEPLOY_GIT_DIR   Server-side git checkout (default: $HOME/presek)
#   DEPLOY_GIT_BRANCH Branch to deploy (default: main)

set -euo pipefail

APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
DEPLOY_GIT_DIR="${DEPLOY_GIT_DIR:-$HOME/presek}"
DEPLOY_GIT_BRANCH="${DEPLOY_GIT_BRANCH:-main}"
DEPLOY_SCRIPT="$DEPLOY_GIT_DIR/deploy/deploy_release.sh"

if [ ! -d "$DEPLOY_GIT_DIR" ]; then
  echo "DEPLOY_GIT_DIR does not exist: $DEPLOY_GIT_DIR" >&2
  echo "Clone the repository on the server before running CI deploy." >&2
  exit 1
fi

if [ ! -f "$DEPLOY_SCRIPT" ]; then
  echo "Missing deploy script at $DEPLOY_SCRIPT" >&2
  echo "Ensure DEPLOY_GIT_DIR points to a full Presek git checkout." >&2
  exit 1
fi

export APP_ROOT
export DEPLOY_GIT_DIR
export DEPLOY_GIT_BRANCH

exec bash "$DEPLOY_SCRIPT"
