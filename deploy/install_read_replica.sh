#!/usr/bin/env bash
# Set up PostgreSQL logical read replica (presek_replica) on the same host.
#
# Usage:
#   sudo APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/install_read_replica.sh
#
# Requires:
#   - PostgreSQL with wal_level=replica (already set on production)
#   - DATABASE_URL in $APP_ROOT/shared/.env
#
# After success, restart API so the async read pool connects:
#   sudo systemctl restart presek-fastapi-unified
set -euo pipefail

APP_ROOT="${APP_ROOT:-$HOME/presek-runtime}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/shared/.env}"
PUBLICATION_NAME="${PUBLICATION_NAME:-presek_read_replica}"
SUBSCRIPTION_NAME="${SUBSCRIPTION_NAME:-presek_read_replica_sub}"
REPLICA_DB="${REPLICA_DB:-presek_replica}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

info() { echo "> $*"; }
ok() { echo "✓ $*"; }

load_database_url() {
  [ -f "$ENV_FILE" ] || fail "Missing env file: $ENV_FILE"
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
  [ -n "${DATABASE_URL:-}" ] || fail "DATABASE_URL not set in $ENV_FILE"
}

ensure_wal_level_logical() {
  local current
  current="$(sudo -u postgres psql -tAc "SHOW wal_level;" | tr -d '[:space:]')"
  if [ "$current" = "logical" ]; then
    ok "wal_level=logical"
    return 0
  fi

  info "Setting wal_level=logical (requires PostgreSQL restart)"
  local conf="/etc/postgresql/17/main/postgresql.conf"
  [ -f "$conf" ] || fail "Could not find postgresql.conf at $conf"
  sudo sed -i "s/^#*wal_level = .*/wal_level = logical/" "$conf"
  sudo systemctl restart postgresql
  sleep 2
  current="$(sudo -u postgres psql -tAc "SHOW wal_level;" | tr -d '[:space:]')"
  [ "$current" = "logical" ] || fail "Failed to set wal_level=logical (currently: ${current})"
  ok "wal_level=logical applied"
}

parse_database_url() {
  python3 - <<'PY' "$DATABASE_URL"
import sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1])
if u.scheme not in {"postgresql", "postgres"}:
    raise SystemExit("DATABASE_URL must be a postgresql URL")
print(u.username or "")
print(u.password or "")
print(u.hostname or "localhost")
print(u.port or 5432)
print((u.path or "/presek").lstrip("/"))
PY
}

ensure_replica_database() {
  local primary_db="$1"
  if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${REPLICA_DB}'" | grep -q 1; then
    ok "Database ${REPLICA_DB} already exists"
  else
    info "Creating database ${REPLICA_DB}"
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${REPLICA_DB} OWNER presek;"
    ok "Created database ${REPLICA_DB}"
  fi

  local table_count
  table_count="$(sudo -u postgres psql -d "$REPLICA_DB" -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
  if [ "${table_count:-0}" = "0" ]; then
    info "Copying schema from ${primary_db} to ${REPLICA_DB}"
    sudo -u postgres pg_dump --schema-only --no-owner --no-privileges "$primary_db" \
      | sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$REPLICA_DB"
    sudo -u postgres psql -d "$REPLICA_DB" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;"
    ok "Replica schema initialized"
  else
    ok "Replica schema already present (${table_count} tables)"
  fi
}

ensure_publication() {
  local primary_db="$1"
  if sudo -u postgres psql -d "$primary_db" -tAc \
      "SELECT 1 FROM pg_publication WHERE pubname='${PUBLICATION_NAME}'" | grep -q 1; then
    ok "Publication ${PUBLICATION_NAME} already exists on ${primary_db}"
  else
    info "Creating publication ${PUBLICATION_NAME} on ${primary_db}"
    sudo -u postgres psql -d "$primary_db" -v ON_ERROR_STOP=1 -c \
      "CREATE PUBLICATION ${PUBLICATION_NAME} FOR ALL TABLES;"
    ok "Publication ${PUBLICATION_NAME} created"
  fi
}

ensure_subscription() {
  local primary_db="$1"
  local db_user="$2"
  local db_pass="$3"
  local db_host="$4"
  local db_port="$5"
  local conninfo
  conninfo="host=${db_host} port=${db_port} dbname=${primary_db} user=${db_user} password=${db_pass}"

  if sudo -u postgres psql -d "$REPLICA_DB" -tAc \
      "SELECT 1 FROM pg_subscription WHERE subname='${SUBSCRIPTION_NAME}'" | grep -q 1; then
    ok "Subscription ${SUBSCRIPTION_NAME} already exists"
    sudo -u postgres psql -d "$REPLICA_DB" -v ON_ERROR_STOP=1 -c \
      "ALTER SUBSCRIPTION ${SUBSCRIPTION_NAME} ENABLE;"
    return 0
  fi

  local primary_articles replica_articles
  primary_articles="$(sudo -u postgres psql -d "$primary_db" -tAc "SELECT COUNT(*) FROM articles;" 2>/dev/null || echo 0)"
  replica_articles="$(sudo -u postgres psql -d "$REPLICA_DB" -tAc "SELECT COUNT(*) FROM articles;" 2>/dev/null || echo 0)"

  if [ "${replica_articles:-0}" = "0" ] && [ "${primary_articles:-0}" != "0" ]; then
    info "Seeding ${REPLICA_DB} data from ${primary_db} (faster than copy_data initial sync)"
    sudo -u postgres pg_dump --data-only --disable-triggers --no-owner --no-privileges "$primary_db" \
      | sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$REPLICA_DB"
    ok "Replica data seeded from primary"
  fi

  info "Creating subscription ${SUBSCRIPTION_NAME} on ${REPLICA_DB}"
  if ! sudo -u postgres psql -d "$primary_db" -tAc \
      "SELECT 1 FROM pg_replication_slots WHERE slot_name='${SUBSCRIPTION_NAME}'" | grep -q 1; then
    info "Creating logical replication slot ${SUBSCRIPTION_NAME} on ${primary_db}"
    sudo -u postgres psql -d "$primary_db" -v ON_ERROR_STOP=1 -c \
      "SELECT pg_create_logical_replication_slot('${SUBSCRIPTION_NAME}', 'pgoutput');"
  fi
  sudo -u postgres psql -d "$REPLICA_DB" -v ON_ERROR_STOP=1 -c \
    "CREATE SUBSCRIPTION ${SUBSCRIPTION_NAME} CONNECTION '${conninfo}' PUBLICATION ${PUBLICATION_NAME} WITH (copy_data = false, create_slot = false, slot_name = '${SUBSCRIPTION_NAME}', enabled = true);"
  ok "Subscription ${SUBSCRIPTION_NAME} created"
}

wait_for_replica_sync() {
  local primary_db="$1"
  info "Waiting for initial replica sync (may take a few minutes)..."
  for _ in $(seq 1 60); do
    local primary_count replica_count
    primary_count="$(sudo -u postgres psql -d "$primary_db" -tAc "SELECT COUNT(*) FROM articles;" 2>/dev/null || echo 0)"
    replica_count="$(sudo -u postgres psql -d "$REPLICA_DB" -tAc "SELECT COUNT(*) FROM articles;" 2>/dev/null || echo 0)"
    if [ "$primary_count" = "$replica_count" ] && [ "${primary_count:-0}" != "0" ]; then
      ok "Replica article count matches primary (${replica_count})"
      return 0
    fi
    sleep 5
  done
  warn "Replica still catching up — check pg_subscription_rel.srsubstate on ${REPLICA_DB}"
}

warn() { echo "! $*" >&2; }

update_env_file() {
  python3 - <<'PY' "$ENV_FILE" "$REPLICA_DB"
import re
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
replica_db = sys.argv[2]
text = env_path.read_text(encoding="utf-8")
match = re.search(r"^DATABASE_URL=(.+)$", text, re.M)
if not match:
    raise SystemExit("DATABASE_URL missing from env file")
primary = match.group(1).strip()
if primary.rstrip("/").endswith("/presek"):
    replica = re.sub(r"/presek$", f"/{replica_db}", primary.rstrip("/"))
else:
    replica = f"{primary.rstrip('/')}/{replica_db}"
line = f"DATABASE_READ_REPLICA_URL={replica}"
if re.search(r"^DATABASE_READ_REPLICA_URL=", text, re.M):
    text = re.sub(r"^DATABASE_READ_REPLICA_URL=.*$", line, text, flags=re.M)
else:
    text = text.rstrip() + "\n\n# PostgreSQL read replica (logical replication)\n" + line + "\n"
env_path.write_text(text, encoding="utf-8")
PY
  ok "Updated DATABASE_READ_REPLICA_URL in ${ENV_FILE}"
}

main() {
  need_cmd python3
  need_cmd sudo
  load_database_url

  mapfile -t parts < <(parse_database_url)
  db_user="${parts[0]}"
  db_pass="${parts[1]}"
  db_host="${parts[2]}"
  db_port="${parts[3]}"
  primary_db="${parts[4]}"

  [ -n "$db_user" ] && [ -n "$db_pass" ] || fail "DATABASE_URL must include username and password"

  info "Primary database: ${primary_db} on ${db_host}:${db_port}"
  ensure_wal_level_logical
  ensure_replica_database "$primary_db"
  ensure_publication "$primary_db"
  ensure_subscription "$primary_db" "$db_user" "$db_pass" "$db_host" "$db_port"
  wait_for_replica_sync "$primary_db"
  update_env_file

  cat <<EOF

Read replica ready.
  Primary:  ${primary_db}
  Replica:  ${REPLICA_DB}
  Env:      DATABASE_READ_REPLICA_URL set in ${ENV_FILE}

Restart API to open the read pool:
  sudo systemctl restart presek-fastapi-unified

Verify routing:
  curl -s http://127.0.0.1:5001/api/home >/dev/null
  curl -s http://127.0.0.1:5001/metrics | grep presek_db_queries_total
EOF
}

main "$@"
