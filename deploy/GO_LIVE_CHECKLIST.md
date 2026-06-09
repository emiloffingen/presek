# Presek ga-live checklist

## 1. Pre-flight

Run from the repo root on the production server:

```sh
cd /home/emiloffingen/presek
APP_ROOT=/home/emiloffingen/presek-runtime test -f "$APP_ROOT/shared/.env" && echo shared-env-ok
APP_ROOT=/home/emiloffingen/presek-runtime test -x "$APP_ROOT/venv/bin/python3" && echo runtime-venv-ok
APP_ROOT=/home/emiloffingen/presek-runtime test -d "$APP_ROOT/shared/web-node_modules" && echo shared-web-deps-ok
```

Confirm:

- `shared/.env` exists
- runtime venv exists
- shared Astro dependencies exist

## 2. Smoke test before release

```sh
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/runtime_status.sh
bash deploy/smoke_check.sh
```

This now checks:

- Astro responds successfully
- API health returns `200`
- API health reports `database.ok = true`
- API health reports `redis.ok = true`
- Public site responds successfully

## 3. Deploy

```sh
sudo APP_ROOT=/home/emiloffingen/presek-runtime INSTALL_NGINX=0 bash deploy/install_server.sh
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/deploy_release.sh
```

Skip the `install_server.sh` step only when the release does not change systemd or installer files.

## 4. Service verification

```sh
sudo systemctl status presek.target --no-pager
sudo journalctl -u presek-astro.service -n 50 --no-pager
sudo journalctl -u presek-fastapi-unified.service -n 50 --no-pager
sudo journalctl -u presek-worker.service -n 50 --no-pager
sudo journalctl -u presek-ingestion-worker.service -n 50 --no-pager
sudo journalctl -u presek-beat.service -n 50 --no-pager
```

Confirm:

- no service is in a failed state
- no repeating startup crashes
- no DB or Redis connection errors
- no import/runtime tracebacks

## 5. Manual live verification

Open and verify:

- `https://presek.live/`
- one `https://presek.live/cluster/...` page
- `https://presek.live/archive`

Confirm:

- freshness is not stale
- homepage renders articles and images
- one cluster page loads fully
- no major source is unexpectedly auto-paused

## 6. Launch decision

Go live only if:

- smoke checks passed
- all services are healthy
- live pages render correctly
- no major runtime errors appear in the journals

## 7. Rollback

If release validation fails:

```sh
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/rollback_release.sh
```

Then rerun:

```sh
bash deploy/smoke_check.sh
sudo systemctl status presek.target --no-pager
sudo systemctl status presek-ingestion-worker.service --no-pager
```
