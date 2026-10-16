#!/data/data/com.termux/files/usr/bin/sh
# Periodic health check + daily summary.
# - Logs DOWN/RECOVERED state transitions.
# - Once per day writes a SUMMARY line with uptime + full-text coverage.
NTFY_URL="${NTFY_URL:-$(cat "$HOME/.presek_ntfy_url" 2>/dev/null)}"  # secret topic URL: env or file, never committed
STAGE=/sdcard/presek_stage
LOG=$STAGE/health.log
echo "healthcheck start $(date)" >> "$LOG"

state=unknown
miss=0
DOWN_NEEDED="${DOWN_NEEDED:-3}"
down_events=0
cur_day=$(date +%Y-%m-%d)

coverage() {
  proot-distro login debian -- /bin/sh -c 'cd /root/presek && .venv/bin/python -c "from core.database import db_manager as db; r=db.execute(\"SELECT count(*) AS total, count(full_content) AS with_body FROM articles WHERE country=%s\", (\"MK\",), read_only=True); print(\"{}/{} full\".format(r[0][\"with_body\"], r[0][\"total\"]))" 2>/dev/null' 2>/dev/null | tail -1
}

ntfy() {
  curl -s -m 10 -H "Title: presek.mk $1" -d "$2" "$NTFY_URL" >/dev/null 2>&1
}

# Baseline summary at startup.
echo "$cur_day SUMMARY state=$state down_events=0 coverage=$(coverage)" >> "$LOG"

while true; do
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  day=$(date +%Y-%m-%d)
  loc=$(curl -s -m 8 -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/ 2>/dev/null)
  pub=$(curl -s -m 12 -o /dev/null -w '%{http_code}' https://presek.mk/api/health 2>/dev/null)
  ok=0
  [ "$loc" = "200" ] && [ "$pub" = "200" ] && ok=1
  # Only declare DOWN (and push an alert) after DOWN_NEEDED consecutive failed
  # polls, so a one-poll network blip does not page. Every failed poll is still logged.
  if [ "$ok" = "1" ]; then
    if [ "$state" = "down" ]; then
      echo "$ts UP local=$loc public=$pub (recovered)" >> "$LOG"
      ntfy "RECOVERED" "$ts presek.mk is back up (local=$loc public=$pub)"
    elif [ "$state" != "up" ]; then
      echo "$ts UP local=$loc public=$pub" >> "$LOG"
    fi
    state=up
    miss=0
  else
    miss=$((miss + 1))
    echo "$ts DOWN local=$loc public=$pub miss=$miss" >> "$LOG"
    if [ "$miss" -ge "$DOWN_NEEDED" ] && [ "$state" != "down" ]; then
      down_events=$((down_events + 1))
      ntfy "DOWN" "$ts presek.mk DOWN local=$loc public=$pub miss=$miss"
      state=down
    fi
  fi

  # Daily rollover summary.
  if [ "$day" != "$cur_day" ]; then
    echo "$day SUMMARY state=$state down_events_prev_day=$down_events coverage=$(coverage)" >> "$LOG"
    down_events=0
    cur_day=$day
  fi

  sleep 60
done
