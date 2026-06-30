# Scope: E2E Testing Track

## Architecture
- Feature R1: Interactive Stance UI (`web/src/pages/cluster/[slug].astro`). Extraction of narrative diversity & perspectives.
- Feature R2: CSP Telemetry API (`core/api_fast.py` endpoint `/api/csp-report`).
- Feature R3: Backup Verification script & Prometheus metrics.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Exploration & Planning | Explore codebase, list existing test setup, design E2E test plan, draft TEST_INFRA.md | None | DONE |
| 2 | R1 (Astro Stance UI) Tests | Implement tests verifying rendering, data extraction, widgets in Astro | M1 | IN_PROGRESS |
| 3 | R2 (CSP Telemetry API) Tests | Implement E2E tests for Feature R2 | M1 | IN_PROGRESS |
| 4 | R3 (Backup Verification) Tests | Implement E2E tests for Feature R3 | M1 | IN_PROGRESS |
| 5 | Execution, Audit, TEST_READY | Run E2E test cases, execute Forensic Auditor, write TEST_READY.md, report back | M2, M3, M4 | PLANNED |

## Interface Contracts
- See PROJECT.md at the project root.
