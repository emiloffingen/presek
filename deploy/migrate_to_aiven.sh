#!/bin/bash
# Copy the public schema from Supabase (DATABASE_URL) into Aiven (AIVEN_DATABASE_URL),
# replacing whatever is in Aiven's public schema, then compare row counts.
# Reads Supabase only; writes Aiven only. Stop the writers first for the final run
# (see deploy/AIVEN_MIGRATION.md). Pass --yes to skip the prompt.
set -uo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
set -a; . "$ENV_FILE"; set +a
: "${DATABASE_URL:?DATABASE_URL missing}" "${AIVEN_DATABASE_URL:?AIVEN_DATABASE_URL missing}"
SRC="${SOURCE_DATABASE_URL:-$DATABASE_URL}"
OUT="${OUT:-$HOME/aiven-restore-logs}"; mkdir -p "$OUT"

if [ "${1:-}" != "--yes" ]; then
  read -r -p "Replace the public schema in Aiven with a fresh copy from Supabase? [y/N] " a
  [ "$a" = "y" ] || exit 1
fi

psql "$AIVEN_DATABASE_URL" -q -v ON_ERROR_STOP=1 \
  -c "DROP SCHEMA IF EXISTS public CASCADE" -c "CREATE SCHEMA public" \
  -c "CREATE EXTENSION vector WITH SCHEMA public" -c "CREATE EXTENSION pg_trgm WITH SCHEMA public" \
  -c "CREATE EXTENSION unaccent WITH SCHEMA public" -c "CREATE EXTENSION btree_gin WITH SCHEMA public" \
  -c "CREATE EXTENSION pgcrypto WITH SCHEMA public" -c 'CREATE EXTENSION "uuid-ossp" WITH SCHEMA public' || exit 1

start=$(date +%s)
pg_dump --schema=public --no-owner --no-privileges --no-comments "$SRC" 2>"$OUT/dump.err" \
  | grep -v -E '^(CREATE SCHEMA public;|CREATE EXTENSION )' \
  | psql "$AIVEN_DATABASE_URL" -q -v ON_ERROR_STOP=0 >"$OUT/restore.out" 2>"$OUT/restore.err"
echo "restore took $(( $(date +%s) - start ))s; ERRORs: $(grep -c ERROR "$OUT/restore.err")"

Q="select table_name||'='||(xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text from information_schema.tables where table_schema='public' and table_type='BASE TABLE' order by 1"
psql "$SRC" -qAt -c "$Q" >"$OUT/counts_src.txt"
psql "$AIVEN_DATABASE_URL" -qAt -c "$Q" >"$OUT/counts_aiven.txt"
if diff "$OUT/counts_src.txt" "$OUT/counts_aiven.txt" >"$OUT/counts.diff"; then
  echo "OK: all $(wc -l <"$OUT/counts_src.txt") tables have identical row counts"
else
  echo "MISMATCH:"; cat "$OUT/counts.diff"; exit 2
fi
