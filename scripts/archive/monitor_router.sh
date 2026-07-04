#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${APP_DIR}/.venv/bin/python"
if [ ! -x "$PYTHON" ] && [ -x "${APP_DIR}/venv/bin/python3" ]; then
  PYTHON="${APP_DIR}/venv/bin/python3"
fi

echo "=== Smart Model Router Monitoring ==="
echo "Last 10 routing decisions:"
journalctl -u presek-fastapi-unified --no-tail -n 50 | grep "\[router\]" | tail -10 || true

echo -e "\n=== Performance Metrics (process memory) ==="
cd "$APP_DIR"
"$PYTHON" -c "
from core.llm_router import SmartModelRouter
SmartModelRouter._load_metrics_from_redis()
for provider, stats in SmartModelRouter._provider_performance.items():
    perf = SmartModelRouter._get_provider_performance(provider)
    print(f'{provider:20} Success: {perf[\"success_rate\"]:.1%} Latency: {perf[\"avg_latency\"]:.2f}s')
"

echo -e "\n=== Quality Metrics ==="
cd "$APP_DIR"
"$PYTHON" -c "
from core.llm_router import SmartModelRouter
SmartModelRouter._load_metrics_from_redis()
for provider, samples in SmartModelRouter._provider_quality.items():
    if samples:
        avg = sum(s['score'] for s in samples) / len(samples)
        print(f'{provider:20} {avg:.2f} quality ({len(samples)} samples)')
"

echo -e "\n=== Current Configuration ==="
if [ -f "${APP_DIR}/.env" ]; then
  grep -E "FREE_API_KEYS_ENABLED|ROUTER_AB_TESTING|LOCAL_MODEL_PATH" "${APP_DIR}/.env" || true
else
  echo "(no local .env — check runtime shared env on production)"
fi
