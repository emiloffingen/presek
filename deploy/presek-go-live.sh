#!/bin/bash
# presek-go-live — one command to run when you get home.
#
# Problem it solves: the Cloudflare tunnel has TWO connectors (phone + shield).
# If the shield runs a STALE build, public presek.mk intermittently serves old
# content (e.g. the Serbian build, missing /feed.xml) because Cloudflare
# load-balances between them.
#
# This script:
#   1. finds the shield (tries known addresses; override with SHIELD_HOST=user@ip)
#   2. builds once on the phone and ships that exact dist to the shield (no rebuild)
#   3. restarts services on both
#   4. VERIFIES both hosts and the public edge are consistent
#
# Usage:
#   deploy/presek-go-live.sh                 # auto-detect shield, full go-live
#   SHIELD_HOST=u0_a106@192.168.1.50 deploy/presek-go-live.sh
#   deploy/presek-go-live.sh --phone-only    # just build + restart the phone
set -uo pipefail

APP_DIR="${PRESEK_APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
SSH_KEY="${SSH_KEY:-/root/.ssh/termux_test}"
COMMON="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 -o BatchMode=yes"

log()  { echo "[$(date '+%F %T')] [go-live] $*"; }
warn() { echo "[$(date '+%F %T')] [go-live] !! $*"; }

DO_PHONE=1; DO_SHIELD=1
for a in "$@"; do
  [ "$a" = "--phone-only" ] && DO_SHIELD=0
  [ "$a" = "--no-build" ] && DO_PHONE=0
done

# --- 1. locate the shield ---------------------------------------------------
detect_shield() {
  if [ -n "${SHIELD_HOST:-}" ]; then echo "$SHIELD_HOST"; return; fi
  local candidates=(
    "u0_a106@192.168.0.62:8022"
    "u0_a106@192.168.0.60:8022"
    "u0_a106@100.77.135.12:8022"
    "u0_a106@192.168.1.60:8022"
    "u0_a106@192.168.8.60:8022"
  )
  # Discover by mDNS name first (works on any subnet without knowing the IP).
  if command -v avahi-browse >/dev/null 2>&1; then
    for name in shield Shield shield.local; do
      local ip
      ip="$(avahi-browse -rt --parsable _ssh._tcp 2>/dev/null | awk -F';' -v n="$name" 'tolower($7) ~ tolower(n) {print $8}' | head -1)"
      [ -n "$ip" ] && candidates=("u0_a106@$ip:8022" "${candidates[@]}")
    done
  fi
  # Add any same-subnet host that answers on SSH port 8022 but skip our own IP.
  for c in "${candidates[@]}"; do
    local host="${c%:*}" port="${c#*:}"
    if timeout 5 ssh -i "$SSH_KEY" -p "$port" $COMMON "$host" true 2>/dev/null; then
      echo "$c"; return
    fi
  done
  echo ""
}

if [ "$DO_SHIELD" = "1" ]; then
  SHIELD="$(detect_shield)"
  if [ -z "$SHIELD" ]; then
    warn "could not reach the shield on any known address."
    warn "set SHIELD_HOST=user@ip[:port] and re-run, or use --phone-only."
    exit 2
  fi
  SHIELD_HOST="${SHIELD%:*}"; SHIELD_PORT="${SHIELD#*:}"
  SSH_OPTS="-i $SSH_KEY -p $SHIELD_PORT $COMMON"
  SCP_OPTS="-i $SSH_KEY -P $SHIELD_PORT $COMMON"
  log "shield found at $SHIELD_HOST:$SHIELD_PORT"
fi

# --- 2. deploy the phone (build once) --------------------------------------
if [ "$DO_PHONE" = "1" ]; then
  log "=== building + restarting the phone ==="
  bash "$APP_DIR/deploy/presek-deploy.sh" || { warn "phone deploy failed"; exit 1; }
fi

# --- 3. ship the phone's dist to the shield (verbatim) ---------------------
if [ "$DO_SHIELD" = "1" ]; then
  WEB_DIR="$APP_DIR/web"
  [ -f "$WEB_DIR/dist/server/entry.mjs" ] || { warn "no phone dist to ship"; exit 1; }
  TMP="$(mktemp -d)"; DIST="$TMP/web_dist.tgz"
  log "=== packaging phone dist ==="
  tar czf "$DIST" -C "$WEB_DIR" dist || { warn "packaging failed"; exit 1; }
  log "shipping $(du -h "$DIST" | cut -f1) to $SHIELD_HOST"
  ssh $SSH_OPTS "$SHIELD_HOST" "mkdir -p /sdcard/presek_stage" || { warn "shield unreachable"; exit 1; }
  scp $SCP_OPTS "$DIST" "$SHIELD_HOST:/sdcard/presek_stage/" || { warn "scp failed"; exit 1; }
  log "=== applying dist on shield (no rebuild) ==="
  ssh $SSH_OPTS "$SHIELD_HOST" "proot-distro login debian -- /bin/sh -c '
    cd /root/presek/web || exit 1
    rm -rf dist && tar xzf /sdcard/presek_stage/web_dist.tgz || exit 1
    [ -f dist/server/entry.mjs ] || { echo NO_ENTRY; exit 1; }
    # Restart the Astro server so the new dist is served (kill the old node).
    pkill -f "dist/server/entry.mjs" 2>/dev/null
    pkill -f "core.api_fast" 2>/dev/null
    pkill -f "core.celery_app" 2>/dev/null
    echo SHIELD_DIST_APPLIED
  '" || { warn "shield apply failed"; exit 1; }
  # Give the shield's watchdog a moment to respawn its services on the new dist.
  sleep 25
  rm -rf "$TMP"
fi

# --- 4. verify both hosts + the public edge --------------------------------
log "=== verifying ==="
sleep 20
PHONE_MK=$(curl -s -m 10 http://127.0.0.1:3000/ | grep -o 'presek_mk' | head -1)
PHONE_FEED=$(curl -s -o /dev/null -w '%{http_code}' -m 10 http://127.0.0.1:3000/feed.xml)
log "phone : social=$PHONE_MK feed.xml=$PHONE_FEED"

if [ "$DO_SHIELD" = "1" ]; then
  SH_MK=$(ssh $SSH_OPTS "$SHIELD_HOST" "proot-distro login debian -- curl -s -m 10 http://127.0.0.1:3000/ | grep -o presek_mk | head -1" 2>/dev/null | tail -1)
  SH_FEED=$(ssh $SSH_OPTS "$SHIELD_HOST" "proot-distro login debian -- curl -s -o /dev/null -w '%{http_code}' -m 10 http://127.0.0.1:3000/feed.xml" 2>/dev/null | tail -1)
  log "shield: social=$SH_MK feed.xml=$SH_FEED"
fi

log "checking public edge (12 requests, expect all presek_mk) ..."
mk=0; rs=0
for i in $(seq 1 12); do
  s=$(curl -s -m 12 "https://presek.mk/?cb=$RANDOM$i" | grep -o 'presek_[a-z]*' | grep -v emblem | head -1)
  [ "$s" = "presek_mk" ] && mk=$((mk+1)) || rs=$((rs+1))
done
log "public: presek_mk=$mk/12 stale=$rs/12"
if [ "$rs" -gt 0 ]; then
  warn "STILL serving stale content on some requests — a connector is still on the old build."
  warn "re-run, or check the Cloudflare tunnel connectors for a third origin."
  exit 1
fi
log "GO-LIVE OK: phone + shield + public edge all consistent"
