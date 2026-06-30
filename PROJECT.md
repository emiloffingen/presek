# Project: Presek Operational Enhancements

## Architecture
- **Web Frontend**: Astro-based page rendering (`web/src/pages/cluster/[slug].astro`). Extracts cluster payload keys `narrative_diversity` and `perspectives`, rendering them with Astro components and CSS.
- **FastAPI Core**: `core/api_fast.py` exposing REST endpoints and Prometheus metrics.
- **CSP API**: A new endpoint `/api/csp-report` that bypasses CSRF and Rate Limiting.
- **Prometheus Metrics**: Exposes backup verification metrics (`presek_backup_verification_status` and `presek_backup_size_bytes`) on the `/metrics` endpoint.
- **Operations Script**: `scripts/verify_backup.py` / `.sh` restoring snapshot to sandbox DB, checking key tables, and reporting metrics.

## Code Layout
- `web/src/pages/cluster/[slug].astro` - Cluster detail UI page.
- `core/api_fast.py` - Core API setup, metrics registration, telemetry endpoints.
- `scripts/verify_backup.py` or `scripts/verify_backup.sh` - Database restoration and verification script.
- `tests/` - Python integration tests for API endpoints and scripts.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | E2E Testing Track | Define test infra, scenarios, and publish TEST_READY.md | None | PLANNED |
| M2 | Interactive Stance UI | Extract narrative diversity and perspectives; render widgets in Astro | None | PLANNED |
| M3 | CSP Telemetry API | Implement /api/csp-report in FastAPI; add integration tests | None | PLANNED |
| M4 | Backup Verification | Implement backup verification script and Prometheus metrics | None | PLANNED |
| M5 | E2E & Adversarial Hardening | Run all E2E tests, resolve failures, and perform adversarial coverage hardening | M1, M2, M3, M4 | PLANNED |

## Interface Contracts

### Web Cluster API Interface
- **Source**: `routes/news.py` / FastAPI DB Query
- **Payload format**:
  - `narrative_diversity`: `{"verdict": "string", "score": float}` (or similar)
  - `perspectives`: `list[dict]` where dict has `{"angle": "string", "content": "string"}`

### CSP Report Telemetry API
- **Endpoint**: POST `/api/csp-report`
- **Content-Type**: `application/csp-report` or `application/json`
- **Request Body**:
  ```json
  {
    "csp-report": {
      "document-uri": "string",
      "referrer": "string",
      "violated-directive": "string",
      "effective-directive": "string",
      "original-policy": "string",
      "disposition": "string",
      "blocked-uri": "string",
      "line-number": 123,
      "column-number": 456,
      "source-file": "string",
      "status-code": 200,
      "script-sample": "string"
    }
  }
  ```
- **Response**: HTTP 200/204, empty body or simple JSON acknowledgement. Rate limits and CSRF exempt.

### Backup Verification Metrics API
- **Metrics exported**:
  - `presek_backup_verification_status` (Gauge, 1 for success, 0 for failure)
  - `presek_backup_size_bytes` (Gauge, size of the backup file in bytes)
