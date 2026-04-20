# Presek release checklist

## Before deploy

- Verify the repo checkout builds cleanly.
- If the change touches `deploy/systemd/` or `deploy/install_server.sh`, plan to run `install_server.sh` before the release deploy.
- Run a database backup:
  - `APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/backup_postgres.sh`
- Confirm the last local smoke check is green:
  - `bash deploy/smoke_check.sh`
- Confirm runtime layout:
  - `APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/runtime_status.sh`
- If source governance shows degraded or auto-paused feeds, decide whether to proceed anyway.
- Confirm:
  - `APP_ROOT/shared/.env` exists
  - `APP_ROOT/venv` exists
  - `APP_ROOT/shared/web-node_modules` exists

## Deploy

- If systemd or installer files changed, run:
  - `sudo APP_ROOT=/home/emiloffingen/presek-runtime INSTALL_NGINX=0 bash deploy/install_server.sh`
- Run:
  - `APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/deploy_release.sh`
- Confirm:
  - `APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/runtime_status.sh`
  - `sudo systemctl status presek.target --no-pager`
  - `sudo systemctl status presek-ingestion-worker.service --no-pager`
  - `sudo journalctl -u presek-fastapi.service -n 50 --no-pager`
  - `sudo journalctl -u presek-astro.service -n 50 --no-pager`
  - `sudo journalctl -u presek-worker.service -n 50 --no-pager`
  - `sudo journalctl -u presek-ingestion-worker.service -n 50 --no-pager`

## After deploy

- Open:
  - `/`
  - one `/cluster/...` page
  - `/archive`
- Confirm:
  - homepage loads
  - no major source is unexpectedly auto-paused
  - freshness is not stale

## Release retention

- Inspect retention plan:
  - `APP_ROOT=/home/emiloffingen/presek-runtime KEEP_EXTRA=2 DRY_RUN=1 bash deploy/prune_releases.sh`
- Apply pruning only after reviewing the dry-run output:
  - `APP_ROOT=/home/emiloffingen/presek-runtime KEEP_EXTRA=2 DRY_RUN=0 bash deploy/prune_releases.sh`

## Rollback

- If smoke checks fail or the app is clearly degraded:
  - `APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/rollback_release.sh`
- Then confirm:
  - `APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/runtime_status.sh`
  - `bash deploy/smoke_check.sh`
  - `sudo systemctl status presek.target --no-pager`
  - `sudo systemctl status presek-ingestion-worker.service --no-pager`
