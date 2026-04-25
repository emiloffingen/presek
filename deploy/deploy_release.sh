#!/bin/bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
RELEASES_DIR="$APP_ROOT/releases"
SHARED_DIR="$APP_ROOT/shared"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
VENV_DIR="${VENV_DIR:-$APP_ROOT/venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PYTHON_ENVS_DIR="${PYTHON_ENVS_DIR:-$SHARED_DIR/python-envs}"
SHARED_WEB_DEPS_ROOT="${SHARED_WEB_DEPS_ROOT:-$SHARED_DIR/web-deps}"
SHARED_WEB_NODE_MODULES="${SHARED_WEB_NODE_MODULES:-$SHARED_DIR/web-node_modules}"
SYSTEMD_TARGET="${SYSTEMD_TARGET:-presek.target}"
NGINX_SERVICE="${NGINX_SERVICE:-nginx}"
ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-1}"
SKIP_RESTART="${SKIP_RESTART:-0}"
SMOKE_SCRIPT="$SOURCE_ROOT/deploy/smoke_check.sh"
BACKUP_SCRIPT="$SOURCE_ROOT/deploy/backup_postgres.sh"
RELEASE_ID="${RELEASE_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
RUN_TESTS="${RUN_TESTS:-0}"
BACKUP_BEFORE_MIGRATIONS="${BACKUP_BEFORE_MIGRATIONS:-1}"
APP_SERVICES=(
  presek-fastapi.service
  presek-astro.service
  presek-worker.service
  presek-worker-ingestion.service
  presek-worker-delivery.service
  presek-beat.service
)

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
info() { echo -e "${BLUE}>${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

# --- Version Management ---

bump_version() {
  local version_file="$SOURCE_ROOT/VERSION"
  local package_json="$SOURCE_ROOT/web/package.json"
  
  if [ ! -f "$version_file" ]; then
    echo "5.3.0" > "$version_file"
  fi

  local current_version=$(cat "$version_file" | tr -d '[:space:]')
  # Split version into parts (Major.Minor.Patch)
  IFS='.' read -r major minor patch <<< "$current_version"
  
  # Increment minor version (e.g. 5.3 -> 5.4)
  local next_minor=$((minor + 1))
  local next_version="$major.$next_minor.0"
  
  info "Bumping version: $current_version -> $next_version"
  
  # Update VERSION file
  echo "$next_version" > "$version_file"
  
  # Update web/package.json
  if [ -f "$package_json" ]; then
    sed -i "s/\"version\": \".*\"/\"version\": \"$next_version\"/" "$package_json"
  fi
  
  # Commit version bump to git
  cd "$SOURCE_ROOT"
  git add VERSION web/package.json
  git commit -m "Admin: Auto-bump version to $next_version" || true
  cd - > /dev/null
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
  sleep 1

  local remaining=""
  remaining="$(sudo lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  if [ -n "$remaining" ]; then
    local stubborn_pids=()
    for pid in $remaining; do
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
  install -d "$RELEASES_DIR" "$SHARED_DIR" "$SHARED_DIR/logs" "$SHARED_DIR/backups" "$SHARED_DIR/static/uploads" "$SHARED_DIR/static/generated" "$PYTHON_ENVS_DIR" "$SHARED_WEB_DEPS_ROOT"
  [ -f "$SHARED_DIR/.env" ] || fail "Missing shared env file at $SHARED_DIR/.env"
  [ -x "$VENV_DIR/bin/uvicorn" ] || fail "Missing Python runtime at $VENV_DIR/bin/uvicorn"
  [ -d "$SHARED_WEB_NODE_MODULES" ] || fail "Missing shared Astro dependencies at $SHARED_WEB_NODE_MODULES. Run deploy/bootstrap_runtime_root.sh first."
  [ -f "$SOURCE_ROOT/web/package.json" ] || fail "Missing Astro app at $SOURCE_ROOT/web/package.json"
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
    --exclude 'presek.db' \
    --exclude 'static/uploads/*' \
    --exclude 'static/generated/*' \
    --exclude 'models/' \
    "$SOURCE_ROOT/" "$RELEASE_DIR/"
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

persist_release_runtime_meta() {
  local target_dir="$1"
  local venv_target="$2"
  local web_target="$3"
  [ -n "$target_dir" ] && [ -d "$target_dir" ] || return 0
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
  local requirements_hash versioned_venv
  requirements_hash="$(hash_file "$RELEASE_DIR/requirements.txt")"
  versioned_venv="$PYTHON_ENVS_DIR/$requirements_hash"

  if [ ! -x "$versioned_venv/bin/python3" ]; then
    info "Creating versioned Python runtime $versioned_venv"
    rm -rf "$versioned_venv"
    "$PYTHON_BIN" -m venv "$versioned_venv"
    "$versioned_venv/bin/python3" -m pip install --upgrade pip
    "$versioned_venv/bin/pip" install -q -r "$RELEASE_DIR/requirements.txt"
  else
    info "Reusing versioned Python runtime $versioned_venv"
  fi

  RELEASE_VENV_TARGET="$versioned_venv"
}

ensure_release_web_deps() {
  local lock_source deps_hash versioned_web_deps
  lock_source="$RELEASE_DIR/web/package-lock.json"
  [ -f "$lock_source" ] || lock_source="$RELEASE_DIR/web/package.json"
  deps_hash="$(hash_file "$lock_source")"
  versioned_web_deps="$SHARED_WEB_DEPS_ROOT/$deps_hash"

  if [ ! -d "$versioned_web_deps/node_modules" ]; then
    info "Installing versioned Astro dependencies $versioned_web_deps"
    rm -rf "$versioned_web_deps"
    install -d "$versioned_web_deps"
    cp "$RELEASE_DIR/web/package.json" "$versioned_web_deps/"
    [ ! -f "$RELEASE_DIR/web/package-lock.json" ] || cp "$RELEASE_DIR/web/package-lock.json" "$versioned_web_deps/"
    (cd "$versioned_web_deps" && npm ci)
  else
    info "Reusing versioned Astro dependencies $versioned_web_deps"
  fi

  RELEASE_WEB_NODE_MODULES_TARGET="$versioned_web_deps/node_modules"
}

update_active_runtime_links() {
  local venv_target="$1"
  local web_target="$2"
  local temp_venv="$APP_ROOT/.venv.$$"
  local temp_web="$APP_ROOT/.web-node_modules.$$"
  ln -sfn "$venv_target" "$temp_venv"
  mv -Tf "$temp_venv" "$VENV_DIR"
  ln -sfn "$web_target" "$temp_web"
  mv -Tf "$temp_web" "$SHARED_WEB_NODE_MODULES"
}

build_release() {
  ln -sfn "$RELEASE_WEB_NODE_MODULES_TARGET" "$RELEASE_DIR/web/node_modules"

  info "Building Astro release"
  (cd "$RELEASE_DIR/web" && npm run build)
  [ -f "$RELEASE_DIR/web/dist/server/entry.mjs" ] || fail "Release build did not produce web/dist/server/entry.mjs"
}

run_release_checks() {
  if [ "$RUN_TESTS" = "1" ]; then
    [ -n "${DATABASE_URL:-}" ] || fail "DATABASE_URL must be set when RUN_TESTS=1"
    info "Running pytest before switch"
    (cd "$RELEASE_DIR" && "$RELEASE_VENV_TARGET/bin/pytest" -q)
  fi
}

run_migrations() {
  if [ "$BACKUP_BEFORE_MIGRATIONS" = "1" ]; then
    info "Creating database backup before schema updates"
    APP_ROOT="$APP_ROOT" bash "$BACKUP_SCRIPT"
    DB_BACKUP_CREATED=1
  else
    warn "Skipping pre-migration database backup (BACKUP_BEFORE_MIGRATIONS=0)"
  fi

  info "Running database schema updates"
  (cd "$RELEASE_DIR" && "$RELEASE_VENV_TARGET/bin/python3" -c "import config; from database import init_db; init_db()")
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

  info "Validating nginx configuration"
  sudo nginx -t || return 1

  info "Reloading $NGINX_SERVICE"
  sudo systemctl reload "$NGINX_SERVICE" || return 1

  cleanup_orphaned_runtime_listeners

  info "Restarting application services"
  sudo systemctl restart "${APP_SERVICES[@]}" || return 1
  sudo systemctl start "$SYSTEMD_TARGET" || return 1

  info "Running smoke checks"
  ENABLE_PUBLIC_CHECK="$ENABLE_PUBLIC_CHECK" APP_ROOT="$APP_ROOT" bash "$SMOKE_SCRIPT" || return 1
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
  cleanup_orphaned_runtime_listeners
  sudo systemctl restart "${APP_SERVICES[@]}" || return 1
  sudo systemctl start "$SYSTEMD_TARGET" || return 1
  if [ "$failed_release_schema_updated" = "1" ]; then
    if [ "$failed_release_backup_created" = "1" ]; then
      warn "Code rollback completed after schema updates. Restore the pre-deploy database backup if the previous release is not schema-compatible."
    else
      warn "Code rollback completed after schema updates without an automatic backup. Verify backward compatibility before trusting the restored release."
    fi
  fi
  info "Running post-rollback smoke checks"
  ENABLE_PUBLIC_CHECK="$ENABLE_PUBLIC_CHECK" APP_ROOT="$APP_ROOT" bash "$SMOKE_SCRIPT" || warn "Post-rollback smoke checks also failed"
}

main() {
  need_cmd rsync
  need_cmd npm
  need_cmd sudo
  need_cmd bash
  need_cmd sed
  need_cmd flock
  need_cmd sha256sum
  need_cmd "$PYTHON_BIN"

  assert_paths_safe
  ensure_layout
  normalize_legacy_runtime_links

  # Acquire exclusive deploy lock to prevent concurrent deploys
  LOCK_FILE="$APP_ROOT/.deploy.lock"
  exec 9>"$LOCK_FILE"
  flock -n 9 || fail "Another deploy is already in progress (lock: $LOCK_FILE)"

  # Auto-bump version (5.3 -> 5.4)
  if [ "${BUMP_VERSION:-1}" = "1" ]; then
    bump_version
  fi

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

  copy_release_tree
  prepare_release_runtime_links
  ensure_release_venv
  ensure_release_web_deps
  build_release
  run_release_checks
  run_migrations

  persist_release_runtime_meta "$RELEASE_DIR" "$RELEASE_VENV_TARGET" "$RELEASE_WEB_NODE_MODULES_TARGET"
  persist_release_runtime_meta "$previous_target" "$current_venv_target" "$current_web_deps_target"

  info "Switching current release to $RELEASE_ID"
  switch_current_link "$RELEASE_DIR"
  if [ -n "$previous_target" ] && [ -d "$previous_target" ]; then
    ln -sfn "$previous_target" "$PREVIOUS_LINK"
  fi
  update_active_runtime_links "$RELEASE_VENV_TARGET" "$RELEASE_WEB_NODE_MODULES_TARGET"

  if ! restart_and_smoke; then
    rollback_release "$RELEASE_DIR" "$previous_target" "$current_venv_target" "$current_web_deps_target" || warn "Rollback did not complete cleanly"
    fail "Release deploy failed"
  fi

  ok "Release deployed successfully"
  ok "Current release: $RELEASE_ID"
}

main "$@"
