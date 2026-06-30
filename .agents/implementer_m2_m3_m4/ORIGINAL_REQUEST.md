## 2026-06-29T11:19:09Z
You are dispatched to implement the E2E Test Suite (Tiers 1-4) for Presek.
Your identity:
- Archetype: teamwork_preview_worker
- Role: Test Implementer
- Working directory: /home/emiloffingen/presek/.agents/implementer_m2_m3_m4/

Tasks:
1. Create your working directory (/home/emiloffingen/presek/.agents/implementer_m2_m3_m4/) if it doesn't exist.
2. Read the E2E Test design in `/home/emiloffingen/presek/.agents/explorer_m1/TEST_INFRA.md`.
3. Create `/home/emiloffingen/presek/TEST_INFRA.md` containing the E2E test design.
4. Check the current status of implementation of the 3 features (R1: Interactive Stance UI, R2: CSP Telemetry API, R3: Backup Verification).
5. Implement the 38 test cases across Tiers 1-4. Write Python integration/unit tests in tests/ (e.g., tests/test_csp_telemetry.py, tests/test_backup_verification.py, tests/test_stance_ui.py) and Cypress E2E tests in web/cypress/e2e/ (e.g., web/cypress/e2e/stance_ui.cy.ts). Ensure that tests are robust, using mocks where features are not fully implemented or targeting the expected code contracts (e.g. mock DB/request/responses).
6. Run the test runner command for Python backend tests (`.venv/bin/pytest`) and Web frontend tests (Cypress) to verify the new tests run and compile correctly.
7. Stage, commit, and push your changes to GitHub as required by user memories.
8. Document all implemented tests, code paths, test run results, and verification commands in your handoff report (/home/emiloffingen/presek/.agents/implementer_m2_m3_m4/handoff.md).
9. Message the parent with a summary of implemented test files and execution logs.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
