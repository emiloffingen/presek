#!/bin/bash
# deep_check.sh - one-shot Presek health snapshot (no MCP dependency).
# Usage: bash /root/presek/scripts/deep_check.sh
set -u
APP_DIR="${PRESEK_APP_DIR:-/root/presek}"
echo "=== HEALTH ==="
curl -s -m 10 http://127.0.0.1:5001/api/health | "$APP_DIR/.venv/bin/python3" -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('status:', d.get('status'), '| version:', d.get('version'), '| uptime:', d.get('uptime_seconds'))
    print('freshness:', d.get('freshness'))
    print('queues total:', d.get('celery_queue',{}).get('total_depth'), '| degraded:', d.get('celery_queue',{}).get('degraded'))
    sq = d.get('synthesis_quality',{})
    print('synth:', sq.get('status'), '| 1d:', sq.get('primary',{}).get('total_summaries'), '| fallback:', sq.get('primary',{}).get('fallback_ratio'))
    print('ai:', {k: f\"{v['used']}/{v['limit']}\" for k,v in d.get('ai',{}).get('providers',{}).items()})
except Exception as e:
    print('HEALTH FAILED:', e)
"
echo "=== API ==="
curl -s -m 10 -o /dev/null -w "home mk: %{http_code} %{time_total}s\n" "http://127.0.0.1:5001/api/home?lang=mk"
echo "=== PROCS ==="
for pat in "uvicorn core.api_fast" "celery -A core.celery_app worker" "celery -A core.celery_app beat" "redis-server" "pgbouncer" "entry.mjs" "presek_watchdog" "failover_guard"; do
  n=$(pgrep -f "$pat" 2>/dev/null | wc -l)
  echo "$pat: $n"
done
echo "=== RESOURCES ==="
df -h / 2>/dev/null | tail -1
free -m 2>/dev/null | head -2
echo "=== LOG TAILS (errors) ==="
grep -i -c "ERROR" "$APP_DIR/logs/worker.log" 2>/dev/null | xargs echo "worker.log ERROR lines:"
tail -n 3 "$APP_DIR/logs/watchdog.log" 2>/dev/null
echo "=== DB ==="
"$APP_DIR/.venv/bin/python3" -c "
import os
d={}
with open('$APP_DIR/.env') as f:
    for l in f:
        l=l.strip()
        if not l or l.startswith('#') or '=' not in l: continue
        k,v=l.split('=',1); d[k.strip()]=v.strip().strip(chr(34)).strip(chr(39))
os.environ.update(d)
import psycopg
try:
    with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=10) as c:
        with c.cursor() as cur:
            cur.execute('SELECT COUNT(*), MAX(ingested_at) FROM articles')
            print('articles:', cur.fetchone())
except Exception as e:
    print('DB FAILED:', str(e)[:200])
" 2>&1
