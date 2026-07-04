# App Bug Search Results

**Date:** 2026-06-09  
**Search Scope:** Full application codebase and tests

## Status: HEALTHY

| Check | Result |
|-------|--------|
| Backend tests | 513 passed, 1 skipped |
| Frontend tests | 32 passed |
| Frontend build | Pass |
| Security audit | Pass |

## Recent Fixes (2026-06-09)

- LLM router tests aligned with current routing logic
- Daily briefing grounding re-enabled (stricter entity check)
- API 500 responses normalized to `{"status": "error", ...}`
- Systemd service names unified to `presek-fastapi-unified.service`
- Deployment docs and CI deploy job updated
- pytest moved to dev dependency group
- Router metrics persisted to Redis (24h TTL)
- COEP header limited to HTML responses

## Known Non-Blocking Items

- `diskcache` CVE-2025-69872 — transitive via llama-cpp-python, no upstream fix yet
- Full Cypress E2E smoke tests require a running stack with seeded data (component tests run in CI)
- Production deploy via CI requires `DEPLOY_SSH_HOST`, `DEPLOY_SSH_USER`, `DEPLOY_SSH_KEY` secrets

## Conclusion

No blocking bugs. Safe to deploy after committing pending changes.
