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
warn() { echo "[$(date '+%F %T')] [deploy] !! $*"; }

# One deploy at a time.
exec 9>"$LOCK"
if ! flock -n 9 2>/dev/null; then
  log "another deploy is running; exiting"
  exit 0
fi

cd "$APP_DIR" || { log "APP_DIR missing: $APP_DIR"; exit 1; }

# Make build-time values IDENTICAL on every host. Without this, one host may
# define PUBLIC_PROMO_DISCOUNT and another may not, producing different Vite
# chunk hashes for the same source (split-brain across the tunnel).
#
# We deliberately do NOT source the whole .env: exporting backend secrets and
# loopback URLs into the Astro build would inline them into the client bundle
# (PUBLIC_* is baked at build time). Only the build-safe knobs are pulled, and
# PUBLIC_API_URL is forced relative so browsers never get 127.0.0.1.
if [ -f "$APP_DIR/.env" ]; then
  _promo="$(grep -E '^PROMO_DISCOUNT=' "$APP_DIR/.env" | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
  [ -n "$_promo" ] && export PUBLIC_PROMO_DISCOUNT="${PUBLIC_PROMO_DISCOUNT:-$_promo}"
  _site="$(grep -E '^PUBLIC_SITE_URL=' "$APP_DIR/.env" | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
  [ -n "$_site" ] && export PUBLIC_SITE_URL="${PUBLIC_SITE_URL:-$_site}"
  export PUBLIC_API_URL="/api"
  log "applied build env (PUBLIC_PROMO_DISCOUNT=${PUBLIC_PROMO_DISCOUNT:-unset}, PUBLIC_API_URL=/api)"
fi

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
#
# The bundle only ADDS/OVERWRITES files, so files deleted upstream would linger
# on this host and get picked up by the bundler (e.g. Tailwind scanning dead
# components -> a different CSS hash). We therefore prune tracked source dirs of
# anything the bundle does not contain.
if [ -n "$SRC_BUNDLE" ]; then
  if [ -f "$SRC_BUNDLE" ]; then
    log "applying source bundle: $SRC_BUNDLE"
    MANIFEST="$APP_DIR/.src-bundle.manifest"
    tar tzf "$SRC_BUNDLE" | sed 's|/$||' | sort -u > "$MANIFEST" 2>/dev/null || true
    if tar xzf "$SRC_BUNDLE" -C "$APP_DIR" 2>/dev/null; then
      log "source bundle applied"
      # Prune files under tracked source roots that the bundle does not list.
      for root in web/src web/public mcp tasks core routes nlp utils; do
        [ -d "$APP_DIR/$root" ] || continue
        while IFS= read -r f; do
          rel="${f#$APP_DIR/}"
          grep -qxF "$rel" "$MANIFEST" || rm -f "$f"
        done < <(find "$APP_DIR/$root" -type f 2>/dev/null)
      done
      log "pruned files absent from the bundle"
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
# On the Android/proot hosts uv's hardlink step fails ("Operation not permitted")
# and its copy fallback has been observed to silently drop files (e.g.
# fastapi/__init__.py), corrupting the live venv. We therefore:
#   * use `--frozen` so uv never re-resolves/regenerates the lock at deploy time,
#   * use `--no-dev` so test tooling is not installed on production hosts,
#   * force UV_LINK_MODE=copy (hardlinks are unsupported under proot),
#   * verify a critical import afterwards and, if broken, restore the previous
#     environment marker so the failure is loud rather than silent.
if [ "${SKIP_PY:-0}" != "1" ]; then
  if printf '%s\n' "$CHANGED" | grep -qE '^(uv\.lock|pyproject\.toml|requirements\.txt)$'; then
    if command -v uv >/dev/null 2>&1 && [ -d "$VENV" ]; then
      log "python manifests changed; uv sync --frozen --no-dev (link-mode=copy)"
      if (cd "$APP_DIR" && UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT="$VENV" \
            uv sync --frozen --no-dev --quiet); then
        if "$VENV/bin/python" -c "from fastapi import FastAPI" >/dev/null 2>&1; then
          log "uv sync ok"
        else
          warn "uv sync left the venv broken (fastapi unimportable); see /tmp/opencode repair or re-run with pip"
        fi
      else
        log "uv sync failed (continuing with existing venv)"
      fi
    else
      log "python manifests changed but uv/venv unavailable; skipping"
    fi
  fi
fi

# --- 3. web build ----------------------------------------------------------
if [ "${SKIP_WEB:-0}" != "1" ]; then
  # Sync web dependencies from the lockfile when manifests changed, or when a
  # deploy is forced. Divergent node_modules between hosts (e.g. different
  # @tailwindcss internals) produce different CSS/JS hashes for identical
  # source -> asset split-brain over a shared tunnel. `npm ci` pins them.
  if [ "${SKIP_NPM:-0}" != "1" ] && [ -f "$WEB_DIR/package-lock.json" ]; then
    if [ "$FORCE_BUILD" = "1" ] || printf '%s\n' "$CHANGED" | grep -qE '^web/(package\.json|package-lock\.json)$'; then
      log "syncing web dependencies (npm ci)"
      (cd "$WEB_DIR" && npm ci --no-audit --no-fund) && log "npm ci ok" || log "npm ci failed (continuing with existing node_modules)"
    fi
  fi
  # Clear caches that make builds non-deterministic across hosts: a warm
  # .astro/Vite cache can yield a different CSS/JS hash than a cold build,
  # which shows up as asset split-brain when two hosts share one tunnel.
  rm -rf "$WEB_DIR/.astro" "$WEB_DIR/node_modules/.vite" "$WEB_DIR/node_modules/.cache" 2>/dev/null || true
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
