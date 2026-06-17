# Presek Audit Remediation Plan

**Created:** 2026-06-17  
**Status:** In progress — critical and high-priority fixes implemented in this pass.

## Summary

Full application audit covering FastAPI backend, Astro frontend, deployment/ops, dependencies, and tests. This document tracks remediation status and recommended follow-up.

---

## Critical (P0) — Fix immediately

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| 1 | Newsletter unsubscribe without signed token | **Fixed** | HMAC tokens via `core/signed_tokens.py`; `GET ?token=` only |
| 2 | Unauthenticated expensive compute endpoints | **Fixed** | Rate limits on analyst + briefing/audio; paths in limiter set |
| 3 | Rate limiting fails open when Redis down | **Fixed** | Fail-closed in `ENV=production` |
| 4 | Redis silent fallback to unauthenticated localhost | **Fixed** | Fail-fast in production |
| 5 | XSS in `highlightFactText` | **Fixed** | `sanitizeHtml()` after highlight |
| 6 | DOM XSS in entity tooltips | **Fixed** | DOM APIs + `textContent` |
| 7 | Wrong MK cluster canonical URLs | **Fixed** | `buildCanonicalUrl` + `siteOrigin(lang)` |
| 8 | Dependency CVEs (starlette, aiohttp, astro) | **Fixed** | Version bumps in `pyproject.toml` / `package.json` |

## High (P1) — This week

| # | Issue | Status | Notes |
|---|-------|--------|-------|
| 9 | Delivery tracking unauthenticated writes | **Fixed** | HMAC-signed `token` param |
| 10 | Public `/api/health` leaks ops intel | **Fixed** | Detailed fields localhost-only |
| 11 | CSRF cookie/header mismatch | **Fixed** | Double-submit validation |
| 12 | Service imports router | **Fixed** | `core/research_helpers.py` |
| 13 | No HTTP integration tests | **Partial** | `tests/test_security_integration.py` added |
| 14 | Input validation gaps | **Fixed** | `cluster_research`, `entity_graph_lookup` |
| 15 | GA before consent | **Fixed** | Consent Mode v2 default denied |
| 16 | Heavy header `client:load` | **Fixed** | `SearchIsland` → `client:idle` |
| 17 | `astro check` errors | **Partial** | Layout + cluster fixes; remaining tracked |
| 18 | Backups unencrypted by default | **Fixed** | `REQUIRE_BACKUP_ENCRYPTION=1` in prod crontab |
| 19 | Nginx rate-limit zones on SSL install | **Fixed** | Zones in `presek.live.conf` + install script |
| 20 | Bootstrap seeds prod from dev `.env` | **Fixed** | Refuses non-production source |
| 21 | CI actions unpinned | **Fixed** | Pinned to version tags |

## Medium (P2) — This month

| # | Issue | Status |
|---|-------|--------|
| 22 | Duplicate `/api/health` contracts | Open — consolidate router vs app |
| 23 | Inconsistent error handling | Open |
| 24 | `saved_insights` admin label as user_id | Open |
| 25 | f-string SQL pattern | Open — audit-only |
| 26 | Alembic without ORM models | Open — by design |
| 27 | Global font payload | Open |
| 28 | `Layout.astro` monolith | Open |
| 29 | SW caches `/api/*` | Open |
| 30 | a11y CI (axe/pa11y) | Open |
| 31 | Stale deploy docs (service names) | **Fixed** |
| 32 | `shared/.env` permissions | **Fixed** | `chmod 600` in bootstrap |
| 33 | Single uvicorn worker | Open — ops decision |
| 34 | No offsite backup cron | Open |
| 35 | Rollback vs migrations | Open — documented |

## Low (P3)

- Hardcoded deploy paths in `api_fast.py`
- Duplicate `/api` + `/api/v1` mounting
- Legacy `DBWrapper`
- Thin E2E coverage
- `production_deploy.sh` deprecation

---

## Recommended fix order (remaining)

1. Add more `TestClient` integration tests (CSRF POST routes, CORS)
2. Resolve remaining `astro check` errors in TopicPage components
3. Increase uvicorn workers or dual API upstream
4. Offsite backup cron + quarterly restore drill
5. Font subsetting per locale
6. CSP refactor for Astro inline scripts

---

## Test commands

```sh
.venv/bin/python3 -m pytest -q tests/test_signed_tokens.py tests/test_security_integration.py
cd web && npm test && npm run lint
```

## Deploy after merge

1. `uv lock` + redeploy API venv
2. `cd web && npm install && npm run build`
3. If nginx changed: `sudo bash deploy/install_server.sh`
4. `APP_ROOT=... bash deploy/ci_deploy.sh`
