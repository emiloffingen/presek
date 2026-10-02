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
REQUIRE_BACKUP_ENCRYPTION="${REQUIRE_BACKUP_ENCRYPTION:-0}"
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
  need_cmd gpg

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

  # pg_dump refuses to dump a *newer* server than itself. Catch it up front so
  # we fail loudly instead of writing a truncated "<100 bytes" file that looks
  # like a backup. Run backups from a host whose client matches the server.
  local server_ver server_major client_ver
  server_ver="$(psql "$DATABASE_URL" -tAc 'show server_version_num' 2>/dev/null || true)"
  server_major=$(( ${server_ver:-0} / 10000 ))
  client_ver="$(pg_dump --version 2>/dev/null | grep -oE '[0-9]+' | head -1)"
  if [ -n "$server_ver" ] && [ -n "$client_ver" ] && [ "$client_ver" -lt "$server_major" ] 2>/dev/null; then
    fail "pg_dump client (v$client_ver) is older than the server (v$server_major); run this from a matching client"
  fi

  if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
    if [ "$REQUIRE_BACKUP_ENCRYPTION" = "1" ]; then
      fail "BACKUP_PASSPHRASE is not set and REQUIRE_BACKUP_ENCRYPTION=1"
    fi
    warn "BACKUP_PASSPHRASE is not set; backup will be gzipped but NOT encrypted"
  fi

  install -d "$BACKUP_DIR"

  if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
    local outfile="$BACKUP_DIR/presek-${TIMESTAMP}.sql.gz.gpg"
    info "Creating encrypted PostgreSQL backup at $outfile"
    pg_dump "$DATABASE_URL" | gzip -9 | gpg --batch --yes --symmetric --pinentry-mode loopback --passphrase "$BACKUP_PASSPHRASE" --cipher-algo AES256 -o "$outfile"
  else
    local outfile="$BACKUP_DIR/presek-${TIMESTAMP}.sql.gz"
    info "Creating PostgreSQL backup at $outfile"
    pg_dump "$DATABASE_URL" | gzip -9 > "$outfile"
  fi

  ok "Backup complete"

  info "Pruning backups older than $KEEP_DAYS days"
  find "$BACKUP_DIR" -type f \( -name 'presek-*.sql.gz' -o -name 'presek-*.sql.gz.gpg' \) -mtime +"$KEEP_DAYS" -delete
  ok "Backup pruning complete"
}

main "$@"
