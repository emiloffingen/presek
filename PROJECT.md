# Project: Presek v8.3.9

Macedonian news aggregation with FastAPI + Astro + Celery.

## Architecture
- **Web Frontend**: Astro SSR in `web/` (`src/pages/index.astro`, `src/pages/mk/index.astro`, `src/pages/cluster/[slug].astro`, `src/components/home/HomePage.astro`). 117 components, bilingual SR/MK, Tailwind 4 + domain CSS (`web/CSS.md`).
- **FastAPI Core**: `core/api_fast.py` exposing REST `/api/*` and Prometheus `/metrics` (`presek_articles_total`, queue depth, DB size, pool stats).
- **Workers**: 8 Celery queues — `celery`, `ingestion`, `ingestion-crawl`, `fast-track`, `synthesis`, `intel-heavy`, `delivery`, `maintenance`. Beat schedules pruning/backfill.
- **Data**: PostgreSQL pgvector (`articles`, `cluster_summaries`) + Redis broker/cache. Health: 23,398 articles, 339.5MB, freshness 0min, queues 0 depth.
- **Synthesis**: AI cascade (gemini3/gemini2/gemini/groq/openrouter/nvidia + extractive fallback). 24h: 737 summaries, 0% fallback. 7d: 5,486 summaries, 0% fallback.

## Code Layout
- `core/api_fast.py` - API setup, metrics, telemetry
- `routes/` - `news.py` (cluster payload incl. `narrative_diversity`, `perspectives`), feeds, stats
- `tasks/` - ingestion, synthesis pipeline/persist, maintenance, delivery
- `nlp/` - local analyst, embeddings (fastembed), heuristics
- `web/src/` - pages, components, layouts (`Layout.astro`), lib, styles
- `web/scripts/` - `lighthouse-homepage.mjs` (budgets: perf ≥90, LCP ≤2500ms, CLS ≤0.10), `a11y-homepage.mjs`, `analyze-bundle.mjs`
- `deploy/` - systemd units (`presek.target`), bootstrap/install/ci scripts
- `tests/` - ~100 backend test modules, `web` uses node --test + Cypress

## Status
- Production: systemd (`presek-fastapi-unified`, `presek-astro`, workers, beat) behind nginx. See `deploy/MINIMUM_PROD.md`.
- Frontend checks: `npm run build` clean, `npm run lint` 0 errors/0 warnings (298 files), bundle 1.70MB total / 176KB client.js within budget.
- Backend: Python >=3.13, uv-managed (`pyproject.toml` + `uv.lock`).

## Proposed (not implemented)
- POST `/api/csp-report` telemetry endpoint + rate-limit/CSRF bypass
- `scripts/verify_backup.py` sandbox restore + `presek_backup_verification_status` / `presek_backup_size_bytes` metrics
- Interactive stance widgets for `narrative_diversity.score` / `perspectives` on cluster page
- `TEST_READY.md` E2E track + adversarial hardening

Implement above before referencing them as architecture.
