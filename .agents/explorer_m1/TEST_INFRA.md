# Presek Operational Enhancements: E2E Test Infrastructure & Design

This document details the test infrastructure, execution model, database environments, and E2E test plan for the Presek platform operational enhancements.

---

## 1. Test Architecture & Execution

The Presek test suite is divided into two primary runtimes: Python backend tests (Pytest) and Web frontend tests (Cypress).

### 1.1 Python Backend Tests
All backend tests are run using the project's virtual environment python package.
- **Test Runner**: `pytest`
- **Virtual Environment Path**: `/home/emiloffingen/presek/.venv/bin/pytest`
- **Default Config**: `/home/emiloffingen/presek/pytest.ini`

**Command to run all tests:**
```bash
.venv/bin/pytest
```

**Command to run a specific test suite:**
```bash
.venv/bin/pytest tests/test_health.py
```

### 1.2 Frontend E2E & Component Tests
The Astro-based web frontend uses Cypress for end-to-end user flow verification.
- **Workspace Directory**: `/home/emiloffingen/presek/web`
- **Test Command (Headless E2E)**: `npm run test:e2e` (runs `cypress run --e2e`)
- **Test Command (Interactive UI)**: `npm run test:e2e:ui` (runs `cypress open --e2e`)

---

## 2. Environment Variables & Database Configuration

During test execution, specific environment overrides ensure isolation and prevent mutation of production databases.

### 2.1 Default Python Test Environment Variables
As defined in `tests/conftest.py`, the following environment variables are set during python tests:
- `SECRET_KEY`: `test-secret-key`
- `CSRF_TOKEN_SECRET`: `test-csrf-secret`
- `DATABASE_URL`: `postgresql://presek:presek_pass_2026@localhost/presek_test`
- `DATABASE_READ_REPLICA_URL`: `postgresql://presek:presek_pass_2026@localhost/presek_test`
- `PRESEK_SKIP_DB_POOL_INIT`: `1` (prevents premature connection pool initialization)
- `PRESEK_DISABLE_SEMANTIC_NER`: `1` (bypasses heavy NLP processes)
- `PRESEK_DISABLE_KEYBERT`: `1`
- `PRESEK_DISABLE_SPACY`: `1`

### 2.2 Cypress Web Environment Variables
Cypress E2E tests target the local Astro development server:
- `baseUrl`: `http://localhost:3000`
- Host header configuration mimics production setups (`presek.live` or `presek.mk`).

---

## 3. E2E Test Suite Design (Tiers 1–4)

This test plan defines **38 test cases** distributed across the three major operational requirements:
- **R1**: Interactive Stance UI
- **R2**: CSP Telemetry API
- **R3**: Backup Verification

Tests are structured across four progressive verification tiers:
- **Tier 1 (Unit & Smoke)**: 15 test cases
- **Tier 2 (Integration & Functional)**: 15 test cases
- **Tier 3 (System & E2E Flow)**: 3 test cases
- **Tier 4 (Adversarial & Failure)**: 5 test cases

---

### Tier 1: Unit & Smoke Tests (15 Test Cases)

| Test Case ID | Feature | Description | Verification Method |
|---|---|---|---|
| **TEST-R1-T1-01** | R1 | Verify TypeScript contract interfaces in `web/src/types.ts` for `ClusterDetail.narrative_diversity` and `ClusterDetail.perspectives`. | Run compilation check (`npm run lint`). |
| **TEST-R1-T1-02** | R1 | Test `normalizePerspective` helper with citation markers in content (e.g. `[1]`). | Unit test checking that citation markers are removed. |
| **TEST-R1-T1-03** | R1 | Test `normalizePerspective` helper with standard consensus inputs. | Assert string returns the translated consensus text from translations map. |
| **TEST-R1-T1-04** | R1 | Test `normalizePerspective` helper with open issue keyword inputs. | Assert string returns translated open stance info text. |
| **TEST-R1-T1-05** | R1 | Test `normalizePerspective` filtration of empty or malformed inputs. | Assert helper excludes invalid objects from final array. |
| **TEST-R1-T1-06** | R1 | Test `clampPercent` utility function for out-of-bound percentages. | Verify inputs `< 0` yield `0`, `> 100` yield `100`, and decimals are rounded. |
| **TEST-R1-T1-07** | R1 | Test `hasMetric` check with non-finite values (NaN, infinity, null). | Assert returns false for invalid numeric scores. |
| **TEST-R2-T1-08** | R2 | Validate Pydantic schema validation for the `CSPReport` request body. | Unit test passing valid JSON W3C format payload to `CSPReport.model_validate()`. |
| **TEST-R2-T1-09** | R2 | Validate Pydantic schema validation of optional keys in `CSPReport`. | Ensure model initializes successfully when optional keys are absent. |
| **TEST-R2-T1-10** | R2 | Test URL parser pattern matching for CSP report fields. | Verify malformed/invalid URLs are flagged as invalid. |
| **TEST-R3-T1-11** | R3 | Validate `presek_backup_verification_status` Gauge registry definition. | Assert gauge is successfully initialized in Prometheus registry. |
| **TEST-R3-T1-12** | R3 | Validate `presek_backup_size_bytes` Gauge registry definition. | Assert gauge is successfully initialized in Prometheus registry. |
| **TEST-R3-T1-13** | R3 | Test local file size utility function in backup script. | Assert correct byte size is returned for mock archive files. |
| **TEST-R3-T1-14** | R3 | Test backup verification status failure helper function. | Verify helper correctly maps fail code to failure status payload. |
| **TEST-R3-T1-15** | R3 | Test Prometheus client generation endpoint exporter helper. | Assert metrics are correctly generated into string format. |

---

### Tier 2: Integration & Functional Tests (15 Test Cases)

| Test Case ID | Feature | Description | Verification Method |
|---|---|---|---|
| **TEST-R1-T2-01** | R1 | Verify FastAPI route GET `/api/cluster/{id}` provides correct `narrative_diversity` and `perspectives` keys. | Fast API TestClient request and JSON payload schema assert. |
| **TEST-R1-T2-02** | R1 | Verify Astro component rendering fallback when narrative diversity payload is missing. | Verify component renders graceful fallback warning or is skipped cleanly. |
| **TEST-R1-T2-03** | R1 | Verify language localization on cluster route with query `?lang=sr`. | Assert page loads Serbian labels (`Izvori`, `Objektivnost`). |
| **TEST-R1-T2-04** | R1 | Verify language localization on cluster route with query `?lang=mk`. | Assert page loads Macedonian labels (`Извори`, `Објективност`). |
| **TEST-R1-T2-05** | R1 | Verify mapping of tone analysis metrics from DB row to API JSON representation. | Assert objectivity, sensationalism and emotional charge values match database seed. |
| **TEST-R2-T2-06** | R2 | Verify POST `/api/csp-report` returns HTTP 200/204 on valid payload. | Fast API TestClient request assertion. |
| **TEST-R2-T2-07** | R2 | Verify POST `/api/csp-report` supports both `application/json` and `application/csp-report` Content-Type headers. | Run HTTP client requests with varying headers. |
| **TEST-R2-T2-08** | R2 | Verify POST `/api/csp-report` bypasses CSRF checks. | Run POST request without `X-CSRF-Token` cookie or header; assert success. |
| **TEST-R2-T2-09** | R2 | Verify POST `/api/csp-report` bypasses API rate limits. | Send 50 sequential requests in rapid succession; assert zero 429 errors. |
| **TEST-R2-T2-10** | R2 | Verify telemetry reports are written to the telemetry logs directory. | Assert file `/home/emiloffingen/presek/logs/csp_telemetry.log` is updated. |
| **TEST-R3-T2-11** | R3 | Verify `verify_backup.py` / `.sh` script execution on a valid backup file. | Execute script targeting a valid SQL dump; assert exit code is 0. |
| **TEST-R3-T2-12** | R3 | Verify script execution on a corrupted/invalid archive file. | Target mock corrupted dump; assert exit code is non-zero (1). |
| **TEST-R3-T2-13** | R3 | Verify backup verification script execution updates the Prometheus metrics. | Run script, scrape metrics, and assert gauge status matches results. |
| **TEST-R3-T2-14** | R3 | Verify `GET /metrics` response contains operational metrics when scraped from localhost. | Scrape using loopback IP; assert metrics presence. |
| **TEST-R3-T2-15** | R3 | Verify `GET /metrics` blocks remote non-local scrapers. | Set request client IP to external domain; assert response is HTTP 403 Forbidden. |

---

### Tier 3: System & E2E Flow Tests (3 Test Cases)

| Test Case ID | Feature | Description | Verification Method |
|---|---|---|---|
| **TEST-R1-T3-01** | R1 | E2E Cypress user flow on cluster page detail. Loads details page and asserts that Stance gauge indicator pin has CSS styling matching the pluralism score. | Run `npm run test:e2e`. Asserts pin position is calculated correctly on screen. |
| **TEST-R2-T3-02** | R2 | Full telemetry transmission flow. Mock page triggers CSP violation, browser executes telemetry callback POST to backend, verify it is successfully logged. | Cypress E2E flow capturing network callback and asserting log output. |
| **TEST-R3-T3-03** | R3 | End-to-end backup verification pipeline execution. Restores snapshot to sandbox, performs database query checks, updates Prometheus gauges, and scrapes `/metrics`. | Run automated system shell script and scrape metrics to assert final update. |

---

### Tier 4: Adversarial & Failure Tests (5 Test Cases)

| Test Case ID | Feature | Description | Verification Method |
|---|---|---|---|
| **TEST-R1-T4-01** | R1 | Cross-Site Scripting (XSS) prevention on perspective visualizer. Inject script elements into perspectives fields. | Cypress E2E test verifying that script tags are sanitized and not evaluated by browser. |
| **TEST-R1-T4-02** | R1 | Responsive viewport check. Simulate responsive viewport adjustments. | Verify CSS grid collapses correctly under mobile vs. desktop configurations. |
| **TEST-R2-T4-03** | R2 | Malformed and oversized payload attack. Send massive JSON payloads (e.g. 5MB) or deep nested objects to `/api/csp-report`. | Assert API safely drops connection or responds with HTTP 413/422 without panicking. |
| **TEST-R3-T4-04** | R3 | Database offline recovery. Verify backup verification script exits gracefully when PostgreSQL is down. | Mock DB connection timeout; verify script outputs exit code 1 and updates gauge to 0. |
| **TEST-R3-T4-05** | R3 | Missing secrets error handling. Run verification script on encrypted backup without `BACKUP_PASSPHRASE`. | Assert script fails with specific passphrase error log and gauge status set to 0. |
