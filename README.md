# Presek

Presek is a news aggregation and analysis app with:

- a FastAPI backend at the repo root
- an Astro frontend in [web](/home/emiloffingen/presek/web)
- deployment/runtime helpers in [deploy](/home/emiloffingen/presek/deploy)

## Current Structure

- `web/` is the only active frontend.
- The older root Vite frontend and Jinja template frontend were removed.
- `start.sh` is a local/manual runtime helper, not the production entrypoint.
- Production serves from the release runtime root at `/home/emiloffingen/presek-runtime/current` behind nginx/systemd.

## Runtime Paths

- Local/manual repo path: `./start.sh`
- Supported production path:
  1. `APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/bootstrap_runtime_root.sh`
  2. `sudo APP_ROOT=/home/emiloffingen/presek-runtime INSTALL_NGINX=0 bash deploy/install_server.sh`
  3. `APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/deploy_release.sh`

If a change touches `deploy/systemd/*` or `deploy/install_server.sh`, run step 2 before step 3 so the installed units match the release code.

## Common Commands

Backend tests:

```sh
./venv/bin/python3 -m pytest -q
```

Frontend tests:

```sh
cd web && npm test
```

Frontend build:

```sh
cd web && npm run build
```

## Manual Provider Checks

Ad hoc provider/key probes now live in [scripts](/home/emiloffingen/presek/scripts):

- `scripts/manual_check_ai_cascade.py`
- `scripts/manual_check_cloudflare.py`
- `scripts/manual_check_keys.py`
