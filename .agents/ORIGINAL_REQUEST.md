# Original User Request

## 2026-06-29T13:13:44Z

This project implements three high-value operational enhancements for Presek: Interactive Stance Visualizations, a CSP script violation telemetry endpoint, and automated daily backup verification.

Working directory: /home/emiloffingen/presek
Integrity mode: development

## Requirements

### R1. Interactive Stance Visualizations
Expose cluster narrative perspectives visually on the cluster details page (web/src/pages/cluster/[slug].astro). Extract the `narrative_diversity` and perspectives keys from the cluster payload and render them using custom visual elements (e.g. distribution bars, color-coded stance gradients). Use rich aesthetics (vanilla CSS HSL palettes, glassmorphism, micro-animations) matching the existing site design.

### R2. Content Security Policy (CSP) Telemetry Endpoint
Implement a FastAPI endpoint `/api/csp-report` (in core/api_fast.py or a dedicated router) that accepts POST requests with Content-Type `application/csp-report` (or fallback JSON). It must parse the standard browser CSP violation payload (containing `blocked-uri`, `violated-directive`, etc.) and log the incident securely. Ensure the endpoint is exempt from rate limits and CSRF verification.

### R3. Automated Backup Verification script
Create an operations automation script (`scripts/verify_backup.sh` or `.py`) that imports a PostgreSQL database snapshot into a sandboxed test database instance, verifies the presence of key tables (e.g. `articles`, `clusters`), and reports the verification status (1 for success, 0 for failure) and backup size to Prometheus. Add appropriate metrics fields for this status in core/api_fast.py.

## Acceptance Criteria

### Interactive Stance Visualizations UI
- [ ] Stance visual widget renders on cluster details page when cluster has narrative perspectives.
- [ ] CSS uses styled HSL variable tokens, subtle borders, and smooth transitions matching the theme.

### CSP Telemetry API
- [ ] POST `/api/csp-report` is reachable and returns HTTP 200/204 upon receiving valid browser CSP payloads.
- [ ] Endpoint has security headers and bypasses CSRF check to receive standard browser reporting.
- [ ] Integration tests in `tests/` check the endpoint and verify correct parsing.

### Backup Verification Operations
- [ ] Verification script successfully restores a database snapshot in a sandboxed environment.
- [ ] Verification status and snapshot metrics are exposed on the Prometheus `/metrics` endpoint.
