#!/usr/bin/env bash
set -euo pipefail

# Verify the latest local backup archive is readable (gzip/gpg integrity only).
# Does not restore into PostgreSQL. Use before quarterly drills or after sync issues.

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_APP_ROOT="$APP_DIR"
if [ -d "$HOME/presek-runtime/shared" ]; then
  DEFAULT_APP_ROOT="$HOME/presek-runtime"
fi

APP_ROOT="${APP_ROOT:-$DEFAULT_APP_ROOT}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/shared/.env}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/shared/backups}"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
RESET='\033[0m'

ok() { echo -e "${GREEN}✓${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }
info() { echo -e "${BLUE}>${RESET}  $*"; }

main() {
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
  fi

  [ -d "$BACKUP_DIR" ] || fail "Backup directory not found: $BACKUP_DIR"

  local latest
  latest="$(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'presek-*.sql.gz' -o -name 'presek-*.sql.gz.gpg' \) -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
  [ -n "$latest" ] || fail "No backup files found in $BACKUP_DIR"

  info "Verifying latest backup: $latest"

  if [[ "$latest" == *.gpg ]]; then
    [ -n "${BACKUP_PASSPHRASE:-}" ] || fail "BACKUP_PASSPHRASE is required to verify encrypted backups"
    gpg --batch --yes --passphrase "$BACKUP_PASSPHRASE" --decrypt "$latest" | gzip -t
  else
    gzip -t "$latest"
  fi

  ok "Backup archive integrity check passed"
}

main "$@"
