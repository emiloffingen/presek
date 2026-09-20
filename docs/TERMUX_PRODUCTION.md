# Termux Production Runbook

`presek.mk` is served from a persistent Termux/Android host. No systemd or nginx
is involved; a shell watchdog supervises everything and a git poller auto-deploys
the checked-out branch.

## Topology

| Component | Address | Managed by |
|-----------|---------|------------|
| Redis | `127.0.0.1:6379` (password in `.env`) | watchdog |
| FastAPI (`core.api_fast:app`) | `127.0.0.1:5001` | tmux window `fastapi` |
| Astro frontend (`web/dist/server/entry.mjs`) | `127.0.0.1:3000` | tmux window `astro` |
| Celery worker / beat | n/a | tmux windows `worker`, `beat` |
| Cloudflare tunnel (`presek.mk`) | public | tmux window `tunnel` |

All service windows live in tmux session `presek`.

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
tmux list-windows -t presek
curl -s http://127.0.0.1:5001/api/health

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

_Last verified: 2026-09-20._
