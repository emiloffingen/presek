# Presek Troubleshooting Guide

This guide describes how to diagnose and resolve common errors and operational incidents on Presek.

---

## 🛑 1. Ingestion Bottlenecks and Queue Congestion

### Symptoms
- No new articles appear on the main feed.
- Memory consumption rises on the host.
- Celery queue depths (`intel-heavy`, `synthesis`) exceed the warning threshold (>100).

### Diagnosis
1. Check Celery queue statuses:
   ```bash
   /home/emiloffingen/presek-runtime/venv/bin/python3 /home/emiloffingen/presek-runtime/current/scripts/queue_depths.py
   ```
2. Check log streams of ingestion workers:
   ```bash
   journalctl -u presek-worker-ingestion -n 100 --no-pager
   journalctl -u presek-worker -n 100 --no-pager
   ```

### Mitigation
If the `fast-track` or `maintenance` queues are congested with duplicate or misrouted tasks, run the queue-grooming scripts:
```bash
# Groom and prune fast-track queue
/home/emiloffingen/presek-runtime/venv/bin/python3 -c "from tasks.utils import reprioritize_fast_track_queue; print(reprioritize_fast_track_queue())"

# Groom and prune maintenance queue
/home/emiloffingen/presek-runtime/venv/bin/python3 -c "from tasks.utils import reprioritize_maintenance_queue; print(reprioritize_maintenance_queue())"
```

---

## 🔒 2. Redis Task Lock Recovery

### Symptoms
- Ingestion, crawler, or homepage supply tasks report they are "already running" or "skipped: already_running", but no actual processing is occurring.
- Occurs when a worker dies mid-task and fails to clean up its Redis lock key.

### Diagnosis
Verify if active worker processes exist:
```bash
ps aux | grep celery
```

### Mitigation
Clear stale locks from Redis. Connect to Redis CLI and query keys:
```bash
redis-cli
127.0.0.1:6379> KEYS "lock:*"
127.0.0.1:6379> DEL "lock:boost_homepage_cluster_supply"
127.0.0.1:6379> DEL "lock:ingestion_lock"
```

---

## 🔀 3. Database Read-Replica Failures

### Symptoms
- Front page loads sluggishly or times out.
- Database logs contain: `duplicate key value violates unique constraint`
- PostgreSQL logical replication worker is in a crash-loop.

### Diagnosis
Check PostgreSQL log streams on the host:
```bash
sudo tail -n 100 /var/log/postgresql/postgresql-16-main.log
```

### Mitigation
Reset logical replication slots and re-sync the read replica:
```bash
sudo APP_ROOT=/home/emiloffingen/presek-runtime \
  bash /home/emiloffingen/presek-runtime/current/deploy/repair_read_replica.sh
```

---

## 🌐 4. Asset 404s and Content Security Policy (CSP) Violations

### Symptoms
- Browser console reports 404 errors fetching Noto Serif or Manrope fonts.
- UI elements fail to render or block scripts due to CSP violations.

### Diagnosis
Inspect response headers:
```bash
curl -I https://presek.live
```
Look for the `Content-Security-Policy` header.

### Mitigation
1. **Asset 404s:** Ensure Astro compiled build scripts executed successfully:
   ```bash
   APP_ROOT=/home/emiloffingen/presek-runtime \
     bash /home/emiloffingen/presek-runtime/current/deploy/ensure_astro_build.sh
   ```
2. **CSP Violations:** Ensure all dynamic inline script blocks are assigned a valid cryptographic `nonce`. Do not use hardcoded inline event handlers (e.g. `onload=""` or `onclick=""`) on HTML tags.
