#!/bin/bash
# presek-fleet-deploy — deploy every Presek host from the phone in one command.
#
# Design: the phone is the ONLY builder. It builds its own dist, then ships that
# exact dist to the Shield and (re)starts services there. The Shield never
# rebuilds, so its assets are byte-identical to the phone's — no cross-host
# chunk-hash divergence, no tunnel split-brain, no stale-source rebuilds.
#
# Usage:
#   deploy/presek-fleet-deploy.sh                 # phone + shield
#   deploy/presek-fleet-deploy.sh --phone-only
#   deploy/presek-fleet-deploy.sh --shield-only
#
# Env: SHIELD_HOST, SHIELD_PORT, SSH_KEY
set -uo pipefail

APP_DIR="${PRESEK_APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
WEB_DIR="$APP_DIR/web"
STAGE=/sdcard/presek_stage
SHIELD_HOST="${SHIELD_HOST:-u0_a106@192.168.0.60}"
SHIELD_PORT="${SHIELD_PORT:-8022}"
SSH_KEY="${SSH_KEY:-/root/.ssh/termux_test}"
COMMON="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o BatchMode=yes"
SSH_OPTS="-i $SSH_KEY -p $SHIELD_PORT $COMMON"
SCP_OPTS="-i $SSH_KEY -P $SHIELD_PORT $COMMON"

log() { echo "[$(date '+%F %T')] [fleet] $*"; }

DO_PHONE=1
DO_SHIELD=1
for arg in "$@"; do
  case "$arg" in
    --phone-only) DO_SHIELD=0 ;;
    --shield-only) DO_PHONE=0 ;;
  esac
done

cd "$APP_DIR" || { log "APP_DIR missing"; exit 1; }

# --- 1. build on the phone (the single builder) ----------------------------
if [ "$DO_PHONE" = "1" ]; then
  log "=== deploy phone (build + restart) ==="
  bash "$APP_DIR/deploy/presek-deploy.sh" "$@" || { log "phone deploy failed"; exit 1; }
fi

if [ "$DO_SHIELD" = "0" ]; then
  log "shield skipped"
  exit 0
fi

# --- 2. ship the phone's built dist to the shield --------------------------
[ -f "$WEB_DIR/dist/server/entry.mjs" ] || { log "no phone dist; run without --shield-only first"; exit 1; }

TMP="$(mktemp -d)"
DIST="$TMP/web_dist.tgz"
log "=== packaging phone dist ==="
tar czf "$DIST" -C "$WEB_DIR" dist || { log "dist archive failed"; exit 1; }
log "dist=$(du -h "$DIST" | cut -f1)"

log "=== ship to shield ($SHIELD_HOST) ==="
ssh $SSH_OPTS "$SHIELD_HOST" "mkdir -p $STAGE" || { log "could not create $STAGE on shield"; exit 1; }
scp $SCP_OPTS "$DIST" "$SHIELD_HOST:$STAGE/" || { log "scp failed"; exit 1; }

# --- 3. apply dist verbatim + restart (NO rebuild on the shield) -----------
log "=== apply dist on shield and restart ==="
ssh $SSH_OPTS "$SHIELD_HOST" "proot-distro login debian -- /bin/sh -c '
  cd /root/presek/web || exit 1
  rm -rf dist
  tar xzf $STAGE/web_dist.tgz || exit 1
  [ -f dist/server/entry.mjs ] || { echo NO_ENTRY; exit 1; }
  U=\"core.api\"\"_fast:app\"; W=\"core.\"\"celery_app worker\"; B=\"core.\"\"celery_app beat\"
  pkill -f \"\$U\"; pkill -f \"\$W\"; pkill -f \"\$B\"; pkill -f dist/server/entry.mjs
  echo SHIELD_DIST_APPLIED
'" || { log "shield apply failed"; exit 1; }

log "fleet deploy complete (phone builds, shield serves the same dist)"
rm -rf "$TMP"
