# Presek Application Audit Report
Date: Thursday, May 14, 2026

## 1. Executive Summary
The Presek application is overall healthy and operational. Core services (API, Frontend, Database, Background Workers) are running as expected. However, critical disk space issues and a high failure rate in news source ingestion require immediate attention.

## 2. Infrastructure & Health
### System Status
- **Disk Usage:** **CRITICAL** (92% used, 4.7GB free on `/`).
- **Memory:** 4.2Gi used of 7.8Gi.
- **Uptime:** 8 days, 15 hours.
- **Services:**
  - `postgresql@16-main`: Running
  - `redis-server`: Running
  - `presek.target` (App stack): All 11 units active.

### Databases
- **PostgreSQL:** Healthy, 4687 articles indexed.
- **Redis:** Healthy, used for caching and Celery broker.

## 3. Security Audit
### Python (Bandit)
- **Status:** PASS with minor warnings.
- **Findings:**
  - `B110 (try_except_pass)`: Detected in `ai_engine.py`. Recommended to add logging to exceptions.
  - `B608 (SQL Injection)`: Flagged in `clustering.py`. Manual review confirms it uses placeholders and is safe, but code style triggers the linter.
  - `B104 (Bind all interfaces)`: Flagged in `api_helpers.py`, verified as part of a blocklist for SSRF protection, not a vulnerability.

### Node.js (npm audit)
- **Status:** **CLEAN**
- No vulnerabilities found in `web` or `web-mk` dependencies.

### Configuration
- Security headers (HSTS, CSP, etc.) are correctly implemented via Nginx snippets.
- Environment variables are managed via `.env` files with `.env.example` as a template.

## 4. Ingestion & Data Health
- **Source Health:** **WARNING**
- High failure rate for Macedonian sources (`.mk` domains).
- **Common Issues:**
  - `Temporary failure in name resolution` (DNS issues).
  - `404 Not Found` (Feed URLs likely changed).
  - `Cloudflare challenge blocked` (Requires better anti-bot headers or proxy).
  - `SSL Certificate Expired` (e.g., `sky.mk`, `gol.mk`).

## 5. Recommendations
### High Priority
1. **Free Disk Space:** Run `sudo journalctl --vacuum-time=1d` to clear old system logs.
2. **Fix Ingestion:** Update RSS feed URLs for 404ing sources and investigate DNS resolution issues for `.mk` domains.
3. **Database Maintenance:** Schedule periodic `VACUUM ANALYZE` if not already handled by autovacuum.

### Medium Priority
1. **Improve Logging:** Replace `pass` in `try-except` blocks with proper logging to catch silent failures in the AI engine.
2. **Update Dependencies:** Some Python packages are significantly outdated (e.g., `cryptography`, `requests`, `pip`).

## 6. Audit Log Files
- `audit_bandit_new.txt`: Bandit findings.
- `audit_npm_web_new.json`: Frontend audit.
- `audit_pip_outdated_new.txt`: List of outdated Python packages.
- `check_source_health.py` output: Detailed source status.
