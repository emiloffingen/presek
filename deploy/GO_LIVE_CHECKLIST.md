# Presek go-live checklist

## 1. Pre-flight

Run from the repo root on the production server:

```sh
cd /home/emiloffingen/presek
grep -E '^(DATABASE_URL|REDIS_URL|SECRET_KEY|PRESEK_ADMIN_TOKEN)=' .env
test -f web/dist/server/entry.mjs && echo astro-build-ok
test -d venv && echo venv-ok
```

Confirm:

- `.env` contains `DATABASE_URL`
- `.env` contains `REDIS_URL`
- `.env` contains `SECRET_KEY`
- `.env` contains `PRESEK_ADMIN_TOKEN`
- Astro server build exists
- Python virtualenv exists

## 2. Smoke test before release

```sh
bash deploy/smoke_check.sh
```

This now checks:

- Flask health returns `200`
- Flask health reports `database.ok = true`
- Flask health reports `redis.ok = true`
- Astro responds successfully
- FastAPI health returns `200`
- FastAPI health reports `database.ok = true`
- FastAPI health reports `redis.ok = true`
- Public site responds successfully

## 3. Deploy

```sh
bash deploy/deploy_release.sh
```

## 4. Service verification

```sh
sudo systemctl status presek.target --no-pager
sudo journalctl -u presek-web.service -n 50 --no-pager
sudo journalctl -u presek-astro.service -n 50 --no-pager
sudo journalctl -u presek-fastapi.service -n 50 --no-pager
sudo journalctl -u presek-worker.service -n 50 --no-pager
sudo journalctl -u presek-beat.service -n 50 --no-pager
```

Confirm:

- no service is in a failed state
- no repeating startup crashes
- no DB or Redis connection errors
- no import/runtime tracebacks

## 5. Manual live verification

Open and verify:

- `https://presek.live/status`
- `https://presek.live/`
- one `https://presek.live/cluster/...` page
- `https://presek.live/archive`

Confirm:

- `/status` shows `DB OK` and `Redis OK`
- freshness is not stale
- homepage renders articles and images
- one cluster page loads fully
- `Прашај го Пресек` answers successfully
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
bash deploy/rollback_release.sh
```

Then rerun:

```sh
bash deploy/smoke_check.sh
sudo systemctl status presek.target --no-pager
```
