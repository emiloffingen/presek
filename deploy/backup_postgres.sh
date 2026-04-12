#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_APP_ROOT="$APP_DIR"
if [ -d "$HOME/presek-runtime/shared" ]; then
  DEFAULT_APP_ROOT="$HOME/presek-runtime"
fi
APP_ROOT="${APP_ROOT:-$DEFAULT_APP_ROOT}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/shared/.env}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/shared/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
info() { echo -e "${BLUE}>${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

main() {
  need_cmd pg_dump
  need_cmd gzip

  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
  elif [ -f "$APP_DIR/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$APP_DIR/.env"
    set +a
  fi

  [ -n "${DATABASE_URL:-}" ] || fail "DATABASE_URL is not set"

  install -d "$BACKUP_DIR"

  local outfile="$BACKUP_DIR/presek-${TIMESTAMP}.sql.gz"
  info "Creating PostgreSQL backup at $outfile"
  pg_dump "$DATABASE_URL" | gzip -9 > "$outfile"
  ok "Backup complete"

  info "Pruning backups older than $KEEP_DAYS days"
  find "$BACKUP_DIR" -type f -name 'presek-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
  ok "Backup pruning complete"
}

main "$@"
