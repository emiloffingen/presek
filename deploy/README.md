# Presek deploy

The supported production path is:

- `systemd` for app processes
- `nginx` for the public reverse proxy
- Cloudflare in front of nginx
- a release root with `releases/`, `current`, and `shared/`

`start.sh` is not the intended production runtime. Keep it for local/manual fallback only.

If you do not want to install the nginx and systemd files manually, use:

```sh
sudo bash deploy/install_server.sh
```

The installer now expects a release-based runtime layout and always installs the systemd units. nginx installation is optional:

- `INSTALL_NGINX=1`: require cert files and update nginx
- `INSTALL_NGINX=0`: leave nginx untouched and update only systemd/services
- `INSTALL_NGINX=auto` (default): update nginx only if the configured cert files exist

It refuses to continue if the Python venv, shared env file, or current release are missing, verifies the systemd units, optionally reloads nginx, and runs local smoke checks against:

- `http://127.0.0.1:5001/api/health`
- `http://127.0.0.1:3000`

You can override defaults with environment variables:

```sh
sudo DOMAIN=presek.live \
  SERVER_USER=emiloffingen \
  APP_ROOT=/home/emiloffingen/presek-runtime \
  INSTALL_NGINX=0 \
  CERT_FULLCHAIN=/etc/ssl/cloudflare/presek.live/fullchain.pem \
  CERT_PRIVKEY=/etc/ssl/cloudflare/presek.live/privkey.pem \
  bash deploy/install_server.sh
```

Before running it on the server, make sure:

- nginx is installed
- the Python virtualenv exists at `APP_ROOT/venv`
- the shared env exists at `APP_ROOT/shared/.env`
- the shared Astro dependencies exist at `APP_ROOT/shared/web-node_modules`
- a built release exists at `APP_ROOT/current`
- if `INSTALL_NGINX=1`, your TLS certificate files are already on disk

## Bootstrap a runtime root

For a first-time server setup, bootstrap the runtime root before the first release:

```sh
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/bootstrap_runtime_root.sh
```

That script creates:
- `APP_ROOT/shared/.env`
- `APP_ROOT/venv`
- `APP_ROOT/shared/web-deps/node_modules`
- `APP_ROOT/shared/web-node_modules`

## Runtime layout

Production should not run from the mutable repo checkout. Use a separate runtime root such as:

```text
/home/emiloffingen/presek-runtime/
  current -> releases/20260412T112310Z
  previous -> releases/20260411T230005Z
  releases/
  shared/
    .env
    celerybeat-schedule
    web-deps/
      package.json
      package-lock.json
      node_modules/
    web-node_modules -> web-deps/node_modules
    backups/
    logs/
  venv/
```

The repo checkout remains the build/source root. Services run from `current`.
Astro runtime dependencies are exposed through `shared/web-node_modules`, so each release can symlink `web/node_modules` without per-release installs or repo-checkout dependency.

## Operational helpers

Local post-deploy smoke check:

```sh
bash deploy/smoke_check.sh
```

Runtime layout and service status:

```sh
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/runtime_status.sh
```

Database backup:

```sh
bash deploy/backup_postgres.sh
```

This loads `.env`, uses `DATABASE_URL`, writes compressed dumps into `backups/`, and prunes older backups automatically.

Release deploy:

```sh
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/deploy_release.sh
```

If the release includes changes under `deploy/systemd/` or changes to `deploy/install_server.sh`, install the updated units first:

```sh
sudo APP_ROOT=/home/emiloffingen/presek-runtime INSTALL_NGINX=0 bash deploy/install_server.sh
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/deploy_release.sh
```

Rollback to the previous release symlink:

```sh
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/rollback_release.sh
```

Inspect release retention without deleting anything:

```sh
APP_ROOT=/home/emiloffingen/presek-runtime KEEP_EXTRA=2 DRY_RUN=1 bash deploy/prune_releases.sh
```

Prune old releases while always keeping `current`, `previous`, and the newest extra releases:

```sh
APP_ROOT=/home/emiloffingen/presek-runtime KEEP_EXTRA=2 DRY_RUN=0 bash deploy/prune_releases.sh
```

Step-by-step operator flow:

```sh
cat deploy/RELEASE_CHECKLIST.md
```
