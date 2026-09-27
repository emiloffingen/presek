#!/bin/bash
# presek-deploy — one deploy path for every Presek host (phone, shield, tablet).
#
# Pulls the tracked branch, syncs Python/web deps when their manifests changed,
# rebuilds the Astro frontend, and restarts the services by killing them; each
# host's supervisor (watchdog on phone/shield, runit on shield, manual/agentd on
# tablet) brings them back. Idempotent and safe to re-run.
#
# Usage:
#   deploy/presek-deploy.sh            # deploy the current branch
#   deploy/presek-deploy.sh --build    # force a web rebuild even if fresh
#   deploy/presek-deploy.sh --no-pull  # skip git (already up to date)
#   BRANCH=feat/x deploy/presek-deploy.sh
#
# Env knobs:
#   PRESEK_APP_DIR   repo root (default: parent of this script)
#   BRANCH           branch to pull (default: current branch)
#   SKIP_PY          set 1 to skip python dep sync
#   SKIP_WEB         set 1 to skip web build
#   FORCE_WEB_BUILD  forwarded to ensure_astro_build.sh
set -uo pipefail

APP_DIR="${PRESEK_APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
WEB_DIR="$APP_DIR/web"
VENV="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/logs"
LOCK="$LOG_DIR/deploy.lock"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%F %T')] [deploy] $*"; }

# One deploy at a time.
exec 9>"$LOCK"
if ! flock -n 9 2>/dev/null; then
  log "another deploy is running; exiting"
  exit 0
fi

cd "$APP_DIR" || { log "APP_DIR missing: $APP_DIR"; exit 1; }

FORCE_BUILD=0
DO_PULL=1
SRC_BUNDLE=""
for arg in "$@"; do
  case "$arg" in
    --build) FORCE_BUILD=1 ;;
    --no-pull) DO_PULL=0 ;;
    --src=*) SRC_BUNDLE="${arg#--src=}" ;;
    *) log "unknown arg: $arg" ;;
  esac
done

# --- 0. optional source bundle (hosts without a git checkout) --------------
# A bundle is a git-archive tarball of tracked files produced on a host that
# DOES have the repo (e.g. `git archive --format=tar.gz -o src.tgz HEAD`).
# Extracting it makes "source" match exactly, so a bundle-deployed host can no
# longer rebuild stale code (the class of bug that broke /izvori).
if [ -n "$SRC_BUNDLE" ]; then
  if [ -f "$SRC_BUNDLE" ]; then
    log "applying source bundle: $SRC_BUNDLE"
    if tar xzf "$SRC_BUNDLE" -C "$APP_DIR" 2>/dev/null; then
      log "source bundle applied"
    else
      log "source bundle extraction FAILED"
    fi
  else
    log "source bundle not found: $SRC_BUNDLE (skipping)"
  fi
fi

# --- 1. git pull -----------------------------------------------------------
OLD=""
if [ "$DO_PULL" = "1" ] && [ -d .git ]; then
  BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null)}"
  if [ -n "$BRANCH" ] && [ "$BRANCH" != "HEAD" ]; then
    git fetch --quiet origin "$BRANCH" 2>/dev/null || log "git fetch failed (offline?)"
    if git merge --ff-only --quiet "origin/$BRANCH" 2>/dev/null; then
      log "fast-forwarded to origin/$BRANCH"
    else
      log "no fast-forward (local ahead/diverged or offline) — continuing with local tree"
    fi
  fi
fi
OLD="$(git rev-parse HEAD 2>/dev/null || echo none)"
CHANGED="$(git diff --name-only HEAD@{1} HEAD 2>/dev/null || true)"

# --- 2. python deps (only when manifests changed) --------------------------
if [ "${SKIP_PY:-0}" != "1" ]; then
  if printf '%s\n' "$CHANGED" | grep -qE '^(uv\.lock|pyproject\.toml|requirements\.txt)$'; then
    if command -v uv >/dev/null 2>&1 && [ -d "$VENV" ]; then
      log "python manifests changed; uv sync"
      (cd "$APP_DIR" && UV_PROJECT_ENVIRONMENT="$VENV" uv sync --quiet) \
        && log "uv sync ok" || log "uv sync failed (continuing)"
    else
      log "python manifests changed but uv/venv unavailable; skipping"
    fi
  fi
fi

# --- 3. web build ----------------------------------------------------------
if [ "${SKIP_WEB:-0}" != "1" ]; then
  if [ -x "$APP_DIR/deploy/ensure_astro_build.sh" ]; then
    log "ensuring web build"
    APP_ROOT="$APP_DIR" WEB_DIR="$WEB_DIR" \
      FORCE_WEB_BUILD=$([ "$FORCE_BUILD" = "1" ] && echo 1 || echo "${FORCE_WEB_BUILD:-0}") \
      bash "$APP_DIR/deploy/ensure_astro_build.sh" && log "web build ok" || log "web build failed (previous dist kept)"
  else
    log "ensure_astro_build.sh missing; running npm build directly"
    (cd "$WEB_DIR" && npm run build) && log "npm build ok" || log "npm build failed"
  fi
fi

# --- 4. restart services (kill; supervisor respawns) -----------------------
restart() {
  local pat="$1" label="$2"
  if pgrep -f "$pat" >/dev/null 2>&1; then
    pkill -f "$pat" 2>/dev/null && log "restart requested: $label"
  else
    log "$label not running (supervisor will start it)"
  fi
}

U="core.api""_fast:app"
W="core.""celery_app worker"
B="core.""celery_app beat"
N="dist/server/""entry.mjs"

restart "$U" fastapi
restart "$W" worker
restart "$B" beat
restart "$N" astro

log "deploy complete (head=$(git rev-parse --short HEAD 2>/dev/null || echo none))"
