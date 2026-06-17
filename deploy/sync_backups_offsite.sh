#!/usr/bin/env bash
set -euo pipefail

# Sync local PostgreSQL backups to offsite storage via rclone.
#
# Configure in $APP_ROOT/shared/.env:
#   BACKUP_OFFSITE_RCLONE_TARGET=r2:presek-backups/presek
#
# Install rclone and configure the remote separately. When the target is unset,
# this script exits successfully without doing work.

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_APP_ROOT="$APP_DIR"
if [ -d "$HOME/presek-runtime/shared" ]; then
  DEFAULT_APP_ROOT="$HOME/presek-runtime"
fi

APP_ROOT="${APP_ROOT:-$DEFAULT_APP_ROOT}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/shared/.env}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/shared/backups}"
LOG_FILE="${LOG_FILE:-$APP_ROOT/shared/logs/backup_sync.log}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
RESET='\033[0m'

ok() { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
info() { echo -e "${BLUE}>${RESET}  $*"; }
fail() { echo -e "${RED}x${RESET}  $*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

main() {
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
  fi

  local target="${BACKUP_OFFSITE_RCLONE_TARGET:-}"
  if [ -z "$target" ]; then
    warn "BACKUP_OFFSITE_RCLONE_TARGET is not set; skipping offsite backup sync"
    exit 0
  fi

  need_cmd rclone
  [ -d "$BACKUP_DIR" ] || fail "Backup directory not found: $BACKUP_DIR"

  install -d "$(dirname "$LOG_FILE")"
  info "Syncing $BACKUP_DIR to $target"
  rclone sync "$BACKUP_DIR/" "$target/" --fast-list --transfers 4 --checkers 8 >>"$LOG_FILE" 2>&1
  ok "Offsite backup sync completed"
}

main "$@"
