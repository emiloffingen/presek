#!/bin/bash
# sync_shield.sh - ship the phone-built web dist to the Shield over SSH/scp.
#
# The phone is the only builder. The Shield's watchdog self-applies
# /sdcard/presek_stage/web_dist.tgz whenever its fp changes, so this replaces
# the old adb push (the Android adb binary cannot run in this proot container).
# Idempotent: skips when the current build fp was already synced.
set -u

APP_DIR="${PRESEK_APP_DIR:-/root/presek}"
LOG="$APP_DIR/logs/shield_sync.log"
MARKER="$APP_DIR/logs/.shield_synced"
LOCK="$APP_DIR/logs/.shield_sync.lock"
SHIELD_SSH="${SHIELD_SSH:-u0_a106@100.77.135.12}"
SSH_KEY="${SSH_KEY:-/root/.ssh/termux_test}"
SSH_PORT="${SHIELD_PORT:-8022}"
REMOTE_STAGE="${SHIELD_STAGE:-/storage/emulated/0/presek_stage}"

mkdir -p "$(dirname "$LOG")"
exec 8>"$LOCK"
flock -n 8 || exit 0

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
ssh_shield() {
  timeout 12 ssh -i "$SSH_KEY" -p "$SSH_PORT" \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o BatchMode=yes -o ConnectTimeout=8 "$SHIELD_SSH" "$@"
}

ENTRY="$APP_DIR/web/dist/server/entry.mjs"
[ -f "$ENTRY" ] || { log "no local dist ($ENTRY); skip"; exit 0; }
FP="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null)-$(stat -c %Y "$ENTRY" 2>/dev/null)"
if [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$FP" ]; then
  exit 0
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if ! tar czf "$TMP/web_dist.tgz" -C "$APP_DIR/web" dist 2>/dev/null; then
  log "tar failed"; exit 0
fi
printf '%s' "$FP" > "$TMP/web_dist.fp"
log "shipping build $FP ($(du -h "$TMP/web_dist.tgz" 2>/dev/null | cut -f1))"

if ! scp -i "$SSH_KEY" -P "$SSH_PORT" \
     -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
     -o BatchMode=yes -o ConnectTimeout=8 \
     "$TMP/web_dist.tgz" "$TMP/web_dist.fp" "$SHIELD_SSH:$REMOTE_STAGE/" >/dev/null 2>&1; then
  log "scp failed"; exit 0
fi

ok=0; i=0
while [ "$i" -lt 12 ]; do
  sleep 5; i=$((i + 1))
  if [ "$(ssh_shield cat "$REMOTE_STAGE/web_dist.applied" 2>/dev/null | tr -d '\r\n')" = "$FP" ]; then
    ok=1; break
  fi
done
if [ "$ok" = 1 ]; then
  echo "$FP" > "$MARKER"
  log "shield applied $FP"
else
  log "pushed but not applied yet (will retry)"
fi
