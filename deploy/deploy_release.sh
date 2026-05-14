#!/bin/bash
set -euo pipefail

# Cleanup lock file on exit (normal or error)
cleanup_lock() {
  [ -n "${LOCK_FILE:-}" ] && rm -f "$LOCK_FILE"
  exec 9>&- 2>/dev/null || true
}
trap cleanup_lock EXIT

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
RELEASES_DIR="$APP_ROOT/releases"
SHARED_DIR="$APP_ROOT/shared"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
VENV_DIR="${VENV_DIR:-$APP_ROOT/venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PYTHON_ENVS_DIR="${PYTHON_ENVS_DIR:-$SHARED_DIR/python-envs}"
SHARED_BROWSERS_DIR="${SHARED_BROWSERS_DIR:-$SHARED_DIR/browsers}"
SHARED_WEB_DEPS_ROOT="${SHARED_WEB_DEPS_ROOT:-$SHARED_DIR/web-deps}"
SHARED_WEB_NODE_MODULES="${SHARED_WEB_NODE_MODULES:-$SHARED_DIR/web-node_modules}"
SYSTEMD_TARGET="${SYSTEMD_TARGET:-presek.target}"
NGINX_SERVICE="${NGINX_SERVICE:-nginx}"
SYNC_NGINX_SNIPPETS="${SYNC_NGINX_SNIPPETS:-1}"
ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-1}"
ENABLE_ADMIN_CHECK="${ENABLE_ADMIN_CHECK:-1}"
SKIP_RESTART="${SKIP_RESTART:-0}"
REQUIRE_CLEAN_GIT="${REQUIRE_CLEAN_GIT:-1}"
REQUIRE_PUSHED_GIT="${REQUIRE_PUSHED_GIT:-1}"
REQUIRE_WEB_LOCKFILE="${REQUIRE_WEB_LOCKFILE:-1}"
ALLOW_NPM_INSTALL_FALLBACK="${ALLOW_NPM_INSTALL_FALLBACK:-0}"
REQUIRE_ENCRYPTED_BACKUPS="${REQUIRE_ENCRYPTED_BACKUPS:-1}"
SMOKE_SCRIPT="$SOURCE_ROOT/deploy/smoke_check.sh"
BACKUP_SCRIPT="$SOURCE_ROOT/deploy/backup_postgres.sh"
RELEASE_ID="${RELEASE_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
RUN_TESTS="${RUN_TESTS:-0}"
BACKUP_BEFORE_MIGRATIONS="${BACKUP_BEFORE_MIGRATIONS:-1}"
MIN_FREE_DISK_GB="${MIN_FREE_DISK_GB:-8}"

# Environment Validation
validate_env() {
  info "Validating environment configuration"
  local env_file="$SHARED_DIR/.env"
  [ -f "$env_file" ] || fail "Missing shared env file at $env_file"
  
  # Check for essential variables (e.g., DATABASE_URL, REDIS_URL)
  local required_vars=("DATABASE_URL" "REDIS_URL")
  for var in "${required_vars[@]}"; do
    if ! grep -q "^$var=" "$env_file"; then
      fail "Missing required environment variable in $env_file: $var"
    fi
  done
  ok "Environment configuration valid"
}

# Logging
LOG_FILE="$SHARED_DIR/logs/deploy-$(date +%Y%m%d).log"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting deployment: $RELEASE_ID"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
log_msg() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
ok()   { log_msg "${GREEN}✓${RESET}  $*"; }
warn() { log_msg "${YELLOW}!${RESET}  $*"; }
info() { log_msg "${BLUE}>${RESET}  $*"; }
fail() { log_msg "${RED}x${RESET}  $*"; [ -n "${RELEASE_ID:-}" ] && notify_deploy "Deployment failed for release $RELEASE_ID: $*" "danger"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

notify_deploy() {
  local msg="$1"
  local color="${2:-good}" # good (green), warning (yellow), danger (red)
  local webhook_url
  webhook_url="$(env -i bash -c 'set -a; source "$1"; set +a; printf "%s" "${DEPLOY_WEBHOOK_URL:-}"' _ "$SHARED_DIR/.env" 2>/dev/null || true)"
  [ -n "$webhook_url" ] || return 0
  
  info "Sending deployment notification"
  # Support Slack-style JSON payload
  curl -s -X POST -H 'Content-type: application/json' \
    --data "{\"attachments\":[{\"color\":\"$color\",\"text\":\"*Presek Deploy*: $msg\"}]}" \
    "$webhook_url" >/dev/null 2>&1 || true
}

assert_disk_space() {
  info "Checking available disk space"
  local free_kb
  free_kb="$(df -k "$APP_ROOT" | awk 'NR==2 {print $4}')"
  local free_gb=$((free_kb / 1024 / 1024))
  if [ "$free_gb" -lt "$MIN_FREE_DISK_GB" ]; then
    fail "Insufficient disk space: ${free_gb}GB free, but ${MIN_FREE_DISK_GB}GB required."
  fi
  ok "Disk space check passed (${free_gb}GB free)"
}

discover_app_services() {
  info "Discovering Presek systemd services"
  
  local SYSTEMD_DIR="$SOURCE_ROOT/deploy/systemd"
  
  # Discover all unit files from the source directory (same as install_server.sh)
  local all_units=()
  while IFS= read -r -d '' file; do
    all_units+=("$(basename "$file")")
  done < <(find "$SYSTEMD_DIR" -maxdepth 1 -type f \( -name "*.service" -o -name "*.target" -o -name "*.timer" \) -print0 2>/dev/null || true)
  
  # Filter to only service files (exclude targets and timers for service management)
  # Also exclude oneshot services that shouldn't be part of the 'active' check
  local services=()
  for unit in "${all_units[@]}"; do
    if [[ "$unit" == *.service ]]; then
      # Exclude oneshot/timer-only services
      if [[ "$unit" == "cloudflare-realip-update.service" ]]; then
        info "Skipping oneshot service: $unit"
        continue
      fi
      services+=("$unit")
    fi
  done
  
  if [ "${#services[@]}" -eq 0 ]; then
    fail "No application services found in $SYSTEMD_DIR"
  fi
  
  APP_SERVICES=("${services[@]}")
  info "Discovered ${#APP_SERVICES[@]} services: ${APP_SERVICES[*]}"
}

cleanup_listener_port() {
  local port="$1"
  local label="$2"
  local pids=""
  pids="$(sudo lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  [ -n "$pids" ] || return 0

  local runtime_pids=()
  local pid=""
  for pid in $pids; do
    if pid_belongs_to_runtime "$pid"; then
      runtime_pids+=("$pid")
    else
      warn "Leaving non-Presek $label listener on port $port (pid $pid)"
    fi
  done

  [ "${#runtime_pids[@]}" -gt 0 ] || return 0

  warn "Stopping existing $label listener(s) on port $port: ${runtime_pids[*]}"
  sudo kill "${runtime_pids[@]}" 2>/dev/null || true
  
  # Wait and verify
  local i
  for i in {1..5}; do
    sleep 1
    pids="$(sudo lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
    [ -n "$pids" ] || break
  done

  pids="$(sudo lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  if [ -n "$pids" ]; then
    local stubborn_pids=()
    for pid in $pids; do
      if pid_belongs_to_runtime "$pid"; then
        stubborn_pids+=("$pid")
      fi
    done
    if [ "${#stubborn_pids[@]}" -gt 0 ]; then
      warn "Force killing stubborn $label listener(s) on port $port: ${stubborn_pids[*]}"
      sudo kill -9 "${stubborn_pids[@]}" 2>/dev/null || true
      sleep 1
    fi
  fi
}

pid_belongs_to_runtime() {
  local pid="$1"
  [ -d "/proc/$pid" ] || return 1

  local cwd=""
  local exe=""
  local cmd=""
  cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
  exe="$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)"
  cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"

  [[ "$cwd" == "$APP_ROOT/"* ]] && return 0
  [[ "$exe" == "$APP_ROOT/"* ]] && return 0
  [[ "$cmd" == *"$APP_ROOT/"* ]] && return 0
  return 1
}

cleanup_orphaned_runtime_listeners() {
  info "Clearing any orphaned runtime listeners before restart"
  cleanup_listener_port 5001 "FastAPI"
  cleanup_listener_port 3000 "Astro"
}

hash_file() {
  local path="$1"
  sha256sum "$path" | awk '{print $1}'
}

assert_paths_safe() {
  local source_real app_real
  source_real="$(cd "$SOURCE_ROOT" && pwd -P)"
  app_real="$(mkdir -p "$APP_ROOT" && cd "$APP_ROOT" && pwd -P)"
  [ "$source_real" != "$app_real" ] || fail "APP_ROOT must differ from SOURCE_ROOT for release-based deploys"
}

assert_git_deployable() {
  if [ "$REQUIRE_CLEAN_GIT" != "1" ]; then
    warn "Skipping clean git check (REQUIRE_CLEAN_GIT=0)"
    return 0
  fi

  if ! git -C "$SOURCE_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn "Skipping clean git check: $SOURCE_ROOT is not a git worktree"
    return 0
  fi

  local dirty=""
  dirty="$(git -C "$SOURCE_ROOT" status --porcelain --untracked-files=all)"
  [ -z "$dirty" ] || fail "Source tree has uncommitted changes. Deploy from a clean commit or set REQUIRE_CLEAN_GIT=0 intentionally."
}

assert_git_pushed() {
  if [ "$REQUIRE_PUSHED_GIT" != "1" ]; then
    warn "Skipping pushed git check (REQUIRE_PUSHED_GIT=0)"
    return 0
  fi

  if ! git -C "$SOURCE_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn "Skipping pushed git check: $SOURCE_ROOT is not a git worktree"
    return 0
  fi

  local upstream=""
  upstream="$(git -C "$SOURCE_ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  [ -n "$upstream" ] || fail "Current branch has no upstream. Push it first or set REQUIRE_PUSHED_GIT=0 intentionally."

  local head_sha upstream_sha
  head_sha="$(git -C "$SOURCE_ROOT" rev-parse HEAD)"
  upstream_sha="$(git -C "$SOURCE_ROOT" rev-parse '@{u}')"
  [ "$head_sha" = "$upstream_sha" ] || fail "Local HEAD differs from $upstream. Push or pull before deploying, or set REQUIRE_PUSHED_GIT=0 intentionally."
}

assert_web_lockfile() {
  [ "$REQUIRE_WEB_LOCKFILE" = "1" ] || return 0
  [ -f "$SOURCE_ROOT/web/package-lock.json" ] || fail "web/package-lock.json is required for reproducible deploys"
  if git -C "$SOURCE_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$SOURCE_ROOT" ls-files --error-unmatch web/package-lock.json >/dev/null 2>&1 \
      || fail "web/package-lock.json exists but is not tracked by git"
  fi
}

normalize_legacy_runtime_links() {
  if [ -d "$VENV_DIR" ] && [ ! -L "$VENV_DIR" ]; then
    local legacy_venv="$PYTHON_ENVS_DIR/legacy-runtime"
    if [ ! -e "$legacy_venv" ]; then
      info "Migrating legacy runtime venv into versioned storage"
      mv "$VENV_DIR" "$legacy_venv"
    fi
    ln -sfn "$legacy_venv" "$VENV_DIR"
  fi
}

ensure_layout() {
  install -d "$RELEASES_DIR" "$SHARED_DIR" "$SHARED_DIR/logs" "$SHARED_DIR/backups" "$SHARED_DIR/static/uploads" "$SHARED_DIR/static/generated" "$PYTHON_ENVS_DIR" "$SHARED_WEB_DEPS_ROOT" "$SHARED_BROWSERS_DIR"
  [ -f "$SHARED_DIR/.env" ] || fail "Missing shared env file at $SHARED_DIR/.env"
  [ -x "$VENV_DIR/bin/uvicorn" ] || fail "Missing Python runtime at $VENV_DIR/bin/uvicorn"
  [ -d "$SHARED_WEB_NODE_MODULES" ] || fail "Missing shared Astro dependencies at $SHARED_WEB_NODE_MODULES. Run deploy/bootstrap_runtime_root.sh first."
  [ -f "$SOURCE_ROOT/web/package.json" ] || fail "Missing Astro app at $SOURCE_ROOT/web/package.json"
  # Validate shared models directory exists for symlinking
  install -d "$SHARED_DIR/models"
}

copy_release_tree() {
  info "Copying source tree into $RELEASE_DIR"
  rsync -a \
    --exclude '.git/' \
    --exclude '.pytest_cache/' \
    --exclude '__pycache__/' \
    --exclude '.mypy_cache/' \
    --exclude '.ruff_cache/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude 'node_modules/' \
    --exclude 'web/node_modules/' \
    --exclude 'web/dist/' \
    --exclude 'logs/' \
    --exclude 'backups/' \
    --exclude 'screenshots/' \
    --exclude 'shared/' \
    --exclude 'releases/' \
    --exclude 'current' \
    --exclude 'previous' \
    --exclude '.runtime-meta' \
    --exclude '.env' \
    --exclude 'presek.db' \
    --exclude 'list_gemini_models.py' \
    --exclude 'test_gemini_key.py' \
    --exclude 'static/uploads/*' \
    --exclude 'static/generated/*' \
    --exclude 'models/' \
    "$SOURCE_ROOT/" "$RELEASE_DIR/" || fail "rsync failed to copy source tree"
  
  # Validate key files were copied
  [ -f "$RELEASE_DIR/api_fast.py" ] || fail "api_fast.py missing after copy"
  [ -f "$RELEASE_DIR/celery_app.py" ] || fail "celery_app.py missing after copy"
  [ -f "$RELEASE_DIR/web/package.json" ] || fail "web/package.json missing after copy"
  [ -f "$RELEASE_DIR/web-mk/package.json" ] || fail "web-mk/package.json missing after copy"
}

prepare_release_runtime_links() {
  ln -sfn "$SHARED_DIR/.env" "$RELEASE_DIR/.env"
  rm -rf "$RELEASE_DIR/models"
  ln -sfnT "$SHARED_DIR/models" "$RELEASE_DIR/models"
  mkdir -p "$RELEASE_DIR/static"
  rm -rf "$RELEASE_DIR/static/uploads" "$RELEASE_DIR/static/generated"
  ln -sfnT "$SHARED_DIR/static/uploads" "$RELEASE_DIR/static/uploads"
  ln -sfnT "$SHARED_DIR/static/generated" "$RELEASE_DIR/static/generated"
}

ensure_playwright_browsers() {
  if "$RELEASE_VENV_TARGET/bin/python3" -c "import playwright" >/dev/null 2>&1; then
    info "Ensuring Playwright Chromium browser is installed in $SHARED_BROWSERS_DIR"
    export PLAYWRIGHT_BROWSERS_PATH="$SHARED_BROWSERS_DIR"
    "$RELEASE_VENV_TARGET/bin/python3" -m playwright install chromium
  fi
}

persist_release_runtime_meta() {
  local target_dir="$1"
  local venv_target="$2"
  local web_target="$3"
  [ -n "$target_dir" ] && [ -d "$target_dir" ] || return 0
  [ "$(cd "$target_dir" && pwd -P)" != "$(cd "$SOURCE_ROOT" && pwd -P)" ] || return 0
  cat > "$target_dir/.runtime-meta" <<EOF
VENV_TARGET=$venv_target
WEB_NODE_MODULES_TARGET=$web_target
SCHEMA_UPDATED=${SCHEMA_UPDATED:-0}
DB_BACKUP_CREATED=${DB_BACKUP_CREATED:-0}
EOF
}

read_release_runtime_meta() {
  local target_dir="$1"
  local key="$2"
  local meta_path="$target_dir/.runtime-meta"
  [ -f "$meta_path" ] || return 1
  sed -n "s/^${key}=//p" "$meta_path" | tail -n 1
}

ensure_release_venv() {
  local lock_hash versioned_venv
  lock_hash="$(hash_file "$RELEASE_DIR/uv.lock")"
  versioned_venv="$PYTHON_ENVS_DIR/$lock_hash"

  if [ ! -x "$versioned_venv/bin/python3" ]; then
    info "Creating versioned Python runtime $versioned_venv using uv"
    rm -rf "$versioned_venv"
    # uv creates environment at the specified path
    # --frozen ensures we use exactly what's in uv.lock
    # --no-dev excludes development dependencies
    # --no-install-project skips installing the current package itself
    UV_PROJECT_ENVIRONMENT="$versioned_venv" uv sync --frozen --no-dev --no-install-project --directory "$RELEASE_DIR" || fail "uv sync failed for versioned venv"
  else
    info "Reusing versioned Python runtime $versioned_venv"
  fi

  # Validate venv was created/exists and has required binaries
  [ -x "$versioned_venv/bin/python3" ] || fail "Versioned Python runtime not found at $versioned_venv/bin/python3"
  [ -x "$versioned_venv/bin/uvicorn" ] || fail "uvicorn not found in versioned venv"
  [ -x "$versioned_venv/bin/celery" ] || fail "celery not found in versioned venv"

  RELEASE_VENV_TARGET="$versioned_venv"
}

ensure_release_web_deps() {
  local lock_source deps_hash versioned_web_deps
  lock_source="$RELEASE_DIR/web/package-lock.json"
  if [ ! -f "$lock_source" ]; then
    if [ "$REQUIRE_WEB_LOCKFILE" = "1" ]; then
      fail "Release is missing web/package-lock.json"
    fi
    lock_source="$RELEASE_DIR/web/package.json"
  fi
  deps_hash="$(hash_file "$lock_source")"
  versioned_web_deps="$SHARED_WEB_DEPS_ROOT/$deps_hash"

  if [ ! -d "$versioned_web_deps/node_modules" ]; then
    info "Installing versioned Astro dependencies $versioned_web_deps"
    rm -rf "$versioned_web_deps"
    install -d "$versioned_web_deps"
    cp "$RELEASE_DIR/web/package.json" "$versioned_web_deps/"
    
    if [ -f "$RELEASE_DIR/web/package-lock.json" ]; then
      cp "$RELEASE_DIR/web/package-lock.json" "$versioned_web_deps/"
      info "Installing Astro dependencies with npm ci"
      (cd "$versioned_web_deps" && npm ci) || {
        if [ "$ALLOW_NPM_INSTALL_FALLBACK" = "1" ]; then
          warn "npm ci failed; falling back to npm install (ALLOW_NPM_INSTALL_FALLBACK=1)"
          (cd "$versioned_web_deps" && npm install) || fail "npm install fallback failed"
        else
          fail "npm ci failed. Fix package-lock.json or set ALLOW_NPM_INSTALL_FALLBACK=1 intentionally."
        fi
      }
    else
      warn "package-lock.json missing; using npm install"
      (cd "$versioned_web_deps" && npm install) || fail "npm install failed"
    fi
  else
    info "Reusing versioned Astro dependencies $versioned_web_deps"
  fi

  # Validate node_modules exists
  [ -d "$versioned_web_deps/node_modules" ] || fail "node_modules not found at $versioned_web_deps/node_modules"

  RELEASE_WEB_NODE_MODULES_TARGET="$versioned_web_deps/node_modules"
}

update_active_runtime_links() {
  local venv_target="$1"
  local web_target="$2"
  local temp_venv="$APP_ROOT/.venv.$$"
  local temp_web="$APP_ROOT/.web-node_modules.$$"
  
  # Cleanup any stale temp links from previous failed runs
  rm -f "$temp_venv" "$temp_web"
  
  ln -sfn "$venv_target" "$temp_venv" || fail "Failed to create temp venv symlink"
  mv -Tf "$temp_venv" "$VENV_DIR" || fail "Failed to update venv symlink"
  ln -sfn "$web_target" "$temp_web" || fail "Failed to create temp web modules symlink"
  mv -Tf "$temp_web" "$SHARED_WEB_NODE_MODULES" || fail "Failed to update web modules symlink"
  
  # Cleanup temp files
  rm -f "$temp_venv" "$temp_web"
}

build_release() {
  ln -sfn "$RELEASE_WEB_NODE_MODULES_TARGET" "$RELEASE_DIR/web/node_modules"
  ln -sfn "$RELEASE_WEB_NODE_MODULES_TARGET" "$RELEASE_DIR/web-mk/node_modules"
  mkdir -p "$RELEASE_DIR/web/.astro/collections"
  mkdir -p "$RELEASE_DIR/web-mk/.astro/collections"

  info "Building Astro releases"
  (cd "$RELEASE_DIR/web" && npm run build)
  [ -f "$RELEASE_DIR/web/dist/server/entry.mjs" ] || fail "Release build failed for 'web'"
  (cd "$RELEASE_DIR/web-mk" && npm run build)
  [ -f "$RELEASE_DIR/web-mk/dist/server/entry.mjs" ] || fail "Release build failed for 'web-mk'"
}

invalidate_public_api_caches() {
  if ! command -v redis-cli >/dev/null 2>&1; then
    warn "redis-cli not found; skipping public API cache invalidation"
    return 0
  fi

  info "Clearing public API caches"
  local redis_args=()
  if [ -f "$SHARED_DIR/.env" ]; then
    local redis_url=""
    redis_url="$(env -i bash -c 'set -a; source "$1"; set +a; printf "%s" "${REDIS_URL:-}"' _ "$SHARED_DIR/.env")"
    if [ -n "$redis_url" ]; then
      redis_args=(-u "$redis_url")
    fi
  fi
  redis-cli "${redis_args[@]}" EVAL "for _,p in ipairs(ARGV) do local cursor='0' repeat local r=redis.call('scan', cursor, 'match', p, 'count', 200) cursor=r[1] for _,k in ipairs(r[2]) do redis.call('del', k) end until cursor == '0' end" 0 \
    "api:news:*" \
    "api:cluster:*" \
    "api:home:*" \
    "api:stats:summary:*" \
    "api:briefing:*" \
    "api:intelligence:research:*" \
    >/dev/null || warn "Could not clear Redis API caches"
}

run_release_checks() {
  info "Checking Python syntax in release runtime"
  (
    cd "$RELEASE_DIR"
    find . \
      -path './web/node_modules' -prune -o \
      -path './web/dist' -prune -o \
      -path './.venv' -prune -o \
      -path './venv' -prune -o \
      -name '*.py' -print0 \
      | xargs -0 -r "$RELEASE_VENV_TARGET/bin/python3" -m py_compile
  )

  info "Checking FastAPI import in release runtime"
  (cd "$RELEASE_DIR" && "$RELEASE_VENV_TARGET/bin/python3" - <<'PY'
import api_fast
import celery_app
import tasks
PY
  )

  if [ "$RUN_TESTS" = "1" ]; then
    [ -n "${DATABASE_URL:-}" ] || fail "DATABASE_URL must be set when RUN_TESTS=1"
    info "Running pytest before switch"
    (cd "$RELEASE_DIR" && "$RELEASE_VENV_TARGET/bin/pytest" -q)
  fi
}

run_migrations() {
  if [ "$BACKUP_BEFORE_MIGRATIONS" = "1" ]; then
    info "Creating database backup before schema updates"
    REQUIRE_BACKUP_ENCRYPTION="$REQUIRE_ENCRYPTED_BACKUPS" APP_ROOT="$APP_ROOT" bash "$BACKUP_SCRIPT" || fail "Database backup failed"
    DB_BACKUP_CREATED=1
  else
    warn "Skipping pre-migration database backup (BACKUP_BEFORE_MIGRATIONS=0)"
  fi

  info "Running database schema updates"
  # Try Alembic first, fallback to legacy init_db if needed
  if [ -f "$RELEASE_DIR/alembic.ini" ]; then
    (cd "$RELEASE_DIR" && "$RELEASE_VENV_TARGET/bin/alembic" upgrade head) || fail "Alembic migrations failed"
  else
    (cd "$RELEASE_DIR" && "$RELEASE_VENV_TARGET/bin/python3" -c "import config; from database import init_db; init_db()") || fail "Legacy schema init failed"
  fi
  SCHEMA_UPDATED=1
}

switch_current_link() {
  local target="$1"
  local temp_link="$APP_ROOT/.current.$$"
  ln -sfn "$target" "$temp_link"
  mv -Tf "$temp_link" "$CURRENT_LINK"
}

restart_and_smoke() {
  if [ "$SKIP_RESTART" = "1" ]; then
    info "Skipping nginx reload, service restart, and smoke checks"
    return 0
  fi

  if [ "$SYNC_NGINX_SNIPPETS" = "1" ]; then
    info "Syncing nginx snippets"
    sudo install -d /etc/nginx/snippets || return 1
    
    # Backup existing snippets for potential rollback
    [ -f /etc/nginx/snippets/presek-security-headers.conf ] && sudo cp /etc/nginx/snippets/presek-security-headers.conf /etc/nginx/snippets/presek-security-headers.conf.bak
    [ -f /etc/nginx/snippets/presek-routes.conf ] && sudo cp /etc/nginx/snippets/presek-routes.conf /etc/nginx/snippets/presek-routes.conf.bak

    if ! sudo cp "$RELEASE_DIR/deploy/nginx/security-headers.conf" /etc/nginx/snippets/presek-security-headers.conf || \
       ! sudo cp "$RELEASE_DIR/deploy/nginx/presek-routes.conf" /etc/nginx/snippets/presek-routes.conf; then
      warn "Failed to copy nginx snippets; restoring backups"
      [ -f /etc/nginx/snippets/presek-security-headers.conf.bak ] && sudo mv /etc/nginx/snippets/presek-security-headers.conf.bak /etc/nginx/snippets/presek-security-headers.conf
      [ -f /etc/nginx/snippets/presek-routes.conf.bak ] && sudo mv /etc/nginx/snippets/presek-routes.conf.bak /etc/nginx/snippets/presek-routes.conf
      return 1
    fi
    
    # Sync nginx site configurations for both Serbian (presek.live) and Macedonian (presek.mk)
    info "Syncing nginx site configurations"
    sudo install -d /etc/nginx/sites-available || return 1
    sudo install -d /etc/nginx/sites-enabled || return 1
    
    # Backup existing site configs for rollback
    [ -f /etc/nginx/sites-available/presek.live.conf ] && sudo cp /etc/nginx/sites-available/presek.live.conf /etc/nginx/sites-available/presek.live.conf.bak
    [ -f /etc/nginx/sites-available/presek-mk.conf ] && sudo cp /etc/nginx/sites-available/presek-mk.conf /etc/nginx/sites-available/presek-mk.conf.bak
    [ -L /etc/nginx/sites-enabled/presek.live.conf ] && sudo cp /etc/nginx/sites-enabled/presek.live.conf /tmp/presek.live.conf.bak 2>/dev/null
    [ -L /etc/nginx/sites-enabled/presek-mk.conf ] && sudo cp /etc/nginx/sites-enabled/presek-mk.conf /tmp/presek-mk.conf.bak 2>/dev/null

    if ! sudo cp "$RELEASE_DIR/deploy/nginx/presek.live.conf" /etc/nginx/sites-available/presek.live.conf || \
       ! sudo cp "$RELEASE_DIR/deploy/nginx/presek-mk.conf" /etc/nginx/sites-available/presek-mk.conf; then
      warn "Failed to copy nginx site configs; restoring backups"
      [ -f /etc/nginx/sites-available/presek.live.conf.bak ] && sudo mv /etc/nginx/sites-available/presek.live.conf.bak /etc/nginx/sites-available/presek.live.conf
      [ -f /etc/nginx/sites-available/presek-mk.conf.bak ] && sudo mv /etc/nginx/sites-available/presek-mk.conf.bak /etc/nginx/sites-available/presek-mk.conf
      return 1
    fi
    
    # Enable both site configs
    sudo ln -sf /etc/nginx/sites-available/presek.live.conf /etc/nginx/sites-enabled/presek.live.conf || return 1
    sudo ln -sf /etc/nginx/sites-available/presek-mk.conf /etc/nginx/sites-enabled/presek-mk.conf || return 1
  fi

  info "Validating nginx configuration"
  if ! sudo nginx -t; then
    warn "Nginx configuration invalid; restoring snippet backups"
    if [ "$SYNC_NGINX_SNIPPETS" = "1" ]; then
      [ -f /etc/nginx/snippets/presek-security-headers.conf.bak ] && sudo mv /etc/nginx/snippets/presek-security-headers.conf.bak /etc/nginx/snippets/presek-security-headers.conf
      [ -f /etc/nginx/snippets/presek-routes.conf.bak ] && sudo mv /etc/nginx/snippets/presek-routes.conf.bak /etc/nginx/snippets/presek-routes.conf
    fi
    return 1
  fi

  # Cleanup backups on success
  [ -f /etc/nginx/snippets/presek-security-headers.conf.bak ] && sudo rm /etc/nginx/snippets/presek-security-headers.conf.bak
  [ -f /etc/nginx/snippets/presek-routes.conf.bak ] && sudo rm /etc/nginx/snippets/presek-routes.conf.bak

  info "Reloading $NGINX_SERVICE"
  sudo systemctl reload "$NGINX_SERVICE" || return 1

  cleanup_orphaned_runtime_listeners

  wait_for_services() {
    info "Waiting for application services to be ready"
    local max_attempts=10
    local attempt=1
    while [ $attempt -le $max_attempts ]; do
      local all_ready=1
      for service in "${APP_SERVICES[@]}"; do
        if ! systemctl is-active --quiet "$service"; then
          all_ready=0
          break
        fi
      done

      if [ $all_ready -eq 1 ]; then
        ok "All services are active"
        return 0
      fi

      warn "Services not ready (attempt $attempt/$max_attempts), waiting..."
      sleep 3
      attempt=$((attempt + 1))
    done

    fail "Services failed to become active after restart"
  }

  info "Restarting application services"
  sudo systemctl restart "${APP_SERVICES[@]}" || return 1
  sudo systemctl start "$SYSTEMD_TARGET" || return 1
  wait_for_services || return 1

  info "Running smoke checks"
  ENABLE_PUBLIC_CHECK="$ENABLE_PUBLIC_CHECK" ENABLE_ADMIN_CHECK="$ENABLE_ADMIN_CHECK" APP_ROOT="$APP_ROOT" bash "$SMOKE_SCRIPT" || return 1
}

rollback_release() {
  local failed_release="$1"
  local previous_target="$2"
  local current_venv_target="$3"
  local current_web_deps_target="$4"
  local failed_release_schema_updated=""
  local failed_release_backup_created=""

  [ -n "$previous_target" ] && [ -d "$previous_target" ] || return 1

  failed_release_schema_updated="$(read_release_runtime_meta "$failed_release" "SCHEMA_UPDATED" || true)"
  failed_release_backup_created="$(read_release_runtime_meta "$failed_release" "DB_BACKUP_CREATED" || true)"

  warn "Deploy failed smoke checks; restoring previous release"
  switch_current_link "$previous_target"
  ln -sfn "$failed_release" "$PREVIOUS_LINK"
  update_active_runtime_links "$current_venv_target" "$current_web_deps_target"
  
  # Restore nginx snippets if backups exist
  if [ -f /etc/nginx/snippets/presek-security-headers.conf.bak ]; then
    info "Restoring nginx security headers from backup"
    sudo mv /etc/nginx/snippets/presek-security-headers.conf.bak /etc/nginx/snippets/presek-security-headers.conf || warn "Failed to restore nginx security headers"
  fi
  if [ -f /etc/nginx/snippets/presek-routes.conf.bak ]; then
    info "Restoring nginx routes from backup"
    sudo mv /etc/nginx/snippets/presek-routes.conf.bak /etc/nginx/snippets/presek-routes.conf || warn "Failed to restore nginx routes"
  fi
  
  # Restore nginx site configurations if backups exist
  if [ -f /etc/nginx/sites-available/presek.live.conf.bak ]; then
    info "Restoring nginx site config for presek.live from backup"
    sudo mv /etc/nginx/sites-available/presek.live.conf.bak /etc/nginx/sites-available/presek.live.conf || warn "Failed to restore presek.live nginx config"
  fi
  if [ -f /etc/nginx/sites-available/presek-mk.conf.bak ]; then
    info "Restoring nginx site config for presek.mk from backup"
    sudo mv /etc/nginx/sites-available/presek-mk.conf.bak /etc/nginx/sites-available/presek-mk.conf || warn "Failed to restore presek.mk nginx config"
  fi
  if [ -f /tmp/presek.live.conf.bak ]; then
    sudo cp /tmp/presek.live.conf.bak /etc/nginx/sites-enabled/presek.live.conf || warn "Failed to restore presek.live enabled config"
    sudo rm -f /tmp/presek.live.conf.bak
  fi
  if [ -f /tmp/presek-mk.conf.bak ]; then
    sudo cp /tmp/presek-mk.conf.bak /etc/nginx/sites-enabled/presek-mk.conf || warn "Failed to restore presek.mk enabled config"
    sudo rm -f /tmp/presek-mk.conf.bak
  fi
  
  cleanup_orphaned_runtime_listeners
  sudo systemctl restart "${APP_SERVICES[@]}" || return 1
  sudo systemctl start "$SYSTEMD_TARGET" || return 1
  
  # Validate nginx config after rollback
  if ! sudo nginx -t 2>/dev/null; then
    warn "Nginx configuration invalid after rollback. Manual intervention required."
  else
    sudo systemctl reload "$NGINX_SERVICE" || warn "Failed to reload nginx after rollback"
  fi
  
  if [ "$failed_release_schema_updated" = "1" ]; then
    if [ "$failed_release_backup_created" = "1" ]; then
      warn "Code rollback completed after schema updates. Restore the pre-deploy database backup if the previous release is not schema-compatible."
    else
      warn "Code rollback completed after schema updates without an automatic backup. Verify backward compatibility before trusting the restored release."
    fi
  fi
  info "Running post-rollback smoke checks"
  ENABLE_PUBLIC_CHECK="$ENABLE_PUBLIC_CHECK" ENABLE_ADMIN_CHECK="$ENABLE_ADMIN_CHECK" APP_ROOT="$APP_ROOT" bash "$SMOKE_SCRIPT" || warn "Post-rollback smoke checks also failed"
}

# Flags
DRY_RUN="${DRY_RUN:-0}"
if [ "${1:-}" == "--dry-run" ]; then
  DRY_RUN=1
  shift
fi

generate_manifest() {
  local manifest_path="$RELEASE_DIR/manifest.json"
  info "Generating release manifest"
  cat > "$manifest_path" <<EOF
{
  "release_id": "$RELEASE_ID",
  "deployed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "git_sha": "$(git -C "$SOURCE_ROOT" rev-parse HEAD 2>/dev/null || echo "unknown")",
  "deployed_by": "$(whoami)"
}
EOF
}

main() {
  need_cmd rsync
  need_cmd npm
  need_cmd sudo
  need_cmd bash
  need_cmd sed
  need_cmd flock
  need_cmd sha256sum
  need_cmd uv
  need_cmd curl
  need_cmd "$PYTHON_BIN"

  assert_paths_safe
  assert_disk_space
  assert_git_deployable
  assert_git_pushed
  assert_web_lockfile
  validate_env
  ensure_layout
  normalize_legacy_runtime_links
  discover_app_services

  # Acquire exclusive deploy lock to prevent concurrent deploys
  LOCK_FILE="$APP_ROOT/.deploy.lock"
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "Another deploy is already in progress (lock: $LOCK_FILE)"

  [ ! -e "$RELEASE_DIR" ] || fail "Release already exists: $RELEASE_DIR"

  local previous_target=""
  local current_venv_target=""
  local current_web_deps_target=""
  DB_BACKUP_CREATED=0
  SCHEMA_UPDATED=0
  if [ -L "$CURRENT_LINK" ]; then
    previous_target="$(readlink -f "$CURRENT_LINK" || true)"
  fi
  if [ -L "$VENV_DIR" ]; then
    current_venv_target="$(readlink -f "$VENV_DIR" || true)"
  fi
  if [ -L "$SHARED_WEB_NODE_MODULES" ]; then
    current_web_deps_target="$(readlink -f "$SHARED_WEB_NODE_MODULES" || true)"
  fi
  [ -n "$current_venv_target" ] || fail "Could not resolve active Python runtime from $VENV_DIR"
  [ -n "$current_web_deps_target" ] || fail "Could not resolve active Astro dependencies from $SHARED_WEB_NODE_MODULES"

# ...
  # 1. Prepare environment and copy source
  copy_release_tree
  generate_manifest

  if [ "$DRY_RUN" = "1" ]; then
    ok "Dry run complete: release tree copied to $RELEASE_DIR and manifest generated. Exiting."
    exit 0
  fi

  prepare_release_runtime_links
# ...
  ensure_release_venv
  ensure_playwright_browsers
  ensure_release_web_deps
  
  # 2. Build and verify
  build_release
  run_release_checks
  
  if [ "${BUMP_VERSION:-0}" = "1" ]; then
    fail "BUMP_VERSION is no longer supported during deploy. Bump VERSION, web/package.json, and web/package-lock.json before committing and deploying."
  fi

  # 4. Database migrations
  run_migrations

  # 5. Atomic switch
  persist_release_runtime_meta "$RELEASE_DIR" "$RELEASE_VENV_TARGET" "$RELEASE_WEB_NODE_MODULES_TARGET"
  persist_release_runtime_meta "$previous_target" "$current_venv_target" "$current_web_deps_target"

  info "Switching current release to $RELEASE_ID"
  switch_current_link "$RELEASE_DIR"
  if [ -n "$previous_target" ] && [ -d "$previous_target" ]; then
    ln -sfn "$previous_target" "$PREVIOUS_LINK"
  fi
  update_active_runtime_links "$RELEASE_VENV_TARGET" "$RELEASE_WEB_NODE_MODULES_TARGET"
  invalidate_public_api_caches

  # 6. Restart services
  if ! restart_and_smoke; then
    rollback_release "$RELEASE_DIR" "$previous_target" "$current_venv_target" "$current_web_deps_target" || warn "Rollback did not complete cleanly"
    fail "Release deploy failed"
  fi

  # 7. Auto-prune old releases
  info "Pruning old releases"
  DRY_RUN=0 KEEP_EXTRA=3 APP_ROOT="$APP_ROOT" bash "$SOURCE_ROOT/deploy/prune_releases.sh" || warn "Cleanup failed"

  notify_deploy "Release $RELEASE_ID deployed successfully to $APP_ROOT" "good"
  ok "Release deployed successfully"
  ok "Current release: $RELEASE_ID"
}

main "$@"
