# Termux Production Runbook

`presek.mk` is served from a persistent Termux/Android host. No systemd or nginx
is involved; a shell watchdog supervises everything and a git poller auto-deploys
the checked-out branch.

## Topology

There are two Android hosts, both running the stack inside a Debian proot,
sharing one Supabase Postgres and each with its **own local Redis**:

- **Phone** — the builder and the **sole ingestion + serving origin**.
- **Shield** (NVIDIA Shield TV, 3 GB RAM) — **serve-only** (no Celery
  worker/beat). It drops off WiFi when idle, so it is not relied on for
  ingestion.

| Component | Address | Managed by |
|-----------|---------|------------|
| Redis | `127.0.0.1:6379` (password in `.env`) | watchdog |
| FastAPI (`core.api_fast:app`) | `127.0.0.1:5001` | watchdog (setsid) |
| Astro frontend (`web/dist/server/entry.mjs`) | `127.0.0.1:3000` | watchdog (setsid) |
| Celery worker / beat | n/a | watchdog (phone only) |
| Cloudflare tunnel (`presek.mk`) | public | watchdog (setsid) |

The watchdog (`/root/scripts/presek_watchdog.sh`) runs tmux-free via `setsid`.
On the Shield, worker/beat spawns are guarded by `PRESEK_SERVE_ONLY` (default
`1` = serve-only). On the phone, FastAPI runs `--workers 2` (override with
`UVICORN_WORKERS`); the Shield stays at `1`.

## Supervisor

`/root/scripts/presek_watchdog.sh` runs detached and, every 30s:

1. starts Redis if it is not answering `PING`;
2. checks FastAPI `/api/health` and Astro on `:3000`, respawning them if down;
3. verifies the Celery worker/beat processes and the tunnel, respawning if absent;
4. every 120s, launches the deploy poller (see below).

It is singleton-guarded via `/root/presek/logs/presek_watchdog.pid`. It is started
on boot by `/root/.termux/boot/startup.sh` and re-launched by `/root/scripts/autorun.sh`
if it dies.

## Auto-deploy

`/root/scripts/presek_deploy.sh` tracks the currently checked-out branch
(`simplify/mk-only-minimal-ai`). On each poll it:

1. `git fetch origin <branch>`;
2. fast-forwards **only** when the working tree is clean and the branch has not
   diverged (local edits are never clobbered);
3. runs `uv sync` when `uv.lock`/`pyproject.toml` changed;
4. runs `alembic upgrade head` when `migrations/` changed;
5. runs `npm ci` and rebuilds Astro when `web/` changed;
6. kills the affected tmux windows so the watchdog respawns them.

Because the watchdog, not the poller, restarts services, deploys are defined as
"code is in place"; process restarts happen on the supervisor's next pass.

## Operations

```bash
# status
pgrep -af 'presek_watchdog.sh'
curl -s http://127.0.0.1:5001/api/health
curl -s -o /dev/null -w 'public %{http_code}\n' https://presek.mk/

# logs
tail -f /root/presek/logs/watchdog.log
tail -f /root/presek/logs/deploy.log
tail -f /root/presek/logs/fastapi.log

# stop / start production (kill the supervisor first or it will restart things)
kill "$(cat /root/presek/logs/presek_watchdog.pid)"
setsid /root/scripts/presek_watchdog.sh </dev/null >>/root/presek/logs/watchdog.out 2>&1 &

# force a deploy check now
bash /root/scripts/presek_deploy.sh
```

CI cannot reach this host (no inbound SSH), so deploys are driven by the poller
above rather than the `deploy` job in `.github/workflows/ci-cd.yml`.

## Edge caching (Cloudflare)

Full HTML is server-rendered (`output: 'server'`), so Cloudflare is used as the
edge cache to keep the flaky Android origins out of the hot path.

- Cache Rules (zone `presek.mk`, ruleset "static edge cache"): `/_astro/*` 1y
  immutable; stable routes (`/archive`, `/tema/*`, `/subjekt/*`, `/izvori`,
  legal pages, `/stats`) 300s; other SSR HTML 60s. `/admin` and `/api/*` are
  never cached.
- `web/src/middleware.ts` sets `Cache-Control: public, max-age=0,
  stale-while-revalidate=300, stale-if-error=86400` on cacheable HTML.
  **Do not add `s-maxage`**: in Cloudflare it implies `proxy-revalidate` and
  disables stale-while-revalidate / stale-if-error. Edge TTL is set by the
  Cache Rules instead.

## Alerting

The phone watchdog pushes **ntfy** alerts (topic `presek-alerts-09c4417ba2ed`)
on state changes only:

- public site down (2 consecutive non-200 checks) / recovered;
- content freshness stale (5 consecutive checks against the **local**
  `/api/health`, which the public response trims) / recovered — this is the
  ingestion-stall signal.

This replaces the old detached `scripts/shield_watch_phone.sh`, which died
silently on 2026-09-26.

## Backups

The **phone** runs the authoritative backup daily (guarded inside the watchdog,
`deploy/backup_postgres.sh`), writing gzipped dumps to
`/root/presek/shared/backups/` (kept 7 days) and then `sync_backups_offsite.sh`.
Offsite R2 sync is skipped until `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`
are set in `.env`. The Shield also has a `presek-backupd` runit service but is
not relied on (WiFi power-save drops it).

## Shield serve-only & ingestion failover

The Shield's watchdog defaults to serve-only: it supervises Redis, FastAPI,
Astro and the tunnel but **not** Celery worker/beat. Note its watchdog guards
with `flock` on `presek_watchdog_v2.lock`; `ensure_redis` starts redis with fd 8
closed so the daemon cannot leak the lock (a leaked lock blocks any new
watchdog).

To fail ingestion over to the Shield (e.g. the phone is down):

```bash
# On the Shield (inside its Debian proot):
# 1. edit /root/scripts/presek_watchdog.sh and set PRESEK_SERVE_ONLY=0
#    (or export it before launching), then:
pkill -f 'scripts/presek[_]watchdog.sh'
setsid /root/scripts/presek_watchdog.sh </dev/null >>/root/presek/logs/watchdog.out 2>&1 &
# 2. confirm worker+beat appear:
pgrep -af 'celery -A core[.]celery_app'
```

Kill watchdogs by pattern (their pidfile is unreliable under proot). Re-enable
serve-only by restoring the guard and repeating the restart.

