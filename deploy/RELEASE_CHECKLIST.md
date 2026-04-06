# Presek release checklist

## Before deploy

- Verify the repo is clean on the server checkout.
- Run a database backup:
  - `bash deploy/backup_postgres.sh`
- Confirm the last local smoke check is green:
  - `bash deploy/smoke_check.sh`
- If source governance shows degraded or auto-paused feeds, decide whether to proceed anyway.

## Deploy

- Run:
  - `bash deploy/deploy_release.sh`
- Confirm:
  - `sudo systemctl status presek.target --no-pager`
  - `sudo journalctl -u presek-fastapi.service -n 50 --no-pager`
  - `sudo journalctl -u presek-astro.service -n 50 --no-pager`

## After deploy

- Open:
  - `/`
  - one `/cluster/...` page
  - `/archive`
- Confirm:
  - homepage loads
  - `Прашај го Пресек` still answers
  - no major source is unexpectedly auto-paused
  - freshness is not stale

## Rollback

- If smoke checks fail or the app is clearly degraded:
  - `bash deploy/rollback_release.sh`
- Then confirm:
  - `bash deploy/smoke_check.sh`
  - `sudo systemctl status presek.target --no-pager`
