# Handoff Report: Presek E2E Test Suite Design (M1)

## 1. Observation

During exploration, the following files and structural configurations were observed:

- **Root Project Contracts**: `PROJECT.md` specifies three core milestones:
  - **Milestone 2 (R1)**: Interactive Stance Visualizations rendering `narrative_diversity` and `perspectives` in `web/src/pages/cluster/[slug].astro`.
  - **Milestone 3 (R2)**: CSP Telemetry API (`POST /api/csp-report`).
  - **Milestone 4 (R3)**: Backup Verification script and Prometheus metrics.
- **Python Test Configuration**:
  - Test runner is configured via `pytest.ini`:
    ```ini
    [pytest]
    asyncio_mode = auto
    asyncio_default_fixture_loop_scope = function
    pythonpath = .
    testpaths = tests
    timeout = 60
    timeout_method = thread
    ```
  - Standard test suite contains **898 tests** successfully executed using the local virtual environment:
    - Executing Command: `.venv/bin/pytest`
    - Result: `897 passed, 1 skipped, 1 warning in 20.69s` (e.g. testing `tests/test_health.py` and unit files).
  - Environment variables set in `tests/conftest.py` default to:
    ```python
    os.environ.setdefault("DATABASE_URL", "postgresql://presek:presek_test@localhost/presek_test")
    ```
- **Web Frontend Structure**:
  - Main Astro page detail page: `web/src/pages/cluster/[slug].astro`.
  - Stance details component: `web/src/components/Cluster/CredibilityAnalysis.astro` which already accepts `pluralismScore` and `perspectives` props.
  - Cypress E2E framework is installed in the frontend package:
    - Config file: `web/cypress.config.ts` (configured to target local server at `http://localhost:3000`).
    - Existing Cypress tests: `web/cypress/e2e/smoke.cy.ts` (runs `cy.visit('/')` and verifies element visibility).
    - Executing Command: `npm run test:e2e` inside `/home/emiloffingen/presek/web`.

---

## 2. Logic Chain

1. **Test Environment Choice**: Since python unit and integration tests are already executed successfully via pytest inside the virtual environment (`.venv/bin/pytest`), new backend tests (Tiers 1, 2, 4) for R2 and R3 must be implemented inside the `tests/` directory as standard python tests.
2. **Frontend E2E Choice**: Since Cypress is configured in `web/` and runs against a local server (`http://localhost:3000`), E2E UI flow tests (Tier 3) for R1 and R2 must be implemented in the `web/cypress/e2e/` folder.
3. **Metric Scraping Verification**: The endpoint `/api/metrics` is exposed in `core/api_fast.py` and restricted to trusted clients using `_is_local_metrics_client(request)`. Therefore, test cases must verify both permission checks (local vs. remote) and metric inclusion.
4. **Test Target Allocation**: To verify requirements comprehensively across 4 distinct Tiers, the E2E test plan assigns 38 test cases with:
   - Unit level coverage (Tier 1) for mock helpers, regexes, and model schemas.
   - Route and script execution level (Tier 2) for API queries, bypass rules, and script exits.
   - Complete browser flow and tool pipeline execution (Tier 3).
   - Security sanitization, network bypass, and resilience checks (Tier 4).

---

## 3. Caveats

- **Mock dependency**: The CSP Report Telemetry API (`POST /api/csp-report`) and backup verification script (`scripts/verify_backup.py`) are planned features not yet fully implemented in the current codebase state. The test designs are based on their interface contracts in `PROJECT.md` and `deploy/verify_backup.sh`.
- **Sandbox DB**: E2E tests for backup verification (Tier 3) assume the existence of a PostgreSQL sandbox/test instance configured via `DATABASE_URL`. Testing this in headless CI will require a local postgres instance.

---

## 4. Conclusion

The testing infrastructure is fully operational and has been mapped to support the 3 upcoming operational enhancements. A comprehensive **38-case test design** (15 Tier 1, 15 Tier 2, 3 Tier 3, 5 Tier 4) has been successfully drafted and saved to `TEST_INFRA.md`.

---

## 5. Verification Method

To verify the test design and current test infrastructure:
1. Validate that `TEST_INFRA.md` is present at `/home/emiloffingen/presek/.agents/explorer_m1/TEST_INFRA.md`.
2. Verify existing test execution works by running:
   ```bash
   .venv/bin/pytest tests/test_health.py
   ```
3. Verify that `web/cypress.config.ts` is syntactically valid and configuration references the expected local baseUrl.

---

## 6. Remaining Work

The next agent (Implementer/Tester) needs to:
1. Create new python test files in `tests/` (e.g. `tests/test_csp_telemetry.py` and `tests/test_backup_verification.py`) implementing the Tier 1, 2, and 4 test cases.
2. Create new Cypress specifications in `web/cypress/e2e/` (e.g. `web/cypress/e2e/stance_ui.cy.ts` and `web/cypress/e2e/csp_violations.cy.ts`) implementing Tier 3 test cases.
3. Validate and integrate the E2E test run output to publish `TEST_READY.md`.
