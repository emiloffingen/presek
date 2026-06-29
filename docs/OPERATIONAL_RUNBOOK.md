# Presek Operational Runbook

This document serves as the guide for system operators managing the Presek application in staging and production environments.

---

## 🏗️ 1. Service Management (systemd target)

Presek runs as a unified **systemd target** (`presek.target`) managing nine distinct service units.

### 📋 Service Inventory

| Service Unit | Purpose | Impact if Offline |
| :--- | :--- | :--- |
| `presek-fastapi-unified.service` | FastAPI Backend API | API and `/api/*` endpoints fail, frontend breaks |
| `presek-astro.service` | Astro SSR/Static Frontend | Web page serving fails (502/504) |
| `presek-worker-ingestion.service` | Ingests news from RSS Feeds | Ingestion stops, no new articles appear |
| `presek-worker.service` (`intel-heavy`) | Core NLP & Synthesis processing | No new syntheses or cluster groupings are processed |
| `presek-beat.service` | Celery Beat Scheduler | Background cron cycles stall |
| `presek-worker-fasttrack.service` | Breaking news & fast syntheses | Priority syntheses slow down |
| `presek-worker-delivery.service` | Email and push notification delivery | Newsletters and alerts stop sending |
| `presek-worker-maintenance.service` | DB maintenance & cleanup operations | Maintenance tasks stall, DB sizes grow |
| `presek-worker-ingestion-crawl.service` | Web extraction and feed crawling | Starvation of ingestion-crawl queue |

### 🛠️ Common Controls

```bash
# Check status of the entire application
sudo systemctl status presek.target

# Restart all Presek services
sudo systemctl restart presek.target

# Stop all Presek services
sudo systemctl stop presek.target

# Start all Presek services
sudo systemctl start presek.target

# Reload systemd configs after unit changes
sudo systemctl daemon-reload
```

---

## 🚦 2. Health & Monitoring

### 🔬 Checking Queue Depths
When background workers lag, check queue depths via CLI:
```bash
/home/emiloffingen/presek-runtime/venv/bin/python3 \
  /home/emiloffingen/presek-runtime/current/scripts/queue_depths.py
```
Or check the **Admin Cockpit** (`/admin` → queue depths + intel backlog status).

### 🔍 Production Metrics & Alerting
- **Metrics endpoint:** `http://127.0.0.1:5001/metrics` (localhost only).
- Includes:
  - `presek_celery_queue_depth`
  - `presek_db_queries_total`
- **Alertmanager:** Available on `http://127.0.0.1:9093`.
- **Grafana Dashboard:** Access via port `3001` (e.g. `http://127.0.0.1:3001`).

---

## 💾 3. Database & Backups

### 🗄️ Backup Postgres
Trigger a manual database backup:
```bash
bash /home/emiloffingen/presek-runtime/current/deploy/backup_postgres.sh
```
Backups are saved to `/home/emiloffingen/presek-runtime/shared/backups/`.

### 🔄 Offsite Cloudflare R2 Sync
Synchronize backups offsite to Cloudflare R2:
```bash
python3 /home/emiloffingen/presek-runtime/current/deploy/sync_backups_r2.py
```

### 🧹 Database Optimization & Pruning
A daily database prune runs at 3:00 AM via Celery beat. To manually force a database optimization:
```bash
bash /home/emiloffingen/presek-runtime/current/deploy/optimize_db.sh
```

---

## 🔀 4. Database Read Replica Management

Presek uses a read replica for GET requests when `DATABASE_READ_REPLICA_URL` is set in the environment.

### 🔌 Repair Replica Replication Lag
If replication lag exceeds safe limits, or if replica SQL workers crash-loop:
```bash
sudo APP_ROOT=/home/emiloffingen/presek-runtime \
  bash /home/emiloffingen/presek-runtime/current/deploy/repair_read_replica.sh
```

### ⚡ Verify Read Routing
Run this to confirm SELECT traffic is correctly routing to the read pool:
```bash
curl -s http://127.0.0.1:5001/metrics | grep presek_db_queries_total
```
Confirm the `pool="replica"` metric counter is incrementing.
