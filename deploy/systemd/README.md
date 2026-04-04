# Presek systemd

These units replace `screen` for supervised deployment of `presek.live`.

## Services

- `presek-web.service`: Flask + Gunicorn on `127.0.0.1:5000`
- `presek-worker.service`: Celery worker
- `presek-beat.service`: Celery beat scheduler
- `presek-fastapi.service`: FastAPI on `127.0.0.1:5001`
- `presek-astro.service`: Astro frontend on `127.0.0.1:3000`
- `presek.target`: starts the full stack

All services restart automatically and log to the systemd journal.

## Assumptions

- Repo path: `/home/emiloffingen/presek`
- Service user: `emiloffingen`
- Python virtualenv: `/home/emiloffingen/presek/venv`
- Astro build already exists at `web/dist/server/entry.mjs`
- `.env` is a shell-compatible file and is sourced with `bash`

If your production server uses a different Unix user or checkout path, edit the unit files before installing them.

## Install

Copy the units into `/etc/systemd/system` on the server:

```sh
sudo cp deploy/systemd/presek-*.service deploy/systemd/presek.target /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable presek.target
sudo systemctl start presek.target
```

## Operate

```sh
sudo systemctl status presek.target
sudo systemctl status presek-web.service
sudo journalctl -u presek-web.service -f
sudo journalctl -u presek-worker.service -f
sudo systemctl restart presek-astro.service
sudo systemctl stop presek.target
```

## Notes

- `presek-web.service` runs the DB schema init in `ExecStartPre`.
- `presek-astro.service` refuses to start if the Astro server build is missing.
- These units do not manage PostgreSQL, Redis, or nginx. Keep those as separate system services.
