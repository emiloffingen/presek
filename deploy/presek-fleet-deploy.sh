#!/bin/bash
# presek-fleet-deploy — deploy every Presek host from the phone in one command.
#
# The phone is the source of truth (it has the git checkout). This script:
#   1. deploys the phone itself (presek-deploy.sh)
#   2. archives the exact tracked source + web dist
#   3. ships them to the Shield and runs presek-deploy.sh --src=... there
#
# The Shield is bundle-deployed (no git checkout), so shipping source is what
# prevents the stale-rebuild class of bug (the /izvori breakage).
#
# Usage:
#   deploy/presek-fleet-deploy.sh                 # both hosts
#   deploy/presek-fleet-deploy.sh --shield-only
#   deploy/presek-fleet-deploy.sh --phone-only
#
# Env:
#   SHIELD_HOST   ssh target (default u0_a106@192.168.0.60, port 8022)
#   SSH_KEY       identity file (default /root/.ssh/termux_test)
set -uo pipefail

APP_DIR="${PRESEK_APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
STAGE=/sdcard/presek_stage
SHIELD_HOST="${SHIELD_HOST:-u0_a106@192.168.0.60}"
SHIELD_PORT="${SHIELD_PORT:-8022}"
SSH_KEY="${SSH_KEY:-/root/.ssh/termux_test}"
COMMON_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o BatchMode=yes"
SSH_OPTS="-i $SSH_KEY -p $SHIELD_PORT $COMMON_OPTS"
SCP_OPTS="-i $SSH_KEY -P $SHIELD_PORT $COMMON_OPTS"

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

if [ "$DO_PHONE" = "1" ]; then
  log "=== deploy phone ==="
  bash "$APP_DIR/deploy/presek-deploy.sh" "$@"
fi

if [ "$DO_SHIELD" = "0" ]; then
  log "shield skipped"
  exit 0
fi

log "=== build source + dist bundles for the shield ==="
TMP="$(mktemp -d)"
SRC="$TMP/presek_src.tgz"
DIST="$TMP/web_dist.tgz"
if [ -d "$APP_DIR/.git" ]; then
  git archive --format=tar.gz -o "$SRC" HEAD || { log "git archive failed"; exit 1; }
else
  log "no .git on this host; uploading source bundle is not possible"
  exit 1
fi
tar czf "$DIST" -C "$APP_DIR/web" dist || { log "dist archive failed"; exit 1; }
log "src=$(du -h "$SRC" | cut -f1) dist=$(du -h "$DIST" | cut -f1)"

log "=== ship to shield ($SHIELD_HOST) ==="
ssh $SSH_OPTS "$SHIELD_HOST" "mkdir -p $STAGE" || { log "could not create $STAGE on shield"; exit 1; }
scp $SCP_OPTS "$SRC" "$DIST" "$SHIELD_HOST:$STAGE/" || { log "scp failed"; exit 1; }

log "=== deploy on shield ==="
ssh $SSH_OPTS "$SHIELD_HOST" "proot-distro login debian -- /bin/sh -c '
  cd /root/presek || exit 1
  tar xzf $STAGE/web_dist.tgz -C web --overwrite 2>/dev/null
  bash deploy/presek-deploy.sh --no-pull --src=$STAGE/$(basename "$SRC") 2>&1 | tail -8
'" || { log "shield deploy failed"; exit 1; }

log "fleet deploy complete"
rm -rf "$TMP"
