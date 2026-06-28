#!/bin/bash
# Production Deployment Script for Presek (Lean Core)
# Usage: bash deploy/deploy_release.sh
# Fast modes:
#   DEPLOY_MODE=frontend bash deploy/deploy_release.sh  # build web, restart Astro only
#   DEPLOY_MODE=backend bash deploy/deploy_release.sh   # skip web build, restart API/workers
#   DEPLOY_MODE=workers bash deploy/deploy_release.sh   # restart workers only
#   DEPLOY_MODE=ops bash deploy/deploy_release.sh       # copy release, no build/DB/restart
#   DEPLOY_MODE=fast bash deploy/deploy_release.sh      # skip DB backup/migrations
#
# Environment:
#   DEPLOY_GIT_DIR       Git checkout to pull and deploy from (recommended for CI/manual)
#   DEPLOY_GIT_BRANCH    Branch to deploy (default: main)
#   REQUIRE_DB_BACKUP    Fail deploy if backup fails (default: 1 for full mode)
#   RUN_PREFLIGHT        Run pre-deploy checks (default: 1 for full mode)
#   RUN_SMOKE_CHECKS     Run post-deploy smoke tests (default: 1)
#   AUTO_ROLLBACK_ON_FAILURE  Roll back on smoke/health failure (default: 1)
#   PRUNE_RELEASES       Prune old releases after success (default: 1)

set -euo pipefail

# Cleanup lock file on exit
cleanup_lock() {
  [ -n "${STAGED_SOURCE_DIR:-}" ] && rm -rf "$STAGED_SOURCE_DIR"
  [ -n "${LOCK_FILE:-}" ] && rm -f "$LOCK_FILE"
  exec 9>&- 2>/dev/null || true
}
trap cleanup_lock EXIT

SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COPY_ROOT="$SOURCE_ROOT"
APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
SHARED_DIR="$APP_ROOT/shared"
VENV_DIR="${VENV_DIR:-$APP_ROOT/venv}"
SHARED_WEB_NODE_MODULES="${SHARED_WEB_NODE_MODULES:-$SHARED_DIR/web-node_modules}"
STAGED_SOURCE_DIR=""
SYSTEMD_TARGET="${SYSTEMD_TARGET:-presek.target}"
SKIP_RESTART="${SKIP_RESTART:-0}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-60}"
DEPLOY_MODE="${DEPLOY_MODE:-full}"
RUN_FRONTEND_BUILD=1
RUN_DB_BACKUP=1
RUN_MIGRATIONS=1
RESTART_FASTAPI=1
RESTART_ASTRO=1
RESTART_WORKERS=1
REQUIRE_DB_BACKUP="${REQUIRE_DB_BACKUP:-}"
RUN_PREFLIGHT="${RUN_PREFLIGHT:-}"
RUN_SMOKE_CHECKS="${RUN_SMOKE_CHECKS:-1}"
AUTO_ROLLBACK_ON_FAILURE="${AUTO_ROLLBACK_ON_FAILURE:-1}"
PRUNE_RELEASES="${PRUNE_RELEASES:-1}"
SKIP_RUNTIME_BOOTSTRAP="${SKIP_RUNTIME_BOOTSTRAP:-0}"

# Logging helpers
info() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"; }
error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2; }
ok() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [OK]   $*"; }
warn() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $*"; }
fail() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2; exit 1; }

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

# Discover services dynamically from source directory
discover_app_services() {
    local SYSTEMD_DIR="$1"

    local services=()
    while IFS= read -r -d '' file; do
        services+=("$(basename "$file")")
    done < <(find "$SYSTEMD_DIR" -maxdepth 1 -type f -name "*.service" -print0 2>/dev/null || true)

    if [ "${#services[@]}" -eq 0 ]; then
        fail "No application services found in $SYSTEMD_DIR"
    fi

    echo "${services[@]}"
}

configure_deploy_mode() {
    case "$DEPLOY_MODE" in
        full)
            ;;
        frontend)
            RUN_DB_BACKUP=0
            RUN_MIGRATIONS=0
            RESTART_FASTAPI=0
            RESTART_WORKERS=0
            ;;
        backend)
            RUN_FRONTEND_BUILD=0
            RESTART_ASTRO=0
            ;;
        workers)
            RUN_FRONTEND_BUILD=0
            RUN_DB_BACKUP=0
            RUN_MIGRATIONS=0
            RESTART_FASTAPI=0
            RESTART_ASTRO=0
            ;;
        ops)
            RUN_FRONTEND_BUILD=0
            RUN_DB_BACKUP=0
            RUN_MIGRATIONS=0
            RESTART_FASTAPI=0
            RESTART_ASTRO=0
            RESTART_WORKERS=0
            ;;
        fast)
            RUN_DB_BACKUP=0
            RUN_MIGRATIONS=0
            ;;
        *)
            fail "Unknown DEPLOY_MODE '$DEPLOY_MODE' (expected full, frontend, backend, workers, ops, fast)"
            ;;
    esac

    if [ -z "$REQUIRE_DB_BACKUP" ]; then
        if [ "$RUN_DB_BACKUP" = "1" ]; then
            REQUIRE_DB_BACKUP=1
        else
            REQUIRE_DB_BACKUP=0
        fi
    fi
    if [ -z "$RUN_PREFLIGHT" ]; then
        if [ "$DEPLOY_MODE" = "full" ]; then
            RUN_PREFLIGHT=1
        else
            RUN_PREFLIGHT=0
        fi
    fi

    # Explicit environment overrides. SKIP_*=1 disables; FORCE_*=1 enables.
    if [ "${SKIP_FRONTEND_BUILD:-0}" = "1" ]; then RUN_FRONTEND_BUILD=0; fi
    if [ "${FORCE_FRONTEND_BUILD:-0}" = "1" ]; then RUN_FRONTEND_BUILD=1; fi
    if [ "${SKIP_DB_BACKUP:-0}" = "1" ]; then RUN_DB_BACKUP=0; REQUIRE_DB_BACKUP=0; fi
    if [ "${FORCE_DB_BACKUP:-0}" = "1" ]; then RUN_DB_BACKUP=1; REQUIRE_DB_BACKUP=1; fi
    if [ "${SKIP_MIGRATIONS:-0}" = "1" ]; then RUN_MIGRATIONS=0; fi
    if [ "${FORCE_MIGRATIONS:-0}" = "1" ]; then RUN_MIGRATIONS=1; fi
}

resolve_git_source() {
    if [ -z "${DEPLOY_GIT_DIR:-}" ] && [ -d "$SOURCE_ROOT/.git" ]; then
        DEPLOY_GIT_DIR="$SOURCE_ROOT"
        info "Using SOURCE_ROOT as DEPLOY_GIT_DIR: $DEPLOY_GIT_DIR"
    fi

    if [ -z "${DEPLOY_GIT_DIR:-}" ]; then
        return
    fi

    [ -d "$DEPLOY_GIT_DIR" ] || fail "DEPLOY_GIT_DIR does not exist: $DEPLOY_GIT_DIR"
    SOURCE_ROOT="$(cd "$DEPLOY_GIT_DIR" && pwd)"
    COPY_ROOT="$SOURCE_ROOT"

    if [ ! -d "$SOURCE_ROOT/.git" ]; then
        fail "DEPLOY_GIT_DIR is not a git checkout: $SOURCE_ROOT"
    fi

    local branch="${DEPLOY_GIT_BRANCH:-main}"
    info "Updating git source at $SOURCE_ROOT (branch: $branch)"
    cd "$SOURCE_ROOT"
    git fetch origin "$branch" || git fetch origin
    git checkout "$branch"
    git pull --ff-only origin "$branch" || fail "git pull --ff-only failed in $SOURCE_ROOT"
    ok "Git source updated to $(git rev-parse --short HEAD)"
}

guard_against_current_release_source() {
    if [ -n "${DEPLOY_GIT_DIR:-}" ]; then
        return
    fi

    local current_path=""
    if [ -L "$CURRENT_LINK" ]; then
        current_path="$(readlink -f "$CURRENT_LINK")"
        if [ "$SOURCE_ROOT" = "$current_path" ] && [ "${ALLOW_CURRENT_SOURCE:-0}" != "1" ]; then
            fail "Deploy started from the current release ($SOURCE_ROOT). Set DEPLOY_GIT_DIR to your git checkout or ALLOW_CURRENT_SOURCE=1 to override."
        fi
    fi
}

stage_clean_git_source_if_needed() {
    if [ ! -d "$SOURCE_ROOT/.git" ]; then
        info "Source is not a git checkout; deploying working tree from $SOURCE_ROOT"
        return
    fi

    cd "$SOURCE_ROOT"
    local head_ref
    head_ref="$(git rev-parse --short HEAD)"

    if [ -z "$(git status --porcelain)" ]; then
        info "Source tree is clean at $head_ref"
        return
    fi

    if [ "${ALLOW_DIRTY_DEPLOY:-0}" = "1" ]; then
        info "ALLOW_DIRTY_DEPLOY=1 set; deploying dirty working tree from $SOURCE_ROOT at $head_ref"
        return
    fi

    STAGED_SOURCE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/presek-release-src.XXXXXX")"
    info "Source tree is dirty; staging clean git archive of $head_ref at $STAGED_SOURCE_DIR"
    git archive HEAD | tar -x -C "$STAGED_SOURCE_DIR"
    COPY_ROOT="$STAGED_SOURCE_DIR"
}

ensure_runtime_bootstrap() {
    if [ "$SKIP_RUNTIME_BOOTSTRAP" = "1" ] || [ "$DEPLOY_MODE" = "ops" ]; then
        info "Skipping runtime bootstrap for DEPLOY_MODE=$DEPLOY_MODE"
        return
    fi

    local bootstrap_script="$COPY_ROOT/deploy/bootstrap_runtime_root.sh"
    [ -f "$bootstrap_script" ] || fail "Missing bootstrap script: $bootstrap_script"

    info "Ensuring runtime Python and web dependencies are up to date..."
    SOURCE_ROOT="$COPY_ROOT" APP_ROOT="$APP_ROOT" bash "$bootstrap_script"
}

run_preflight_checks() {
    if [ "$RUN_PREFLIGHT" != "1" ]; then
        info "Skipping preflight checks"
        return
    fi

    local preflight_script="$COPY_ROOT/deploy/preflight_check.sh"
    [ -f "$preflight_script" ] || fail "Missing preflight script: $preflight_script"

    info "Running pre-deployment preflight checks..."
    SKIP_SMOKE=1 APP_ROOT="$APP_ROOT" bash "$preflight_script"
}

has_service() {
    local wanted="$1"
    local service
    for service in "${APP_SERVICES[@]}"; do
        [ "$service" = "$wanted" ] && return 0
    done
    return 1
}

unit_is_installed() {
    local unit="$1"
    systemctl list-unit-files "$unit" --no-legend 2>/dev/null | grep -q .
}

wait_http_status() {
    local name="$1"
    local url="$2"
    local expected="${3:-200}"
    local deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
    local code=""

    info "Waiting for $name at $url"
    while [ "$SECONDS" -lt "$deadline" ]; do
        code="$(curl -sS -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || true)"
        if [ "$code" = "$expected" ]; then
            ok "$name responded with HTTP $code"
            return 0
        fi
        sleep 2
    done

    error "$name did not become ready (last HTTP code: ${code:-none})"
    return 1
}

sync_systemd_units() {
    local systemd_dir="$RELEASE_DIR/deploy/systemd"
    if [ ! -d "$systemd_dir" ]; then
        warn "No systemd directory in release; skipping unit sync"
        return 0
    fi

    info "Installing updated systemd units from release..."
    local unit_path unit_name tmp_unit
    for unit_path in "$systemd_dir"/*.service "$systemd_dir"/*.target "$systemd_dir"/*.timer; do
        [ -f "$unit_path" ] || continue
        unit_name="$(basename "$unit_path")"
        tmp_unit="$(mktemp)"
        sed -e "s|/home/emiloffingen/presek-runtime|$APP_ROOT|g" "$unit_path" > "$tmp_unit"
        sudo install -m 644 "$tmp_unit" "/etc/systemd/system/$unit_name"
        rm -f "$tmp_unit"
    done
    sudo systemctl daemon-reload
    ok "Systemd units synced from release"
}

restart_services_in_order() {
    if [ "$SKIP_RESTART" = "1" ]; then
        info "SKIP_RESTART is set, skipping systemctl restart"
        return
    fi

    if [ "$RESTART_WORKERS" = "1" ] || [ "$RESTART_FASTAPI" = "1" ]; then
        sync_systemd_units
    fi

    local remaining_services=()
    local service

    if [ "$RESTART_FASTAPI" = "1" ] && has_service "presek-fastapi-unified.service"; then
        info "Restarting unified FastAPI service"
        sudo systemctl restart presek-fastapi-unified.service
        wait_http_status "FastAPI Unified" "http://127.0.0.1:5001/api/health" || return 1
    fi

    if [ "$RESTART_ASTRO" = "1" ] && has_service "presek-astro.service"; then
        info "Restarting Astro"
        sudo systemctl restart presek-astro.service
        wait_http_status "Astro" "http://127.0.0.1:3000" || return 1
    fi

    if [ "$RESTART_WORKERS" = "1" ]; then
        for service in "${APP_SERVICES[@]}"; do
            case "$service" in
                presek-fastapi-unified.service|presek-astro.service|cloudflare-realip-update.service)
                    ;;
                *)
                    if unit_is_installed "$service"; then
                        remaining_services+=("$service")
                    else
                        warn "Skipping restart for missing unit: $service"
                    fi
                    ;;
            esac
        done
    fi

    if [ "${#remaining_services[@]}" -gt 0 ]; then
        info "Restarting background/support services: ${remaining_services[*]}"
        sudo systemctl restart "${remaining_services[@]}"
    fi

    if [ "$RESTART_FASTAPI" = "1" ] || [ "$RESTART_ASTRO" = "1" ] || [ "$RESTART_WORKERS" = "1" ]; then
        sudo systemctl start "$SYSTEMD_TARGET" || true
    else
        info "No service restarts requested for DEPLOY_MODE=$DEPLOY_MODE"
    fi
    sudo systemctl reload nginx || true
}

switch_current_release() {
    local current_target=""
    if [ -L "$CURRENT_LINK" ]; then
        current_target="$(readlink -f "$CURRENT_LINK")"
    fi

    info "Switching to new release..."
    ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

    if [ -n "$current_target" ] && [ "$current_target" != "$RELEASE_DIR" ] && [ -d "$current_target" ]; then
        ln -sfn "$current_target" "$PREVIOUS_LINK"
    fi
}

warn_about_schema_rollback() {
    if [ "${SCHEMA_UPDATED:-0}" = "1" ]; then
        if [ "${DB_BACKUP_CREATED:-0}" = "1" ]; then
            warn "Code rolled back after schema migrations. Restore the pre-deploy database backup if the previous release is not schema-compatible."
        else
            warn "Code rolled back after schema migrations without an automatic backup. Verify database compatibility before trusting the restored release."
        fi
    fi
}

attempt_auto_rollback() {
    local reason="$1"

    if [ "$AUTO_ROLLBACK_ON_FAILURE" != "1" ]; then
        warn "AUTO_ROLLBACK_ON_FAILURE=0; leaving current release in place after $reason"
        return 1
    fi

    warn "Attempting automatic rollback after $reason"
    rollback_to_previous_release
}

rollback_to_previous_release() {
    local rollback_target=""

    if [ ! -L "$PREVIOUS_LINK" ]; then
        error "No previous release symlink available for rollback"
        return 1
    fi

    rollback_target="$(readlink -f "$PREVIOUS_LINK")"
    [ -d "$rollback_target" ] || fail "Previous release target is missing: $rollback_target"

    info "Rolling back from $(basename "$(readlink -f "$CURRENT_LINK")") to $(basename "$rollback_target")"
    ln -sfn "$rollback_target" "$CURRENT_LINK"
    if ! restart_services_in_order; then
        error "Rollback completed symlink switch but service restart failed"
        return 1
    fi
    warn_about_schema_rollback
    ok "Rollback to $(basename "$rollback_target") completed"
    return 0
}

run_post_deploy_smoke_checks() {
    if [ "$RUN_SMOKE_CHECKS" != "1" ] || [ "$SKIP_RESTART" = "1" ]; then
        info "Skipping post-deploy smoke checks"
        return 0
    fi

    local smoke_script="$RELEASE_DIR/deploy/smoke_check.sh"
    [ -f "$smoke_script" ] || fail "Missing smoke check script: $smoke_script"

    info "Running post-deploy smoke checks..."
    if APP_ROOT="$APP_ROOT" ENABLE_PUBLIC_CHECK="${ENABLE_PUBLIC_CHECK:-1}" ENABLE_MK_PUBLIC_CHECK="${ENABLE_MK_PUBLIC_CHECK:-1}" bash "$smoke_script"; then
        ok "Post-deploy smoke checks passed"
        return 0
    fi

    error "Post-deploy smoke checks failed"
    attempt_auto_rollback "smoke check failure" || true
    return 1
}

prune_old_releases() {
    if [ "$PRUNE_RELEASES" != "1" ]; then
        return
    fi

    local prune_script="$RELEASE_DIR/deploy/prune_releases.sh"
    [ -f "$prune_script" ] || return

    info "Pruning old releases..."
    KEEP_EXTRA="${KEEP_EXTRA:-2}" DRY_RUN=0 APP_ROOT="$APP_ROOT" bash "$prune_script" || warn "Release pruning failed (non-fatal)"
}

install_frontend_dependencies() {
    local web_dir="$1"
    cd "$web_dir"

    if [ -L "$SHARED_WEB_NODE_MODULES" ] || [ -d "$SHARED_WEB_NODE_MODULES" ]; then
        ln -sfn "$SHARED_WEB_NODE_MODULES" "node_modules"
        return
    fi

    if [ -f package-lock.json ]; then
        npm ci --silent
    else
        warn "package-lock.json missing; falling back to npm install"
        npm install --silent
    fi
}

# 1. Environment Validation
info "Validating deployment environment..."
configure_deploy_mode
info "Deploy mode: $DEPLOY_MODE (build=$RUN_FRONTEND_BUILD backup=$RUN_DB_BACKUP migrations=$RUN_MIGRATIONS restart_api=$RESTART_FASTAPI restart_astro=$RESTART_ASTRO restart_workers=$RESTART_WORKERS)"
need_cmd git
need_cmd rsync
need_cmd tar
need_cmd curl
need_cmd sudo
need_cmd flock
if [ "$DEPLOY_MODE" != "ops" ] && [ "$SKIP_RUNTIME_BOOTSTRAP" != "1" ]; then
    need_cmd uv
    need_cmd npm
elif [ "$RUN_FRONTEND_BUILD" = "1" ]; then
    need_cmd npm
fi
[ -d "$APP_ROOT" ] || fail "APP_ROOT $APP_ROOT does not exist"

LOCK_FILE="$APP_ROOT/.deploy.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || fail "Another deploy or rollback is already in progress (lock: $LOCK_FILE)"

resolve_git_source
guard_against_current_release_source
stage_clean_git_source_if_needed

APP_SERVICES=($(discover_app_services "$COPY_ROOT/deploy/systemd"))

if [ "$DEPLOY_MODE" != "ops" ] && [ "$SKIP_RUNTIME_BOOTSTRAP" != "1" ]; then
    ensure_runtime_bootstrap
elif [ ! -d "$VENV_DIR" ]; then
    fail "VENV_DIR $VENV_DIR does not exist (run bootstrap_runtime_root.sh first)"
fi

run_preflight_checks

# 2. Release Management
RELEASE_ID=$(date -u +%Y%m%dT%H%M%SZ)
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"

info "Copying release to $RELEASE_DIR..."
mkdir -p "$RELEASE_DIR"
rsync -a \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude 'node_modules/' \
    --exclude 'web/node_modules/' \
    --exclude 'web/dist/' \
    --exclude 'logs/' \
    --exclude '/shared/' \
    --exclude 'releases/' \
    --exclude 'current' \
    "$COPY_ROOT/" "$RELEASE_DIR/"

# Correct static generated and uploads symlinks
info "Correcting static symlinks..."
rm -rf "$RELEASE_DIR/static/generated" "$RELEASE_DIR/static/uploads"
mkdir -p "$SHARED_DIR/static/generated" "$SHARED_DIR/static/uploads"
ln -sfn "$SHARED_DIR/static/generated" "$RELEASE_DIR/static/generated"
ln -sfn "$SHARED_DIR/static/uploads" "$RELEASE_DIR/static/uploads"

# 3. Build Frontend
if [ "$RUN_FRONTEND_BUILD" = "1" ] && [ -L "$CURRENT_LINK" ] && [ -f "$(readlink -f "$CURRENT_LINK")/.runtime-meta" ] && [ -d "$SOURCE_ROOT/.git" ]; then
    current_commit=$(grep '^COMMIT_SHA=' "$(readlink -f "$CURRENT_LINK")/.runtime-meta" | cut -d= -f2) || true
    if [ -n "$current_commit" ]; then
        if git diff --quiet "$current_commit" HEAD -- web/; then
            info "No changes under web/ directory detected since current release commit $current_commit. Skipping frontend build to save time."
            RUN_FRONTEND_BUILD=0
        fi
    fi
fi

if [ "$RUN_FRONTEND_BUILD" = "1" ]; then
    info "Building frontend..."
    install_frontend_dependencies "$RELEASE_DIR/web"
    npm run build --silent
    info "Copying server-only font assets to client directory..."
    mkdir -p "$RELEASE_DIR/web/dist/client/_astro"
    cp -n "$RELEASE_DIR/web/dist/server/_astro"/*.woff2 "$RELEASE_DIR/web/dist/client/_astro/" 2>/dev/null || true
    cp -n "$RELEASE_DIR/web/dist/server/_astro"/*.woff "$RELEASE_DIR/web/dist/client/_astro/" 2>/dev/null || true
else
    info "Skipping frontend build for DEPLOY_MODE=$DEPLOY_MODE"
    if [ -L "$CURRENT_LINK" ] && [ -d "$(readlink -f "$CURRENT_LINK")/web/dist" ]; then
        info "Reusing frontend build from current release"
        cp -a "$(readlink -f "$CURRENT_LINK")/web/dist" "$RELEASE_DIR/web/dist"
    else
        fail "Cannot skip frontend build: current release web/dist is missing"
    fi
    if [ -L "$SHARED_WEB_NODE_MODULES" ] || [ -d "$SHARED_WEB_NODE_MODULES" ]; then
        ln -sfn "$SHARED_WEB_NODE_MODULES" "$RELEASE_DIR/web/node_modules"
    fi
fi

# 4. Backup database & Update Backend migrations
DB_BACKUP_CREATED=0
if [ "$RUN_DB_BACKUP" = "1" ] && [ -f "$COPY_ROOT/deploy/backup_postgres.sh" ]; then
    # Determine if there are actually any pending database migrations to run
    has_pending_migrations=1
    if [ -f "$VENV_DIR/bin/alembic" ]; then
        current_rev=$("$VENV_DIR/bin/alembic" current 2>/dev/null | grep -v "INFO" | awk '{print $1}') || true
        head_rev=$("$VENV_DIR/bin/alembic" heads 2>/dev/null | awk '{print $1}') || true
        if [ -n "$current_rev" ] && [ -n "$head_rev" ] && [ "$current_rev" = "$head_rev" ]; then
            has_pending_migrations=0
        fi
    fi

    if [ "$has_pending_migrations" = "0" ] && [ "${FORCE_DB_BACKUP:-0}" != "1" ]; then
        info "No pending database migrations detected. Skipping automatic database backup to save time. (Use FORCE_DB_BACKUP=1 to force backup)"
    else
        info "Backing up database..."
        if APP_ROOT="$APP_ROOT" ENV_FILE="$SHARED_DIR/.env" bash "$COPY_ROOT/deploy/backup_postgres.sh"; then
            DB_BACKUP_CREATED=1
            ok "Automatic database backup created successfully"
        elif [ "$REQUIRE_DB_BACKUP" = "1" ]; then
            fail "Database backup failed and REQUIRE_DB_BACKUP=1"
        else
            warn "Database backup failed (continuing because REQUIRE_DB_BACKUP=0)"
        fi
    fi
else
    info "Skipping database backup for DEPLOY_MODE=$DEPLOY_MODE"
fi

cd "$RELEASE_DIR"
if [ -f "$SHARED_DIR/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$SHARED_DIR/.env"
    set +a
fi

SCHEMA_UPDATED=0
if [ "$RUN_MIGRATIONS" = "1" ]; then
    info "Running migrations..."
    if "$VENV_DIR/bin/alembic" upgrade head; then
        SCHEMA_UPDATED=1
        ok "Database migrations applied successfully"
    else
        fail "Alembic migrations failed — aborting deploy before switching release"
    fi
else
    info "Skipping migrations for DEPLOY_MODE=$DEPLOY_MODE"
fi

# Write runtime metadata for rollback support
info "Writing release runtime metadata..."
commit_sha=""
if [ -d "$SOURCE_ROOT/.git" ]; then
    commit_sha=$(git -C "$SOURCE_ROOT" rev-parse HEAD)
fi
cat > "$RELEASE_DIR/.runtime-meta" <<EOF
VENV_TARGET=$(readlink -f "$VENV_DIR")
WEB_NODE_MODULES_TARGET=$(readlink -f "$SHARED_WEB_NODE_MODULES")
SCHEMA_UPDATED=$SCHEMA_UPDATED
DB_BACKUP_CREATED=$DB_BACKUP_CREATED
DEPLOY_MODE=$DEPLOY_MODE
COMMIT_SHA=$commit_sha
EOF

# 5. Switch Release
switch_current_release

# 6. Restart Services
info "Restarting services..."
if ! restart_services_in_order; then
    attempt_auto_rollback "service restart failure" || true
    fail "Deployment $RELEASE_ID failed during service restart"
fi

# 7. Post-deploy verification
if ! run_post_deploy_smoke_checks; then
    fail "Deployment $RELEASE_ID failed verification"
fi

prune_old_releases

ok "Deployment $RELEASE_ID successful!"
