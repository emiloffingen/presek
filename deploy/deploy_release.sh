#!/bin/bash
# Production Deployment Script for Presek (Lean Core)
# Usage: bash deploy/deploy_release.sh
# Fast modes:
#   DEPLOY_MODE=frontend bash deploy/deploy_release.sh  # build web, restart Astro only
#   DEPLOY_MODE=backend bash deploy/deploy_release.sh   # skip web build, restart API/workers
#   DEPLOY_MODE=workers bash deploy/deploy_release.sh   # restart workers only
#   DEPLOY_MODE=ops bash deploy/deploy_release.sh       # copy release, no build/DB/restart
#   DEPLOY_MODE=fast bash deploy/deploy_release.sh      # skip DB backup/migrations

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

# Logging helpers
info() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"; }
error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2; }
ok() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [OK]   $*"; }
fail() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2; exit 1; }

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

# Discover services dynamically from source directory
discover_app_services() {
    local SYSTEMD_DIR="$SOURCE_ROOT/deploy/systemd"

    # Discover only service units from the source directory.
    local services=()
    while IFS= read -r -d '' file; do
        services+=("$(basename "$file")")
    done < <(find "$SYSTEMD_DIR" -maxdepth 1 -type f -name "*.service" -print0 2>/dev/null || true)

    if [ "${#services[@]}" -eq 0 ]; then
        fail "No application services found in $SYSTEMD_DIR"
    fi

    echo "${services[@]}"
}

APP_SERVICES=($(discover_app_services))

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

    # Explicit environment overrides. SKIP_*=1 disables; FORCE_*=1 enables.
    if [ "${SKIP_FRONTEND_BUILD:-0}" = "1" ]; then RUN_FRONTEND_BUILD=0; fi
    if [ "${FORCE_FRONTEND_BUILD:-0}" = "1" ]; then RUN_FRONTEND_BUILD=1; fi
    if [ "${SKIP_DB_BACKUP:-0}" = "1" ]; then RUN_DB_BACKUP=0; fi
    if [ "${FORCE_DB_BACKUP:-0}" = "1" ]; then RUN_DB_BACKUP=1; fi
    if [ "${SKIP_MIGRATIONS:-0}" = "1" ]; then RUN_MIGRATIONS=0; fi
    if [ "${FORCE_MIGRATIONS:-0}" = "1" ]; then RUN_MIGRATIONS=1; fi
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

has_service() {
    local wanted="$1"
    local service
    for service in "${APP_SERVICES[@]}"; do
        [ "$service" = "$wanted" ] && return 0
    done
    return 1
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

    fail "$name did not become ready (last HTTP code: ${code:-none})"
}

restart_services_in_order() {
    if [ "$SKIP_RESTART" = "1" ]; then
        info "SKIP_RESTART is set, skipping systemctl restart"
        return
    fi

    local remaining_services=()
    local service

    if [ "$RESTART_FASTAPI" = "1" ] && has_service "presek-fastapi-unified.service"; then
        info "Restarting unified FastAPI service"
        sudo systemctl restart presek-fastapi-unified.service
        wait_http_status "FastAPI Unified" "http://127.0.0.1:5001/api/health"
    fi

    if [ "$RESTART_ASTRO" = "1" ] && has_service "presek-astro.service"; then
        info "Restarting Astro"
        sudo systemctl restart presek-astro.service
        wait_http_status "Astro" "http://127.0.0.1:3000"
    fi

    if [ "$RESTART_WORKERS" = "1" ]; then
        for service in "${APP_SERVICES[@]}"; do
            case "$service" in
                presek-fastapi-unified.service|presek-astro.service|cloudflare-realip-update.service)
                    ;;
                *)
                    remaining_services+=("$service")
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
if [ "$RUN_FRONTEND_BUILD" = "1" ]; then
    need_cmd npm
fi
[ -d "$APP_ROOT" ] || fail "APP_ROOT $APP_ROOT does not exist"
[ -d "$VENV_DIR" ] || fail "VENV_DIR $VENV_DIR does not exist"

LOCK_FILE="$APP_ROOT/.deploy.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || fail "Another deploy or rollback is already in progress (lock: $LOCK_FILE)"

stage_clean_git_source_if_needed

# Update git stats file dynamically inside the deployment COPY_ROOT
if [ -f "$SOURCE_ROOT/scripts/update_git_stats.py" ]; then
    info "Generating git stats..."
    python3 "$SOURCE_ROOT/scripts/update_git_stats.py"
    if [ "$COPY_ROOT" != "$SOURCE_ROOT" ]; then
        cp "$SOURCE_ROOT/web/src/git_stats.json" "$COPY_ROOT/web/src/git_stats.json"
    fi
fi

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
    --exclude 'shared/' \
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
if [ "$RUN_FRONTEND_BUILD" = "1" ]; then
    info "Building frontend..."
    cd "$RELEASE_DIR/web"
    if [ -d "$SHARED_WEB_NODE_MODULES" ]; then
        ln -sfn "$SHARED_WEB_NODE_MODULES" "node_modules"
    else
        npm install --silent
    fi
    npm run build --silent
else
    info "Skipping frontend build for DEPLOY_MODE=$DEPLOY_MODE"
    if [ -L "$CURRENT_LINK" ] && [ -d "$(readlink -f "$CURRENT_LINK")/web/dist" ]; then
        info "Reusing frontend build from current release"
        cp -a "$(readlink -f "$CURRENT_LINK")/web/dist" "$RELEASE_DIR/web/dist"
    else
        fail "Cannot skip frontend build: current release web/dist is missing"
    fi
    if [ -d "$SHARED_WEB_NODE_MODULES" ]; then
        ln -sfn "$SHARED_WEB_NODE_MODULES" "$RELEASE_DIR/web/node_modules"
    fi
fi

# 4. Backup database & Update Backend migrations
DB_BACKUP_CREATED=0
if [ "$RUN_DB_BACKUP" = "1" ] && [ -f "$SOURCE_ROOT/deploy/backup_postgres.sh" ]; then
    info "Backing up database..."
    if APP_ROOT="$APP_ROOT" ENV_FILE="$SHARED_DIR/.env" bash "$SOURCE_ROOT/deploy/backup_postgres.sh" >/dev/null 2>&1; then
        DB_BACKUP_CREATED=1
        ok "Automatic database backup created successfully"
    else
        info "Database backup skipped or failed (unconfigured environment or missing utility)"
    fi
else
    info "Skipping database backup for DEPLOY_MODE=$DEPLOY_MODE"
fi

cd "$RELEASE_DIR"
if [ -f "$SHARED_DIR/.env" ]; then
    set -a
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
        info "Alembic migrations failed or not configured, skipping..."
    fi
else
    info "Skipping migrations for DEPLOY_MODE=$DEPLOY_MODE"
fi

# Write runtime metadata for rollback support
info "Writing release runtime metadata..."
cat > "$RELEASE_DIR/.runtime-meta" <<EOF
VENV_TARGET=$(readlink -f "$VENV_DIR")
WEB_NODE_MODULES_TARGET=$(readlink -f "$SHARED_WEB_NODE_MODULES")
SCHEMA_UPDATED=$SCHEMA_UPDATED
DB_BACKUP_CREATED=$DB_BACKUP_CREATED
DEPLOY_MODE=$DEPLOY_MODE
EOF

# 5. Switch Release
switch_current_release

# 6. Restart Services
info "Restarting services..."
restart_services_in_order

ok "Deployment $RELEASE_ID successful!"
