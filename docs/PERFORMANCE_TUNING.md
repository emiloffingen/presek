# Presek Performance Tuning Guide

This document describes options and best practices for tuning the performance of Presek under heavy loads.

---

## 🔀 1. Prefork Worker and Venv Tuning

By default, the unified venv loaded on production machines consumes ~6 GB of memory because it loads full machine learning and NLP models (PyTorch, spaCy, Playwright).

### Split API and Worker Venvs
To decrease API worker memory footprints, run the split helper:
```bash
APP_ROOT=/home/emiloffingen/presek-runtime \
  bash /home/emiloffingen/presek-runtime/current/deploy/setup_split_venvs.sh
```
Add the following configuration lines to `/home/emiloffingen/presek-runtime/shared/.env`:
```bash
PRESEK_API_VENV=/home/emiloffingen/presek-runtime/venv-api
PRESEK_WORKER_VENV=/home/emiloffingen/presek-runtime/venv-worker
```
FastAPI workers will now use `venv-api` (excluding heavy NLP dependencies), allowing you to raise `UVICORN_WORKERS` safely without depleting the host's RAM.

---

## 🗄️ 2. PostgreSQL Connection Pooling

FastAPI uses both synchronous and asynchronous pools via `SQLAlchemy`.

### Connection Exhaustion
If the backend throws database connection timeouts under heavy load:
1. Adjust worker pool parameters in `.env`:
   - `DB_POOL_SIZE`: Limit of open persistent connections per worker (default `10`).
   - `DB_MAX_OVERFLOW`: Allowed overflow connections under load (default `20`).
2. Verify connection limits in PostgreSQL settings:
   ```sql
   SHOW max_connections;
   ```
   If needed, increase `max_connections` in `/etc/postgresql/16/main/postgresql.conf`.

---

## 🗂️ 3. Celery Concurrency Tuning

Workers running on CPU/memory-constrained environments should have concurrency limited to prevent OS thrashing.

### Worker Configurations
Adjust concurrency in `/etc/systemd/system/presek-worker*` unit configurations:
- `presek-worker-ingestion`: Concurrency `2` to `3` (CPU bound XML parsing).
- `presek-worker` (intel-heavy): Concurrency `1` (extremely memory and model intensive; do not exceed `1` on systems with < 16 GB of RAM).
- `presek-worker-fasttrack`: Concurrency `2` (fast syntheses).
