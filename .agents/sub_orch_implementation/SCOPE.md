# Scope: Implementation Track

## Architecture
- **Interactive Stance Visualizations UI**: Extract `narrative_diversity` and `perspectives` keys from the cluster payload on `/web/src/pages/cluster/[slug].astro` and render custom distribution bars/stance gradients with glassmorphism/HSL styling.
- **CSP Telemetry API**: Implement FastAPI endpoint POST `/api/csp-report` in `core/api_fast.py` (or a router), bypassing CSRF/Rate Limiting, parsing and logging CSP browser violation payload.
- **Backup Verification Operations**: Implement `scripts/verify_backup.py` / `.sh` to restore database snapshot in sandbox, check tables (`articles`, `clusters`), and expose `presek_backup_verification_status` and `presek_backup_size_bytes` on the Prometheus metrics endpoint in `core/api_fast.py`.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| R1 | Interactive Stance UI | Extract and render narrative perspective widget in Astro | None | PLANNED |
| R2 | CSP Telemetry API | POST /api/csp-report endpoint, security headers, rate limit/CSRF bypass, unit/integration tests | None | PLANNED |
| R3 | Backup Verification | Database restoration sandbox script, Prometheus metrics exposure | None | PLANNED |
| Phase1 | E2E Test Pass (Tiers 1-4) | Poll for TEST_READY.md and pass E2E tests | R1, R2, R3 | PLANNED |
| Phase2 | Adversarial Hardening (Tier 5) | Challenger-led white-box testing and vulnerability resolution | Phase1 | PLANNED |

## Interface Contracts

### R1. Web Cluster Page Interface
- **Payload keys**: `narrative_diversity` (expected layout: `{"verdict": str, "score": float}`), `perspectives` (expected layout: `list[dict]` with `angle`, `content` keys).
- **Styling**: Vanilla CSS HSL variables, glassmorphism (`backdrop-filter`), smooth transitions.

### R2. CSP Report API Interface
- **Endpoint**: POST `/api/csp-report`
- **Payload format**: Standard CSP report JSON containing `csp-report` dictionary.
- **Bypasses**: Rate limit, CSRF. Returns HTTP 200/204.

### R3. Backup Verification Metrics
- **Prometheus Gauges**:
  - `presek_backup_verification_status` (1 for success, 0 for failure)
  - `presek_backup_size_bytes` (Backup file size in bytes)
