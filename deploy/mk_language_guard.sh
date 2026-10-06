#!/bin/bash
# mk_language_guard.sh - alert when freshly generated MK summaries leak letters
# that are not in the Macedonian alphabet (Bulgarian/Russian/Serbian drift), so
# prompt/cleanup regressions are caught without anyone reading every summary.
set -uo pipefail

APP_DIR="${PRESEK_APP_DIR:-/root/presek}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
LOG="${MK_LANG_GUARD_LOG:-$APP_DIR/logs/mk_language_guard.log}"
LOCK="$APP_DIR/logs/.mk_language_guard.lock"
STATE="$APP_DIR/logs/.mk_language_guard_state"
INTERVAL="${MK_LANG_GUARD_INTERVAL:-21600}"   # 6 hours
WINDOW="${MK_LANG_GUARD_WINDOW_HOURS:-24}"
PY="$APP_DIR/.venv/bin/python"

mkdir -p "$(dirname "$LOG")"
exec 9>"$LOCK"
flock -n 9 || exit 0

NTFY=""
NTFY_TOKEN=""
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
notify() {
  [ -n "${NTFY_TOPIC_URL:-}" ] || return 0
  local auth=()
  [ -n "${NTFY_TOKEN:-}" ] && auth=(-H "Authorization: Bearer $NTFY_TOKEN")
  curl -s -m 12 -H "Title: $1" -H "Tags: $2" "${auth[@]}" -d "$3" "$NTFY_TOPIC_URL" >/dev/null 2>&1
}

# Prints "<count> <comma-separated ids>"
count_foreign() {
  "$PY" - "$WINDOW" <<'PYEOF'
import os, sys, psycopg
hours = int(sys.argv[1])
with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=15) as c:
    rows = c.execute(
        r"""
        SELECT cluster_id FROM cluster_summaries
        WHERE created_at > now() - make_interval(hours => %s)
          AND (coalesce(summary,'') || ' ' || coalesce(synthetic_headline,'') || ' ' || coalesce(synthetic_standfirst,''))
              ~ '[йяюыэёђћіїєґъ]'
        LIMIT 20
        """,
        (hours,),
    ).fetchall()
print(len(rows), ",".join(r[0] for r in rows[:5]))
PYEOF
}

log "mk language guard started (interval ${INTERVAL}s, window ${WINDOW}h)"
while true; do
  out="$(count_foreign 2>/dev/null || true)"
  n="${out%% *}"
  ids="${out#* }"
  if [ -n "$n" ] && [ "$n" != "0" ]; then
    log "found $n summaries with non-MK letters in last ${WINDOW}h: $ids"
    today="$(date +%F)"
    if [ "$(cat "$STATE" 2>/dev/null || true)" != "$today" ]; then
      notify "MK summaries: $n with foreign letters" "warning" \
        "In the last ${WINDOW}h, $n generated summaries contain non-MK letters. Clusters: $ids"
      echo "$today" > "$STATE"
    fi
  else
    log "clean (0 with non-MK letters in last ${WINDOW}h)"
  fi
  sleep "$INTERVAL"
done
