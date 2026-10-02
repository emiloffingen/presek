# host/ — Termux fleet operational scripts

These are **host-side** operational scripts for the Presek deployment
(phone = builder/ingestion + standby origin; NVIDIA Shield = primary origin).
They are snapshots of files that live outside the repo at runtime; editing the
running copies does not update this directory.

| File | Runs on | Purpose |
| --- | --- | --- |
| `presek_watchdog.sh` | phone (`/root/scripts/`) | Supervises Redis, FastAPI, Astro, Celery worker/beat and `cloudflared`. Also implements: Shield-primary / phone-standby connector gating, fingerprint-based dist sync to the Shield, per-build standby refresh, and invoking the Shield keep-awake keeper. |
| `presek_watchdog.shield.sh` | Shield (`/root/scripts/presek_watchdog.sh` inside proot) | Same supervisor, serve-only variant (`PRESEK_SERVE_ONLY=1` by default, no Celery worker/beat). Runs Astro with `NODE_ENV=production` and `--max-old-space-size=384`. |
| `shield_keepawake_phone.sh` | phone (`/root/scripts/`) | Re-applies the Shield's never-sleep power policy over adb (shell uid) every ~5 min, wakes it if asleep, and runs `am kill-all` every 15 min. |
| `shield_adb.py` | phone (`/root/shield-adb/`) | Minimal pure-python adb-shell client (`adb_shell` + `CryptographySigner`, key `/root/.android/adbkey`). |
| `warmup_run` | Shield runit service `presek-warmup` (`/data/data/com.termux/files/usr/var/service/presek-warmup/run`) | Pings `http://127.0.0.1:3000/` and `:5001/api/health` every 30 s to keep the SSR process/JIT warm. |

## Secrets

`REDIS_PASS` is **not** stored in these files. It is taken from the
`PRESEK_REDIS_PASS` environment variable, or derived from the app `.env`
(`REDIS_URL`) as a fallback. The real `.env` is gitignored.

## Notes

- Runtime paths differ from the repo: the phone reads `/root/scripts/*`; the
  Shield's copies live inside the proot Debian rootfs.
- The phone's auto-deploy poller only cares about tracked changes; this
  directory is inert data for the app.
