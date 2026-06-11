# Minimum production profile

Presek runs as a **systemd target** (`presek.target`) with nine units. Use this table during incidents to decide what to restart first.

| Service | Must run? | If stopped |
|---------|-----------|------------|
| `presek-fastapi-unified` | Yes | API and `/api/*` broken |
| `presek-astro` | Yes | Frontend SSR/static broken |
| `presek-worker-ingestion` | Yes | No new articles ingested |
| `presek-worker` (`intel-heavy`) | Yes | No synthesis, clustering backlog grows |
| `presek-beat` | Yes | Scheduled tasks stop |
| `presek-worker-fasttrack` | Mostly | Breaking news and fast summaries slow down |
| `presek-worker-delivery` | Yes | Newsletter/push delivery stops |
| `presek-worker-maintenance` | Yes | DB maintenance and backfill stall |

## First restart order after an incident

1. `presek-fastapi-unified` — restore user-facing API
2. `presek-worker-ingestion` — resume news intake
3. `presek-worker` (`intel-heavy`) — drain synthesis backlog

Then check queue depths:

```bash
/home/emiloffingen/presek-runtime/venv/bin/python3 \
  /home/emiloffingen/presek-runtime/current/scripts/queue_depths.py
```

Or open the admin cockpit **Celery queues** panel (`/admin` → queue depths + intel backlog status).

## Baseline capture

Save a snapshot of healthy production for comparison:

```bash
APP_ROOT=/home/emiloffingen/presek-runtime \
  bash /home/emiloffingen/presek-runtime/current/scripts/capture_baseline.sh
```

Logs land in `$APP_ROOT/shared/logs/baselines/`.

## Monitoring hooks

- **Synthesis quality:** `scripts/monitor_synthesis_quality.py` (cron every 15 min; see `deploy/crontab`)
- **Prometheus:** `sudo bash deploy/install_prometheus.sh`
- **Alertmanager + exporters + ntfy:** `sudo bash deploy/install_monitoring_exporters.sh`
- **Grafana dashboard:** `sudo bash deploy/install_grafana.sh` (UI on `127.0.0.1:3001`)
- **Metrics:** `http://127.0.0.1:5001/metrics` (localhost only; includes `presek_celery_queue_depth`, `presek_db_queries_total`)
- **Alerts:** Alertmanager on `127.0.0.1:9093` forwards to ntfy via `NTFY_TOPIC` / `NTFY_TOKEN`

## Read replica (optional)

When `DATABASE_READ_REPLICA_URL` is set in shared `.env`, SELECT/WITH queries auto-route to the replica pool. Writes and Celery tasks stay on primary.

Verify routing in metrics:

```bash
curl -s http://127.0.0.1:5001/metrics | grep presek_db_queries_total
```

During traffic, `pool="replica"` should climb for `/api/home`, `/api/news`, search, archive, and stats GETs.

## Split API / worker venvs (optional)

The unified venv (~6 GB with torch/spacy/playwright) can be split so FastAPI workers use less RAM:

```bash
APP_ROOT=/home/emiloffingen/presek-runtime \
  bash /home/emiloffingen/presek-runtime/current/deploy/setup_split_venvs.sh
```

Add to `$APP_ROOT/shared/.env`:

```bash
PRESEK_API_VENV=/home/emiloffingen/presek-runtime/venv-api
PRESEK_WORKER_VENV=/home/emiloffingen/presek-runtime/venv-worker
```

Then `sudo systemctl daemon-reload && sudo systemctl restart presek.target`.

Fresh hosts can also use `SPLIT_VENVS=1 bash deploy/bootstrap_runtime_root.sh`.
