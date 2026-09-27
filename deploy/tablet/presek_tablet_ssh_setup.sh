#!/data/data/com.termux/files/usr/bin/bash
# presek_tablet_ssh_setup.sh — set up remote SSH for the TABLET (Termux host).
#
# Gives the tablet a dedicated Cloudflare tunnel so you can reach it from
# anywhere:  ssh-tablet.presek.mk -> tcp://localhost:8022
#
# Run this ON THE TABLET (Termux host, not inside proot).
# Idempotent: safe to re-run.

set -u
export PATH=/data/data/com.termux/files/usr/bin:$PATH

TUNNEL_ID="3a2d2a47-36af-4928-9c0a-ae24e757c72a"
HOSTNAME="ssh-tablet.presek.mk"
CFDIR=/data/data/com.termux/files/home/.cloudflared
CFG="$CFDIR/tablet-ssh-config.yml"
CREDS="$CFDIR/presek-tablet.credentials.json"
LOG=/data/data/com.termux/files/home/presek-ssh-tunnel.log
SVCDIR=$CFDIR
SUPERVISOR=/data/data/com.termux/files/home/presek_ssh_tunnel_supervisor.sh
LOCK=/data/data/com.termux/files/home/.presek_tablet_tunnel.lock

log() { echo "[$(date '+%F %T')] $*"; }

# 1. cloudflared present?
if ! command -v cloudflared >/dev/null 2>&1; then
  log "installing cloudflared"
  pkg install -y cloudflared || { log "could not install cloudflared"; exit 1; }
fi

mkdir -p "$CFDIR"; chmod 700 "$CFDIR" 2>/dev/null || true

# 2. credentials JSON from the tunnel token (token keys a/t/s -> CF key names)
# The token is NOT stored in the repo. Provide it one of these ways:
#   - export PRESEK_TABLET_TUNNEL_TOKEN=... before running, or
#   - place it in ~/.cloudflared/presek-tablet.token
# Get it from: Cloudflare dashboard > Zero Trust > Networks > Tunnels >
#   presek-tablet > Configure. (Also in the shared memory / password manager.)
TOKEN="${PRESEK_TABLET_TUNNEL_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f "$CFDIR/presek-tablet.token" ]; then
  TOKEN="$(tr -d '\n' < "$CFDIR/presek-tablet.token")"
fi
if [ -z "$TOKEN" ]; then
  log "ERROR: tunnel token not provided (PRESEK_TABLET_TUNNEL_TOKEN or $CFDIR/presek-tablet.token)"; exit 1
fi
python3 - "$TOKEN" <<'PY'
import base64, json, sys
tok = sys.argv[1].strip()
obj = json.loads(base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4)))
creds = {"AccountTag": obj["a"], "TunnelID": obj["t"], "TunnelSecret": obj["s"]}
open("/data/data/com.termux/files/home/.cloudflared/presek-tablet.credentials.json", "w").write(json.dumps(creds))
print("credentials written")
PY
chmod 600 "$CREDS"

# 3. tunnel config (distinct metrics port so instances never collide)
cat > "$CFG" <<'CFGEOF'
metrics: 127.0.0.1:20244
tunnel: 3a2d2a47-36af-4928-9c0a-ae24e757c72a
credentials-file: /data/data/com.termux/files/home/.cloudflared/presek-tablet.credentials.json
ingress:
  - hostname: ssh-tablet.presek.mk
    service: tcp://localhost:8022
  - service: http_status:404
CFGEOF

# 4. supervisor: keep the tunnel alive (runs on the Termux host, survives proot)
cat > "$SUPERVISOR" <<'SUPEOF'
#!/data/data/com.termux/files/usr/bin/bash
export PATH=/data/data/com.termux/files/usr/bin:$PATH
LOG=/data/data/com.termux/files/home/presek-ssh-tunnel-supervisor.log
LOCK=/data/data/com.termux/files/home/.presek_tablet_tunnel_supervisor.lock
INTERVAL="${SSH_TUNNEL_SUPERVISOR_INTERVAL:-45}"
exec 9>"$LOCK"; flock -n 9 || exit 0
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
log "tablet ssh tunnel supervisor started"
while true; do
  if ! pgrep -f 'cloudflared.*tablet-ssh-config.yml' >/dev/null 2>&1; then
    log "tunnel down -> starting"
    nohup cloudflared tunnel --config /data/data/com.termux/files/home/.cloudflared/tablet-ssh-config.yml \
      --logfile /data/data/com.termux/files/home/presek-ssh-tunnel.log run </dev/null >/dev/null 2>&1 &
  fi
  sleep "$INTERVAL"
done
SUPEOF
chmod +x "$SUPERVISOR"

# 5. start the tunnel now + the supervisor
pkill -f 'tablet-ssh-config.yml' 2>/dev/null || true
nohup cloudflared tunnel --config "$CFG" --logfile "$LOG" run </dev/null >/dev/null 2>&1 &
if ! pgrep -f 'presek_ssh_tunnel_supervisor' >/dev/null 2>&1; then
  setsid "$SUPERVISOR" </dev/null >/dev/null 2>&1 &
fi
sleep 8
log "running: $(pgrep -f 'tablet-ssh-config.yml' | wc -l) tunnel procs"

# 6. persist in Termux:Boot
BOOT=/data/data/com.termux/files/home/.termux/boot/startup.sh
mkdir -p "$(dirname "$BOOT")"
if ! grep -q "PRESEK TABLET SSH TUNNEL" "$BOOT" 2>/dev/null; then
  cat >> "$BOOT" <<'BOOTEOF'

# --- PRESEK TABLET SSH TUNNEL ---
if ! pgrep -f 'presek_ssh_tunnel_supervisor' >/dev/null 2>&1; then
  setsid /data/data/com.termux/files/home/presek_ssh_tunnel_supervisor.sh </dev/null >/dev/null 2>&1 &
fi
BOOTEOF
fi
chmod +x "$BOOT" 2>/dev/null || true

log "done. Connect with: ssh -o ProxyCommand='cloudflared access ssh --hostname %h' u0_a559@ssh-tablet.presek.mk"
