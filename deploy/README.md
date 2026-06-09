# Presek Production Deployment

Scripts and configuration for deploying Presek to the release runtime at `~/presek-runtime`.

## Supported Production Path

```bash
# 1. Bootstrap runtime (once, or when uv.lock / web deps change)
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/bootstrap_runtime_root.sh

# 2. Install systemd/nginx units (once, or when deploy/systemd changes)
sudo APP_ROOT=/home/emiloffingen/presek-runtime INSTALL_NGINX=0 bash deploy/install_server.sh

# 3. Deploy a release (every change)
APP_ROOT=/home/emiloffingen/presek-runtime \
DEPLOY_GIT_DIR=/home/emiloffingen/presek \
bash deploy/deploy_release.sh
```

CI uses `deploy/ci_deploy.sh`, which sets `DEPLOY_GIT_DIR` and runs `deploy_release.sh`.

## How `deploy_release.sh` Works

1. Acquires a deploy lock (`$APP_ROOT/.deploy.lock`)
2. Pulls latest code from `DEPLOY_GIT_DIR` (if set)
3. Runs preflight checks (env, venv, nginx, service status)
4. Updates Python/web deps via `bootstrap_runtime_root.sh` when lock files change
5. Copies code into `$APP_ROOT/releases/<timestamp>/`
6. Builds the Astro frontend (`npm ci` when no shared `node_modules`)
7. Backs up PostgreSQL (fails deploy if backup fails in full mode)
8. Runs Alembic migrations (fails deploy on error, before switching release)
9. Switches `$APP_ROOT/current` symlink
10. Restarts FastAPI, Astro, and workers; waits for health checks
11. Runs post-deploy smoke tests; auto-rolls back on failure
12. Prunes old releases

## Deploy Modes

| Mode | Use case |
|------|----------|
| `full` (default) | Complete deploy with backup, migrations, smoke tests |
| `frontend` | Rebuild web, restart Astro only |
| `backend` | Skip web build, restart API/workers |
| `workers` | Restart background workers only |
| `ops` | Copy release only, no build/DB/restart |
| `fast` | Skip DB backup and migrations |

```bash
DEPLOY_MODE=frontend bash deploy/deploy_release.sh
```

## Key Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ROOT` | `~/presek-runtime` | Runtime root |
| `DEPLOY_GIT_DIR` | unset | Git checkout to pull and deploy from |
| `DEPLOY_GIT_BRANCH` | `main` | Branch to deploy |
| `REQUIRE_DB_BACKUP` | `1` in full mode | Fail if pre-deploy backup fails |
| `RUN_PREFLIGHT` | `1` in full mode | Run pre-deploy checks |
| `RUN_SMOKE_CHECKS` | `1` | Run post-deploy smoke tests |
| `AUTO_ROLLBACK_ON_FAILURE` | `1` | Roll back on smoke/health failure |
| `PRUNE_RELEASES` | `1` | Prune old releases after success |
| `ALLOW_CURRENT_SOURCE` | `0` | Allow deploying from `current` release dir |

## Rollback

```bash
APP_ROOT=/home/emiloffingen/presek-runtime bash deploy/rollback_release.sh
```

Manual rollback is also triggered automatically when post-deploy smoke checks fail.

## CI/CD

GitHub Actions SSH deploy requires:

- `DEPLOY_SSH_HOST`, `DEPLOY_SSH_USER`, `DEPLOY_SSH_KEY`
- Optional: `DEPLOY_APP_ROOT`, `DEPLOY_GIT_DIR`, `DEPLOY_GIT_BRANCH`

The server must have a git clone at `DEPLOY_GIT_DIR`. CI pulls latest `main` then deploys.

Docker images built in CI are optional registry artifacts; production runs via systemd on the host.

## Configuration Layout

| Path | Purpose |
|------|---------|
| `$APP_ROOT/shared/.env` | Production environment variables |
| `$APP_ROOT/venv` | Python virtualenv (symlink to versioned env) |
| `$APP_ROOT/shared/web-node_modules` | Shared Astro dependencies |
| `$APP_ROOT/current` | Symlink to active release |
| `$APP_ROOT/previous` | Symlink to prior release (rollback) |
| `$APP_ROOT/shared/backups` | PostgreSQL backups |

## Maintenance Scripts

| Script | Purpose |
|--------|---------|
| `backup_postgres.sh` | Manual or cron DB backup |
| `smoke_check.sh` | Full application health verification |
| `preflight_check.sh` | Pre-deploy checks (set `SKIP_SMOKE=1` for deploy integration) |
| `runtime_status.sh` | Runtime layout and service summary |
| `prune_releases.sh` | Release disk retention (`DRY_RUN=1` to preview) |
| `crontab` | Example cron entries for backups, health, pruning |

## Legacy: `production_deploy.sh`

`deploy/production_deploy.sh` is a **legacy greenfield installer** for `/opt/presek` (Gunicorn + Celery on port 8000). It does not match the current FastAPI/Astro release runtime. Do not use it on an existing `presek-runtime` server.

`deploy/dry-run-deploy.sh` simulates that legacy script only.

## Troubleshooting

**Deploy blocked: "started from the current release"**
Set `DEPLOY_GIT_DIR` to your git checkout, or use `deploy/ci_deploy.sh`.

**Migration failed**
Deploy aborts before switching `current`. Fix the migration, then redeploy.

**Smoke checks failed after deploy**
Deploy auto-rolls back to `previous` when `AUTO_ROLLBACK_ON_FAILURE=1`.

**Check logs**
```bash
sudo journalctl -u presek-fastapi-unified.service -f
sudo journalctl -u presek-astro.service -f
tail -f $APP_ROOT/shared/logs/backup.log
```
