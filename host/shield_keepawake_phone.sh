#!/bin/bash
# shield_keepawake_phone.sh - enforce the NVIDIA Shield's never-sleep power
# policy from the phone, over adb (shell uid), because the Shield's own
# keepawake runit service runs as the app uid and every privileged command
# (settings/dumpsys/input) silently fails with SecurityException.
#
# Idempotent and safe to run repeatedly. Invoked by presek_watchdog.sh on a
# throttle. Re-applies the settings and wakes the device if it is asleep.

set -u

HELPER="/root/shield-adb/adbvenv/bin/python"
ADB_PY="/root/shield-adb/shield_adb.py"
HOST="${SHIELD_ADB_HOST:-100.77.135.12}"
PORT="${SHIELD_ADB_PORT:-5555}"
LOG="/root/presek/logs/shield_keepawake.log"
LOCK="/root/presek/logs/shield_keepawake.lock"

mkdir -p "$(dirname "$LOG")"

# One run at a time; never pile up.
exec 9>"$LOCK"
flock -n 9 || exit 0

# Recycle Android TV background apps (~15 min) so GMS/TV providers cannot
# re-inflate RAM and push the box back into swap thrash.
KILLALL_STAMP="/root/presek/logs/.shield_killall_last"
now="$(date +%s)"
last_kill="$(cat "$KILLALL_STAMP" 2>/dev/null || echo 0)"
KILLALL=""
if [ $((now - last_kill)) -ge 900 ]; then
  KILLALL="am kill-all >/dev/null 2>&1;"
  echo "$now" > "$KILLALL_STAMP"
fi

REMOTE="${KILLALL}"'settings put global stay_on_while_plugged_in 7;
settings put global wifi_sleep_policy 2;
settings put global wifi_wakeup_enabled 1;
settings put global wifi_scan_always_enabled 1;
settings put system screen_off_timeout 2147483647;
settings put secure sleep_timeout -1;
settings put global hdmi_control_auto_device_off_enabled 0;
settings put global hdmi_control_react_on_active_source_enabled 0;
settings put global hdmi_control_send_active_source_enabled 0;
settings put global hdmi_one_touch_play_enabled 0;
dumpsys deviceidle disable >/dev/null 2>&1;
cmd deviceidle whitelist +com.termux >/dev/null 2>&1;
w=$(dumpsys power 2>/dev/null | grep -m1 mWakefulness= | cut -d= -f2 | tr -d " \r");
case "$w" in
  Asleep|Dozing|Dreaming) input keyevent 224 >/dev/null 2>&1; input keyevent 82 >/dev/null 2>&1; w="${w}->woke";;
esac;
echo "wake=$w stay=$(settings get global stay_on_while_plugged_in) idle=$(dumpsys deviceidle 2>/dev/null | grep -m1 mState=)"'

out="$("$HELPER" "$ADB_PY" "$HOST" "$PORT" "$REMOTE" 2>&1)"
rc=$?
ts="$(date '+%F %T')"
if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'wake='; then
  echo "[$ts] OK $(printf '%s' "$out" | grep 'wake=' | tail -1)" >> "$LOG"
else
  echo "[$ts] FAIL rc=$rc $(printf '%s' "$out" | tail -1)" >> "$LOG"
fi
exit 0
