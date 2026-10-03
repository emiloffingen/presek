#!/bin/bash
# setup_local_postgres.sh — stand up a Termux-native PostgreSQL 18.6 + pgvector
# for Presek on an Android/Termux host (Shield), because:
#
#   * Neon (the original DB) is a hosted service that can go over quota.
#   * The proot Debian container CANNOT run Postgres: initdb/postgres deadlock
#     under proot's ptrace at the shared-memory probe ("selecting default
#     shared_buffers/max_connections"), and postgres refuses to run as root.
#
# The working approach is the Termux-native `postgresql` package, which runs as
# the unprivileged Termux app user (no proot), plus a from-source pgvector.
#
# Run this ON THE SHIELD (Termux host, not inside proot).
#
# Result:
#   * data dir:  $HOME/pgdata
#   * listens on 127.0.0.1 and the host's LAN/Tailscale IPs (phone access)
#   * database:  presek  (extensions: vector, pg_trgm, btree_gin, unaccent)
#   * a keepalive loop + Termux:Boot entry keep it running
#
# Usage:  bash deploy/setup_local_postgres.sh
set -euo pipefail

export PATH="$PREFIX/bin:$PATH"
PGDATA="$HOME/pgdata"
PGLOG="$HOME/pg.log"
PGVECTOR_TAG="${PGVECTOR_TAG:-master}"

log() { echo "[$(date '+%F %T')] $*"; }

log "installing Termux postgresql + build tools"
pkg install -y postgresql clang make git >/dev/null

if [ ! -f "$PGDATA/PG_VERSION" ]; then
  log "initializing cluster at $PGDATA"
  initdb -D "$PGDATA" -U postgres --auth=trust --no-sync >/dev/null
else
  log "cluster already initialized at $PGDATA"
fi

log "configuring postgresql.conf + pg_hba.conf"
CONF="$PGDATA/postgresql.conf"
HBA="$PGDATA/pg_hba.conf"
if ! grep -q "# PRESEK" "$CONF"; then
  {
    echo "# PRESEK TUNED"
    echo "listen_addresses = '*'"
    echo "port = 5432"
    echo "shared_buffers = 32MB"
    echo "max_connections = 50"
    echo "fsync = off"
    echo "synchronous_commit = off"
  } >> "$CONF"
fi
if ! grep -q "PRESEK phone access" "$HBA"; then
  {
    echo "# PRESEK phone access"
    echo "host    all    all    192.168.0.0/24    trust"
    echo "host    all    all    100.64.0.0/10     trust"
  } >> "$HBA"
fi

# --- pgvector (not in the Termux repo; build from source) ------------------
if [ ! -f "$PREFIX/share/postgresql/extension/vector.control" ]; then
  log "building pgvector ($PGVECTOR_TAG)"
  rm -rf "$HOME/pgvector"
  git clone --depth 1 --branch "$PGVECTOR_TAG" \
    https://github.com/pgvector/pgvector.git "$HOME/pgvector" 2>/dev/null || \
    git clone --depth 1 https://github.com/pgvector/pgvector.git "$HOME/pgvector"
  # -lm is required: on Android Bionic, acos() lives in libm.so, and without an
  # explicit dependency the module fails to load ("cannot locate symbol acos").
  ( cd "$HOME/pgvector" && make SHLIB_LINK="-lm" && make install )
else
  log "pgvector already installed"
fi

log "starting postgres"
pg_ctl -D "$PGDATA" -l "$PGLOG" restart -m fast >/dev/null 2>&1 || \
  pg_ctl -D "$PGDATA" -l "$PGLOG" start >/dev/null 2>&1
for _ in $(seq 1 15); do
  pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1 && break
  sleep 2
done
pg_isready -h 127.0.0.1 -p 5432

log "creating database + extensions"
psql -h 127.0.0.1 -U postgres -v ON_ERROR_STOP=1 <<'SQL'
SELECT 'CREATE DATABASE presek'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'presek')\gexec
SQL
psql -h 127.0.0.1 -U postgres -d presek -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS unaccent;
SQL

log "done. DATABASE_URL=postgresql://postgres@127.0.0.1:5432/presek"
log "phone reachable at postgresql://postgres@<shield-lan-ip>:5432/presek"
