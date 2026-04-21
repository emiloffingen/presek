# Presek systemd

These units are the supported production runtime for `presek.live`.

`start.sh` remains in the repo only as a local/manual fallback launcher. Do not treat it as the primary live process manager.

## Services

- `presek-worker.service`: Celery worker for `celery`, `intelligence`, and `maintenance`
- `presek-worker-ingestion.service`: dedicated Celery worker for `ingestion`
- `presek-worker-delivery.service`: dedicated Celery worker for `delivery`
- `presek-beat.service`: Celery beat scheduler
- `presek-fastapi.service`: FastAPI on `127.0.0.1:5001`
- `presek-astro.service`: Astro frontend on `127.0.0.1:3000`
- `presek.target`: starts the full stack

All services restart automatically and log to the systemd journal.

## Assumptions

- Runtime root: `/home/emiloffingen/presek-runtime`
- Current release symlink: `/home/emiloffingen/presek-runtime/current`
- Shared env: `/home/emiloffingen/presek-runtime/shared/.env`
- Shared Astro dependencies: `/home/emiloffingen/presek-runtime/shared/web-node_modules`
- Python virtualenv: `/home/emiloffingen/presek-runtime/venv`
- Service user: `emiloffingen`
- `.env` is a shell-compatible file and is sourced with `bash`

If your production server uses a different Unix user or checkout path, edit the unit files before installing them.

## Install

Bootstrap the runtime root first:

```sh
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/bootstrap_runtime_root.sh
```

Copy the units into `/etc/systemd/system` on the server:

```sh
sudo cp deploy/systemd/presek-*.service deploy/systemd/presek.target /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable presek.target
sudo systemctl start presek.target
```

Or use the installer in systemd-only mode when nginx/TLS is managed elsewhere:

```sh
sudo APP_ROOT=/home/emiloffingen/presek-runtime INSTALL_NGINX=0 bash deploy/install_server.sh
```

## Operate

```sh
sudo systemctl status presek.target
sudo systemctl status presek-fastapi.service
sudo journalctl -u presek-fastapi.service -f
sudo journalctl -u presek-worker.service -f
sudo journalctl -u presek-worker-ingestion.service -f
sudo journalctl -u presek-worker-delivery.service -f
sudo systemctl restart presek-astro.service
sudo systemctl stop presek.target
bash deploy/smoke_check.sh
bash deploy/backup_postgres.sh
```

## Notes

- `presek-fastapi.service` is the public API service.
- `presek-astro.service` runs from `current/web` and still guards against stale or broken `dist` output.
- `presek-beat.service` stores scheduler state in `shared/celerybeat-schedule`, not inside a release.
- Celery queues are split so `run_ingestion` cannot be buried behind delivery or downstream intelligence backlog.
- These units do not manage PostgreSQL, Redis, or nginx. Keep those as separate system services.
- After install or restart, run `deploy/smoke_check.sh` to verify the API and Astro locally before trusting the release.
- Keep a regular backup cadence with `deploy/backup_postgres.sh` or a system cron/timer wrapper around it.
