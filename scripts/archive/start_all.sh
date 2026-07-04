#!/bin/bash
# Presek startup script - starts all services with proper supervision
# Usage: ./scripts/start_all.sh [start|stop|status]

set -e
cd /home/emiloffingen/presek
source .env

PID_DIR="$(pwd)/pids"
mkdir -p "$PID_DIR"
LOG_DIR="$(pwd)/logs"

start_fastapi() {
    echo "Starting FastAPI..."
    nohup .venv/bin/uvicorn core.api_fast:app \
        --host 127.0.0.1 --port 5001 --workers 1 \
        --timeout-keep-alive 60 \
        > "$LOG_DIR/fastapi.log" 2>&1 &
    echo $! > "$PID_DIR/fastapi.pid"
    echo "  PID: $(cat $PID_DIR/fastapi.pid)"
}

start_celery_worker() {
    echo "Starting Celery worker..."
    nohup .venv/bin/celery -A core.celery_app worker \
        --loglevel=info --concurrency=1 \
        --logfile="$LOG_DIR/worker.log" \
        --pidfile="$PID_DIR/worker.pid" \
        > "$LOG_DIR/worker-stdout.log" 2>&1 &
    echo "  PID: $(cat $PID_DIR/worker.pid 2>/dev/null || echo $!)"
}

start_scheduler() {
    echo "Starting periodic scheduler..."
    nohup ./scripts/periodic_scheduler.sh \
        > "$LOG_DIR/periodic-scheduler.log" 2>&1 &
    echo $! > "$PID_DIR/scheduler.pid"
    echo "  PID: $(cat $PID_DIR/scheduler.pid)"
}

start_astro() {
    echo "Starting Astro SSR..."
    cd web
    nohup node ./dist/server/entry.mjs \
        > "$LOG_DIR/astro.log" 2>&1 &
    echo $! > "$PID_DIR/astro.pid"
    cd ..
    echo "  PID: $(cat $PID_DIR/astro.pid)"
}

stop_service() {
    local name=$1 pidfile="$PID_DIR/$1.pid"
    if [ -f "$pidfile" ]; then
        local pid=$(cat "$pidfile")
        echo "Stopping $name (PID $pid)..."
        kill "$pid" 2>/dev/null || true
        rm -f "$pidfile"
    fi
}

status_service() {
    local name=$1 pidfile="$PID_DIR/$1.pid"
    if [ -f "$pidfile" ]; then
        local pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            echo "  $name: running (PID $pid)"
        else
            echo "  $name: dead (stale PID $pid)"
        fi
    else
        echo "  $name: not started"
    fi
}

case "${1:-start}" in
    start)
        # Clean stale beat files
        rm -f celerybeat-schedule celerybeat-schedule-* 2>/dev/null
        start_fastapi
        start_celery_worker
        start_scheduler
        start_astro
        echo "All services started."
        ;;
    stop)
        for svc in fastapi celery_worker scheduler astro; do
            stop_service "$svc"
        done
        echo "All services stopped."
        ;;
    status)
        echo "Presek services:"
        for svc in fastapi celery_worker scheduler astro; do
            status_service "$svc"
        done
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac
