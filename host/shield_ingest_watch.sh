#!/data/data/com.termux/files/usr/bin/sh
# presek ingestion watch (runs on the Shield, Termux side, under runit).
#
# Why: the phone is the sole ingestion/synthesis host. When its processes die the
# site keeps serving from the Shield, so an HTTP 200 check stays green while no new
# articles arrive. This polls /api/health (the freshness block is computed from the
# shared DB, so it is valid whichever origin answers) and pushes an ntfy alert when
# ingestion has gone stale. Complements presek-healthcheck (up/down only).
#
# Env overrides: STALE_MIN (default 45), BAD_NEEDED (consecutive bad polls, default 3),
# INTERVAL (s, default 60), REMIND (s between repeat alerts, default 7200),
# ONCE=1 run a single poll, DRY=1 print instead of pushing.
# The public endpoint is trimmed (no freshness block); the Shield's local API has it.
URL="${HEALTH_URL:-http://127.0.0.1:5001/api/health}"
NTFY="${NTFY_URL:-$(cat "$HOME/.presek_ntfy_url" 2>/dev/null)}"  # secret topic URL: env or file, never committed
STALE_MIN="${STALE_MIN:-45}"
BAD_NEEDED="${BAD_NEEDED:-3}"
INTERVAL="${INTERVAL:-60}"
REMIND="${REMIND:-7200}"
LOG="${LOG:-$HOME/presek-ingest-watch.log}"
TMP="${TMPDIR:-$HOME}/ingest_watch_health.json"

log() { echo "$(date -u '+%F %T') $*" >> "$LOG"; }

push() { # title, message, priority
  if [ "${DRY:-0}" = "1" ]; then echo "[dry] $1 | $2"; return 0; fi
  curl -s -m 10 -H "Title: $1" -H "Priority: ${3:-default}" -H "Tags: warning" -d "$2" "$NTFY" >/dev/null 2>&1
}

bad=0
alerted=0
last_alert=0
log "ingest-watch start stale_min=$STALE_MIN bad_needed=$BAD_NEEDED"

while true; do
  now=$(date +%s)
  code=$(curl -s -m 15 -o "$TMP" -w '%{http_code}' "$URL" 2>/dev/null)
  age=""
  if [ "$code" = "200" ]; then
    age=$(grep -o '"age_minutes": *[0-9]*' "$TMP" 2>/dev/null | head -1 | grep -o '[0-9]*$')
  fi

  if [ -z "$age" ]; then
    # API unreachable or no freshness field: presek-healthcheck owns that case.
    log "skip http=$code (no freshness value)"
  elif [ "$age" -ge "$STALE_MIN" ]; then
    bad=$((bad + 1))
    log "STALE age=${age}m bad=$bad"
    if [ "$bad" -ge "$BAD_NEEDED" ]; then
      if [ "$alerted" = "0" ] || [ $((now - last_alert)) -ge "$REMIND" ]; then
        push "presek INGESTION STALE" "No new articles for ${age} min (threshold ${STALE_MIN}). The phone worker host is probably down: check Redis, celery_supervisor and the watchdog on the phone." high
        alerted=1
        last_alert=$now
      fi
    fi
  else
    if [ "$alerted" = "1" ]; then
      push "presek ingestion RECOVERED" "Ingestion is fresh again (age ${age} min)." default
      log "RECOVERED age=${age}m"
    fi
    bad=0
    alerted=0
  fi

  [ "${ONCE:-0}" = "1" ] && break
  sleep "$INTERVAL"
done
