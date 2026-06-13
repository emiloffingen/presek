# Presek Changelog

## v8.0.0 (2026-06-13)

### New Features & UX
- Premium pages (`/for-you`, `/briefing`, `/settings`) are ad-free
- Za Vas loads recommendations client-side with skeleton UI for faster first paint
- Homepage start-here guide collapses on mobile; lead story appears first
- SR briefing dates render in Latin script (`sr-Latn-RS`)

### Fixes & Polish
- Removed duplicate Za Vas page header
- Fixed `test_tasks.py` imports after synthesis sanitize extraction
- Quieter ad styling on cluster/archive surfaces

## v5.7.0 (2025-04-26)

### New Features
- **Rate Limiting**: Added slowapi-based rate limiting for API endpoints
  - Default: 100 requests/minute, 1000 requests/hour per IP
  - Custom limits for expensive endpoints (research: 10/min, entity-graph: 30/min)
  - Health and tracking endpoints exempt from limits
  - Graceful fallback if slowapi not installed

- **Celery Worker Protection**:
  - Memory limit: 2GB per worker process (`worker_max_memory_per_child`)
  - Task limit: 100 tasks per worker before restart (`worker_max_tasks_per_child`)
  - Reduced concurrency: 2 concurrent tasks per worker (down from 4)
  - Task-specific rate limits for ingestion, embeddings, synthesis
  - Result expiration: 1 hour to reduce Redis overhead

- **Structured Logging**: New `logging_config.py` module
  - JSON logging in production mode
  - Human-readable text logging in development
  - Support for structured extra data in log messages
  - Automatic suppression of noisy library logs in production
  - Convenience functions: `log_request()`, `log_error()`

### Security Improvements
- Removed `.venv_audit/` directory from git (110MB of accidentally committed dependencies)
- Updated `.gitignore` with broader patterns for `.venv*` and `*.db*` files
- Removed debug `print()` statements from production code
- Added input length validation middleware:
  - Query parameter limit: 500 characters
  - Request body limit: 10MB
- Disabled API docs (`/api/docs`, `/api/redoc`) in production mode
- Configurable CORS origins via `CORS_ORIGINS` environment variable

### Bug Fixes
- Fixed SQL `COALESCE` expressions for consistency across intelligence endpoints
- Replaced "AI" terminology with "Systemic" for clarity in public-facing text

### Code Quality
- Centralized logging configuration
- Updated logging imports across modules to use `get_logger()` from `logging_config`
- Cleaned up duplicate log initialization

### Dependencies
- Added `slowapi==0.2.0` to requirements.txt (rate limiting)
- Added `structlog==24.10.0` to requirements.txt (structured logging, optional)

## v5.6.0 (2025-04-26)

- Fix: Sync stats counter with Europe/Skopje timezone

## v5.5.0 (2025-04-26)

- PWA: Upgrade to v5.4 with custom Offline page and smart caching

## v5.4.0 (2025-04-22)

- UI: Final editorial wording polish - Remove AI/Gemma jargon across all pages
