#!/usr/bin/env bash
# Reset logical replication after a manual pg_dump reseed or a crashed apply worker.
#
# Usage:
#   sudo APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/repair_read_replica.sh
#
# Safe when primary and replica row counts already match. Drops the stale slot,
# recreates it at the current WAL position, and reattaches the subscription.
set -euo pipefail

APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/shared/.env}"
PUBLICATION_NAME="${PUBLICATION_NAME:-presek_read_replica}"
SUBSCRIPTION_NAME="${SUBSCRIPTION_NAME:-presek_read_replica_sub}"
REPLICA_DB="${REPLICA_DB:-presek_replica}"

info() { echo "> $*"; }
ok() { echo "✓ $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

load_database_url() {
  [ -f "$ENV_FILE" ] || fail "Missing env file: $ENV_FILE"
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
  [ -n "${DATABASE_URL:-}" ] || fail "DATABASE_URL not set in $ENV_FILE"
}

parse_database_url() {
  python3 - <<'PY' "$DATABASE_URL"
import sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1])
print(u.username or "")
print(u.password or "")
print(u.hostname or "localhost")
print(u.port or 5432)
print((u.path or "/presek").lstrip("/"))
PY
}

verify_counts_match() {
  local primary_db="$1"
  local primary_count replica_count
  primary_count="$(sudo -u postgres psql -d "$primary_db" -tAc "SELECT COUNT(*) FROM articles;" 2>/dev/null || echo 0)"
  replica_count="$(sudo -u postgres psql -d "$REPLICA_DB" -tAc "SELECT COUNT(*) FROM articles;" 2>/dev/null || echo 0)"
  if [ "${primary_count:-0}" != "${replica_count:-0}" ] || [ "${primary_count:-0}" = "0" ]; then
    fail "Article counts differ (primary=${primary_count}, replica=${replica_count}). Run install_read_replica.sh reseed first."
  fi
  ok "Article counts match (${primary_count})"
}

reset_subscription() {
  local primary_db="$1"
  local conninfo="$2"

  if sudo -u postgres psql -d "$REPLICA_DB" -tAc \
      "SELECT 1 FROM pg_subscription WHERE subname='${SUBSCRIPTION_NAME}'" | grep -q 1; then
    info "Dropping subscription ${SUBSCRIPTION_NAME}"
    sudo -u postgres psql -d "$REPLICA_DB" -v ON_ERROR_STOP=1 -c \
      "ALTER SUBSCRIPTION ${SUBSCRIPTION_NAME} DISABLE;"
    sudo -u postgres psql -d "$REPLICA_DB" -v ON_ERROR_STOP=1 -c \
      "ALTER SUBSCRIPTION ${SUBSCRIPTION_NAME} SET (slot_name = NONE);"
    sudo -u postgres psql -d "$REPLICA_DB" -v ON_ERROR_STOP=1 -c \
      "DROP SUBSCRIPTION ${SUBSCRIPTION_NAME};"
  fi

  if sudo -u postgres psql -d "$primary_db" -tAc \
      "SELECT 1 FROM pg_replication_slots WHERE slot_name='${SUBSCRIPTION_NAME}'" | grep -q 1; then
    info "Dropping stale replication slot ${SUBSCRIPTION_NAME}"
    sudo -u postgres psql -d "$primary_db" -v ON_ERROR_STOP=1 -c \
      "SELECT pg_drop_replication_slot('${SUBSCRIPTION_NAME}');"
  fi

  info "Creating fresh replication slot at current WAL position"
  sudo -u postgres psql -d "$primary_db" -v ON_ERROR_STOP=1 -c \
    "SELECT pg_create_logical_replication_slot('${SUBSCRIPTION_NAME}', 'pgoutput');"

  info "Recreating subscription ${SUBSCRIPTION_NAME}"
  sudo -u postgres psql -d "$REPLICA_DB" -v ON_ERROR_STOP=1 -c \
    "CREATE SUBSCRIPTION ${SUBSCRIPTION_NAME} CONNECTION '${conninfo}' PUBLICATION ${PUBLICATION_NAME} WITH (copy_data = false, create_slot = false, slot_name = '${SUBSCRIPTION_NAME}', enabled = true);"
}

wait_for_worker() {
  info "Waiting for apply worker..."
  for _ in $(seq 1 12); do
    if sudo -u postgres psql -d "$REPLICA_DB" -tAc \
        "SELECT pid FROM pg_stat_subscription WHERE subname='${SUBSCRIPTION_NAME}' AND pid IS NOT NULL" | grep -q '[0-9]'; then
      ok "Apply worker running"
      return 0
    fi
    sleep 2
  done
  fail "Apply worker did not start — check /var/log/postgresql/postgresql-*-main.log"
}

main() {
  load_database_url
  mapfile -t parts < <(parse_database_url)
  db_user="${parts[0]}"
  db_pass="${parts[1]}"
  db_host="${parts[2]}"
  db_port="${parts[3]}"
  primary_db="${parts[4]}"
  conninfo="host=${db_host} port=${db_port} dbname=${primary_db} user=${db_user} password=${db_pass}"

  verify_counts_match "$primary_db"
  reset_subscription "$primary_db" "$conninfo"
  wait_for_worker

  cat <<EOF

Read replica replication reset.
  Primary: ${primary_db}
  Replica: ${REPLICA_DB}
  Slot:    ${SUBSCRIPTION_NAME} (fresh)

Restart API if needed:
  sudo systemctl restart presek-fastapi-unified
EOF
}

main "$@"
