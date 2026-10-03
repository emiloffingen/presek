#!/data/data/com.termux/files/usr/bin/sh
# SHIELD DEPLOY — run this on the NVIDIA Shield (Termux, Android side) when it is
# back on the home LAN. Deploys the latest presek.mk frontend + restarts the stack.
#
# Usage (in the Shield's Termux):
#   sh /sdcard/opencode/SHIELD_DEPLOY.sh
#
# It expects the frontend bundle at /sdcard/presek_stage/web_dist.tgz
STAGE=/sdcard/presek_stage
SVCDIR=/data/data/com.termux/files/usr/var/service

echo "=== [1/5] check bundle ==="
if [ ! -f "$STAGE/web_dist.tgz" ]; then
  echo "MISSING $STAGE/web_dist.tgz — push it first (see note at bottom)."
  exit 1
fi
ls -la "$STAGE/web_dist.tgz"

echo "=== [2/5] deploy dist into the Debian proot ==="
proot-distro login debian -- /bin/sh -c \
  'cd /root/presek/web && rm -rf dist && tar xzf /sdcard/presek_stage/web_dist.tgz && echo DIST_OK && ls -la dist/server/entry.mjs'

echo "=== [3/5] ensure runit supervisor is up ==="
if pgrep -f runsvdir >/dev/null 2>&1; then
  echo "runsvdir RUNNING"
else
  echo "starting runsvdir"
  setsid runsvdir "$SVCDIR" </dev/null >/dev/null 2>&1 &
  sleep 2
fi
for s in agentd healthcheck backfill_all backupd; do
  printf "presek-%s: " "$s"
  sv status "$SVCDIR/presek-$s" 2>&1 | head -1
done

echo "=== [4/5] restart Astro (runit/agentd will bring it back) ==="
pkill -f "dist/server/entry.mjs"
sleep 6

echo "=== [5/5] verify ==="
curl -s -m 6 -o /dev/null -w "local astro:  %{http_code}\n" http://127.0.0.1:3000/
curl -s -m 6 -o /dev/null -w "local fastapi:%{http_code}\n" http://127.0.0.1:5001/api/health
curl -s -m 12 -o /dev/null -w "public site: %{http_code}\n" https://presek.mk/
echo "=== dead links on public (expect none) ==="
curl -s -m 12 https://presek.mk/ | grep -oE 'href="[^"]*/(briefing|for-you|pulse|pregled|analize)"' | sort -u || true
echo "SHIELD_DEPLOY_DONE"

# ---------------------------------------------------------------------------
# If the bundle is missing, copy it from the phone to the Shield. From the
# phone's Termux (adb to the Shield at 192.168.0.60:5555):
#
#   adb connect 192.168.0.60:5555
#   adb -s 192.168.0.60:5555 push /sdcard/presek_stage/web_dist.tgz /sdcard/presek_stage/web_dist.tgz
#   adb -s 192.168.0.60:5555 shell input keyevent 224   # wake
#   # then in the Shield's opencode/Termux run: sh /sdcard/opencode/SHIELD_DEPLOY.sh
# ---------------------------------------------------------------------------
