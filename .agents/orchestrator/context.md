# Context Information

## Environment
- OS: Linux
- Workspace: `/home/emiloffingen/presek`
- Principal framework: FastAPI (Backend), Astro (Frontend)
- Database: PostgreSQL (configured in core/database.py)
- Metrics: Prometheus (`prometheus_client` used in core/api_fast.py)

## Target Files
- Astro page: `/home/emiloffingen/presek/web/src/pages/cluster/[slug].astro`
- API file: `/home/emiloffingen/presek/core/api_fast.py`
- Verification script location: `/home/emiloffingen/presek/scripts/verify_backup.py` or `.sh`

## Active Tasks / Subagents
- Heartbeat cron: `task-17`
- E2E Testing Track: Not started
- Implementation Track: Not started
