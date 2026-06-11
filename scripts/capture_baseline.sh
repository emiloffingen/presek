#!/usr/bin/env bash
# Capture a one-shot operational baseline for Presek (queue depths, health, disk, RAM).
set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/emiloffingen/presek-runtime}"
OUT_DIR="${OUT_DIR:-$APP_ROOT/shared/logs/baselines}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$OUT_DIR/baseline-$STAMP.txt"

mkdir -p "$OUT_DIR"

{
  echo "=== Presek baseline $STAMP ==="
  echo "APP_ROOT=$APP_ROOT"
  echo

  echo "--- release ---"
  readlink -f "$APP_ROOT/current" 2>/dev/null || echo "current: missing"
  echo

  echo "--- health ---"
  curl -sS http://127.0.0.1:5001/api/health 2>/dev/null | head -c 4000 || echo "health: unreachable"
  echo
  echo

  echo "--- queue depths (redis) ---"
  if [ -f "$APP_ROOT/current/scripts/queue_depths.py" ]; then
    "$APP_ROOT/venv/bin/python3" "$APP_ROOT/current/scripts/queue_depths.py" 2>/dev/null || true
  else
    echo "queue_depths.py not deployed yet"
  fi
  echo

  echo "--- memory ---"
  free -h 2>/dev/null || true
  echo

  echo "--- disk ---"
  df -h "$APP_ROOT" / 2>/dev/null || true
  echo

  echo "--- presek.target ---"
  systemctl is-active presek.target 2>/dev/null || true
} | tee "$OUT_FILE"

echo "Baseline written to $OUT_FILE"
