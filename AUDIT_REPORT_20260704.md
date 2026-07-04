# Presek Comprehensive Audit Report — 2026-07-04

- **Repo:** `/home/emiloffingen/presek`
- **Head:** `077e67eb` (`pin: cap broken PyPI packages`)
- **Scope:** Backend (FastAPI + Celery, ~44k LOC Python across `core/ routes/ tasks/ nlp/ utils/`) + Astro frontend (`web/`)
- **Method:** Static read-only audit by 5 parallel agents (security, code quality, architecture, performance, frontend). No files were modified.
- **Prior reports:** This joins a series of date-stamped `AUDIT_REPORT_*.md` already at repo root (see code-quality finding H8 — those should be archived).

## TL;DR

Presek is a mature, well-defended app: JWT auth is sound, SQL is parameterized, SSRF protections are strong, no hardcoded secrets, path traversal is blocked, rate-limit bypass is correctly gated, and the Astro frontend sanitizes all `set:html` through DOMPurify. The most pressing issues are:

1. **P0/S-H1** Frontend CSP downgrades the backend's nonce-based policy to `script-src 'unsafe-inline'`, neutralizing XSS mitigations site-wide.
2. **P0/C-H1** Three sync blocking calls (embedding inference, LLM `analyst.analyze`, Pillow resize + sync Redis) run inside `async def` routes — one slow query stalls the entire event loop.
3. **S-H2** Host-header injection in the marketing payment + access-email flow (Stripe redirect / outbound email payload).
4. **A-1/A-2** Layering is inverted: `core/` imports `tasks/` and `routes/`; `tasks/` imports `routes/`; all three import `scripts/` at runtime.
5. **Q-C1/C3** CI doesn't run linters/type-checkers; the local venv has a broken `pytest-mock` and `pytest --co` fails before any test runs.

---

## Severity legend

- **P0** — production availability / correctness risk (event-loop stalls, query timeouts).
- **S-Crit / S-H / S-M / S-L** — security: Critical / High / Medium / Low.
- **A-H / A-M / A-L** — architecture.
- **Q-C / Q-H / Q-M / Q-L** — code quality.
- **F-H / F-M / F-L** — frontend.

---

## 1. Security

The auth core, JWT handling (HS256-only, issuer+audience, expiry, no `none` confusion), SQL parameterization (`core/database.py` uses `%s` exclusively; only validated-allowlist fragments are dynamic), SSRF defense (`utils/network.py:13-47` blocks private/loopback/link-local/metadata, peer-IP verified post-connect), path-traversal guards, and rate-limit bypass gating (`ENV != production` AND loopback AND non-admin path) are solid. No hardcoded credentials; `private_key.pem`/`public_key.pem` at repo root are orphaned, unreferenced, and not tracked. No `shell=True`, `eval`, `exec`, or `pickle.loads` in app code.

| # | Sev | Area | File:Line | Issue | Remediation |
|---|---|---|---|---|---|
| S-H1 | High | CSP | `web/src/middleware.ts:40`, `web/src/lib/csp.ts:14` | Astro middleware overwrites the backend nonce-based CSP with `script-src 'self' 'unsafe-inline' https://www.googletagmanager.com`; per-request nonce is computed but never added to the policy. Every inline script anywhere in the document executes. | Drop `'unsafe-inline'`; emit `script-src 'self' 'nonce-<nonce>'`; thread nonces into every inline script (F-M2 enumerates the missing ones). |
| S-H2 | High | Host header | `routes/marketing.py:140-146`, `:420-424` | `base_url` derived from `request.headers["host"]` + `x-forwarded-proto`; a forged Host (if any proxy passes it through unvalidated) lets an attacker mint Stripe `success_url`/`cancel_url` and embed attacker links in access-request emails. | Derive `base_url` from a configured `PUBLIC_SITE_URL`; validate Host against prod domains. |
| S-M1 | Med | AuthZ (page gate) | `web/src/middleware.ts:62-76` | Admin-page token compared with `!==` (timing) and accepted via URL query string (logs/Referer leak). | Header-only delivery; `crypto.timingSafeEqual`. |
| S-M2 | Med | Upload/CSRF | `routes/marketing.py:37-236` | `/marketing/checkout` is unauthenticated, CSRF-less, writes uploaded files to `static/uploads/ads/`, and mints Stripe Checkout sessions. | Add CSRF; require a one-time signed initiate token; re-encode uploads (already partially done) and add `Content-Disposition`. |
| S-M3 | Med | CSRF | `routes/marketing.py:328,340,401` | Click/impression/request-access POSTs lack `verify_csrf_token`; `request-access` sends email (email-bomb / phishing vector). | `Depends(verify_csrf_token)` on all three. |
| S-L1 | Low | Crypto | `core/admin_tokens.py:267` | Admin-token hash compared with `!=` instead of constant-time. | `hmac.compare_digest`. |
| S-L2 | Low | SSRF | `utils/network.py:13-47` + callers | Resolve-then-connect window permits theoretical DNS rebinding; mitigated by post-connect peer-IP check. | Pin resolved IP for the actual connection. |
| S-L3 | Low | CORS | `core/api_fast.py:181-188` | `allow_headers=["*"]` with credentials enabled. | Restrict to the explicit header allowlist. |
| S-L4 | Low | Deps | `pyproject.toml:16`, `requirements.txt:388` | `passlib==1.7.4` is unused, unmaintained dead surface. | Remove; adopt `argon2-cffi` if passwords are ever introduced. |
| S-I1 | Info | Secrets | `private_key.pem`, `public_key.pem` (root) | Orphaned PEMs on disk; gitignored, not tracked, unreferenced. | Delete or move to a secrets manager. |
| S-I2 | Info | CSP endpoint | `PROJECT.md:34-39` | Planned `/api/csp-report` (CSRF/RL bypass) not yet implemented — when added, ensure it is pure logging with no side effects. | Strict Pydantic model; explicit RL exemption; cap log size. |
| S-I3 | Info | Secrets scan | `.secrets.baseline` | All baseline hits are false positives/templates; no live secrets found. | Periodically re-run `detect-secrets scan --baseline`. |

**Security posture:** Strong, with the CSP downgrade (S-H1) being the only finding that meaningfully elevates client-side risk today. Fixes for S-H1 and S-H2 should be top priority.

---

## 2. Performance

| # | Sev | Area | File:Line | Issue | Remediation |
|---|---|---|---|---|---|
| P-H1 | **P0** | Async | `routes/news.py:429,821`, `routes/intelligence.py:1245` | Sync `generate_query_embedding()` (torch/CPU MiniLM inference) called inside `async def` — loads torch + the model into the API process on first cold query and blocks the entire event loop for tens–hundreds of ms per query. | `await get_query_embedding_async(q)` (the helper exists at `core/embeddings.py:344`); better, push to a `fast-track` Celery task. |
| P-H2 | **P0** | Async | `routes/intelligence.py:920-1023` (`synthesize_nodes`) | Sync `analyst.analyze()` runs llama-cpp CPU inference for several seconds (plus a `time.sleep(1.0)` Redis-lock spin loop at `nlp/local_analyst.py:199-206`) inside `async def`. Rate-limited to 5/min but a single call freezes the whole API for the duration. | Enqueue a `fast-track` task and return 202, or `await asyncio.to_thread(analyst.analyze, ...)`. |
| P-H3 | **P0** | Async | `routes/system.py:906-987` (`/proxy`) | Pillow `Image.open().resize(LANCZOS).save("WEBP", method=4)` + sync `redis_client.get/set` + sync `open()` all block inside `async def proxy_image`. Homepage fans out dozens of these in parallel — serialized on the single event loop. | `await asyncio.to_thread(...)` for fetch+resize+encode; `redis.asyncio`; lower WEBP `method` to 2. |
| P-H4 | **P1** | Async | `core/database.py:48-79` (`_read_replica_is_fresh`) | On every 30s TTL expiry, the first async query opens two sync `psycopg.connect(..., connect_timeout=3)` and runs `SELECT MAX(...)` on primary + replica — on the event loop. Up to 6s of stall. | Background timer refresh, `psycopg.AsyncConnection`, or `await asyncio.to_thread`. |
| P-H5 | **P1** | Async | `utils/cache.py:21-51`, `:36-53` | Sync `redis.Redis` (`get`/`set` socket calls with `json.dumps(DateTimeEncoder)` on large payloads) used in every cached async route. | Switch hot path to `redis.asyncio`. |
| P-M1 | **P1** | DB | `routes/news.py:461,506,568,598,679,1053`, `routes/home.py:778`, `routes/intelligence.py:1266`, `core/database.py:656,734` | `SELECT * FROM articles` on every homepage / cluster-list / archive path materializes `embedding vector(384)`, `full_content TEXT`, `search_vector tsvector` for up to 500 cluster IDs × multiple articles each. Mostly discarded by `_public_article_payload` (`news.py:138`). | Project explicit columns; fetch `full_content` only on the cluster-detail route. |
| P-M2 | **P1** | DB N+1 | `tasks/intelligence/metadata.py:91-95`, `:200-204`, `core/embeddings.py:135-152` | Per-cluster `SELECT cluster_entities WHERE cluster_id=%s`, per-entity `INSERT ... ON CONFLICT DO NOTHING`, per-article `UPDATE ... WHERE id=%s` loops. | `WHERE cluster_id = ANY(%s)` once; `executemany` / multi-row INSERT; `UPDATE … FROM unnest(...)`. |
| P-M3 | **P1** | Ingestion | `core/ingestion.py:1197-1322` | Batch-clustering inner loop is O(N²) over candidates in pure Python; combined with `recent_articles.insert(0,…).pop()` = O(N·M). `SoftTimeLimitExceeded` is caught and partial flushes (`:1175,1324-1330`) — a correctness patch, not a throughput fix. Large feed sweeps still risk truncation. | Bucket by `(category, topic)`; pgvector SQL-side similarity join; `deque(maxlen=CLUSTER_LOOKBACK)`. |
| P-M4 | **P2** | DB indexes | `migrations/versions/b251aec55d2e_*.py`, `24434f8a57fc_*.py`, `bcfd5f5cf64c_*.py` | Queries use `WHERE cluster_id = ANY(%s) ORDER BY created_at DESC` on a single-column `articles(cluster_id)` index (forces per-cluster re-sort); `cluster_entities WHERE LOWER(entity_name)=LOWER(%s)` and `knowledge_entities WHERE LOWER(name)=LOWER(%s)` have no functional indexes; `cluster_metadata(updated_at)` filtered for 14-day window has no index; `articles WHERE topic='vesti'` scans (no `topic` index). | Composite `articles(cluster_id, created_at DESC)`; functional `cluster_entities(lower(entity_name))`, `knowledge_entities(lower(name))`; `cluster_metadata(updated_at)`; partial `articles(topic) WHERE topic='vesti'`. |
| P-M5 | **P2** | Cache | `tasks/utils.py:55-62` | `invalidate_public_data_caches` blows `api:news:`, `api:home:`, `api:intelligence:`, etc. — but **not** `api:search:semantic:*` (`news.py:813`, ttl 300) nor `api:cluster:*:historical:v1` (`news.py:1562`, ttl 3600). Worse: plain ingestion that adds an article to an existing cluster does **not** call `invalidate_cluster_caches(cluster_id)` — readers see stale article lists (cluster detail ttl up to 3600s) until synthesis runs. Low-source clusters may never re-synthesize. | Call `invalidate_cluster_caches` for every `modified_cluster_ids` in `run_ingestion` (`ingestion_task.py:163-164` already computes the set); add the missing prefixes. |
| P-M6 | **P2** | Worker | `tasks/intelligence/summarization.py:20-39`, `:60` | Batch summarization tasks call `summarize_article_task(article_id)` **directly** (not `.delay()`) — bypasses the per-task `rate_limit="50/m"`. One slow LLM call dominates a 200-item batch with no per-item timeout. Also `generate_embeddings_task` (`backfill.py:116`) has no `soft_time_limit`. | `.delay()` per item (or chunk with per-item `try/except SoftTimeLimitExceeded`); add explicit `soft_time_limit` to `generate_embeddings_task`. |
| P-M7 | **P2** | Cache herd | `routes/news.py:1346-1417` | `get_cluster_detail` cold-path does O(N²) `get_jaccard_similarity` + per-article `analyze_sentiment_locally` in-process; no singleflight lock around cache refill → thundering herd when a popular cluster page expires under concurrent load. | Precompute `timeline`/`stance_vectors`/`editorial_divergence` in `synthesize_cluster_task`; add Redis singleflight on cache miss. |
| P-L1 | **P3** | Pool | `core/database.py:259-262` | `DB_POOL_MINCONN=1`, `DB_POOL_MAXCONN=5` defaults are small for the homepage's concurrent fan-out under gunicorn/uvicorn with multiple workers. | Tune to `min=2, max=20+`; monitor `presek_db_pool_waiting`. |
| P-L2 | **P3** | SSR | `web/src/lib/homepageData.ts:174-224` | `loadHomepageFallback` fires 5–6 parallel backend `fetch()` per SSR request via bare `fetchJson` (not `fetchJsonCached`) — fans out N×5 from SSR tier on backend hiccup. | Route through `fetchJsonCached`; lower SSR fetch timeout to 3–5s. |
| P-L3 | **P3** | Deps | `pyproject.toml` `[tool.uv].default-groups = ["api","worker"]` | A default install pulls torch/spacy/llama-cpp + sentence-transformers/fasttext; the API is architected to run embeddings in-process, so the api/worker split exists in pyproject but is not enforced at runtime. | Move query-embedding to a `fast-track` task (worker-only) or set `default-groups = ["api"]`; confirm worker hosts install torch/spacy. |

**Top fixes:** P-H1, P-H2, P-H3 are the clearest availability wins — three localized changes each unblock the entire API under load.

---

## 3. Architecture

| # | Sev | Area | File:Line | Issue | Remediation |
|---|---|---|---|---|---|
| A-1 | High | Layering | `core/ai_engine.py:1195,1260`, `core/ingestion.py:1363,1417-1426`, `core/clustering.py:928-929`, `core/services/notifier.py:7` (module-level), `core/limiter.py:26` | `core/` imports `tasks/` and `routes/` — domain core reaches into orchestration/HTTP layers. Deferred imports hide (not prevent) the cycle. | Move task dispatch out of core domain into a thin orchestration layer; move `_client_ip_for_request` to `core/` or `utils/`. |
| A-2 | High | Layering | `core/celery_app.py:100`, `routes/monitoring.py:17`, `tasks/maintenance.py:486` | `core/`, `routes/`, `tasks/` import `scripts/` at runtime — Celery's task-failure handler itself calls `scripts.monitor_errors.check_failed_tasks`, coupling every worker to the ad-hoc toolkit. | Move `monitor_errors`, `monitor_synthesis_quality`, `security_monitoring` into `core/ops/` or `core/observability/`. |
| A-3 | High | DI | `core/dependency_injector.py` (265 LOC) | Zero external importers; DI subsystem is dead. 81 sites hard-import `db_manager` directly. Inconsistent style as pure dead weight. | Delete it, or commit to using it everywhere. |
| A-4 | High | DB | ~319 inline `execute()` SQL strings across `core/routes/tasks` | No repository pattern, no ORM = schema has no single source-of-truth object. Column renames silently break scattered raw strings. migrations are hand-written SQL post-hoc (`472c0aa46965_recover_delivery_tables`, `722c56e76f5b_recover_missing_intelligence_tables`, `eba041de01ad_add_missing_schema_columns`). | Introduce a repository layer or SQLAlchemy models + alembic autogenerate (`migrations/env.py:27` has empty `MetaData()`). |
| A-5 | Med | Wiring | `core/api_fast.py:472-482`, `:883-902` | All 9 routers mounted **twice** under `/api` and `/api/v1`; admin trigger routes live inline (`:774-879`) instead of `routes/admin.py`; `api_fast.py` is a 902-line god-file with inline health/metrics/audio/image-proxy/CSRF/delivery-tracking endpoints. | Single API prefix; move inline routes into routers; split into `core/app.py` + routers. |
| A-6 | Med | API contract | (no committed OpenAPI) | Frontend hardcodes `/api/...` paths in ~20 Preact islands; `api_fast.py:132-133` disables docs in prod so no schema export. Route renames silently break the frontend. | Export `openapi.json` at build, commit under `docs/`, generate `web/src/types/api.ts`. |
| A-7 | Med | Queues | `core/celery_app.py:332-359`, `:163-331` | No global retry policy (`task_annotations` omits `autoretry_for`/`max_retries`); beat entries inconsistently set `options.expires`; idempotency is per-task opt-in via `acquire_task_lock`. | Define a global retry policy; require `expires` on every beat entry; make idempotency a shared helper. |
| A-8 | Med | Overlap | `core/db_monitoring.py:101,130,139,207,217,223,325,333,341` | `DatabaseMonitor.resize_pool`, `check_pool_health`, `get_current_pool_stats`, `is_pool_under_stress`, `get_pool_stress_level` duplicate `DatabaseManager.resize_pool` (`database.py:539`) and `get_pool_stats` (`:516`). Two pool-resize paths. | Consolidate monitoring onto `DatabaseManager` accessors. |
| A-9 | Med | Config | `core/celery_app.py:111-112,365`, `core/api_fast.py:141-180`, `core/limiter.py`, `core/personalization_score.py`, `core/auth.py`, `core/clustering.py`, `core/runtime_limits.py` (48 reads), `core/services/notifier.py`, `core/version.py` | 228 `os.getenv` calls outside `core/config.py`; `runtime_limits.py` is a de-facto second config layer bypassing Pydantic Settings. | Fold every env-backed value into `core/config.py` Settings; absorb or remove `runtime_limits.py`. |
| A-10 | Med | God-package | `core/` (~57 flat .py), `core/ingestion.py` 57 KB, `core/ai_engine.py` 49 KB, `core/api_fast.py` 902 L | `core/` has grown into a grab-bag; top-level `nlp/` (12 modules) overlaps `core/embeddings.py`, `core/clustering.py`, `core/cross_lingual.py`, `core/entities.py`, `core/topic_discovery.py` with no documented split. | Subpackage `core/{auth,ingestion,ai,nlp,infra,ops,localization,web}/`; merge or boundary top-level `nlp/` against `core/nlp/`. |
| A-11 | Med | Deploy | `deploy/dry-run-deploy.sh` (3081 B) vs `scripts/dry-run-deploy.sh` (4340 B); `deploy_release.sh` (root stub) vs `deploy/deploy_release.sh` (real, 21 KB) | Two divergent dry-run scripts; two deploy_release scripts with unclear seam. | Single deploy entry; delete the root stub; reconcile the dry-run scripts. |
| A-12 | Med | Migrations | `migrations/env.py:27`, `add_language_to_daily_briefings.py` | Autogenerate disabled (empty `MetaData()`); 25 revisions follow `12-hex_slug.py` but `add_language_to_daily_briefings.py` lacks the hex prefix and likely no-ops after `b7ba54d8a217_add_lang_to_daily_briefings.py`. | Introduce ORM (see A-4); squash the redundant migration. |
| A-13 | Low | Hygiene | repo root | 14 `AUDIT_REPORT_*.md`/`IMPROVEMENT_*.md` reports (incl. this one) + root `.py` files (`health.py`, `update_broadsheet*.py`, `verify_marketing_math.py`, `scratch/test_briefing.py`) + UI debug PNGs (803 KB + 163 KB) tracked at root. | Archive dated reports to `docs/audits/`; `git rm` scratch files; move root scripts into `scripts/`. |
| A-14 | Low | Dead code | `core/translated_prompts.py` (49 LOC, 0 importers), `core/dependency_injector.py` | Orphan modules. | Delete. |
| A-15 | Low | Loc | `core/localization_rules.json` (677 LOC) | Flat in `core/` next to `localization.py`; only 3 importers. | Move into `core/localization/resources/`. |

**Deploy-vs-scripts seam (A-11) becomes natural once A-2 is resolved:** once `monitor_errors`/`monitor_synthesis_quality`/`security_monitoring` move into the app package, `scripts/` becomes purely dev-ad-hoc one-shots + backfills (Q-H3 confirms ~60 of 87 tracked scripts are unreferenced), and `deploy/` remains one-time install/release scripts.

---

## 4. Code Quality

| # | Sev | Area | File:Line | Issue | Remediation |
|---|---|---|---|---|---|
| Q-C1 | **Crit** | CI | `.github/workflows/ci-cd.yml` | Linters/formatters/mypy configured in `.pre-commit-config.yaml` (ruff, black, isort, flake8, mypy, codespell, detect-secrets) **never run in CI**. Pre-commit only fires if installed locally. | Add a `lint` job: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy core/ routes/ tasks/ nlp/ utils/`, `pre-commit run --all-files`. |
| Q-C2 | **Crit** | Types | `pyproject.toml` (no `[tool.mypy]`) | mypy is configured in pre-commit with `--ignore-missing-imports` and no scope; weak coverage; 412 broad `except Exception` blocks; no `disallow_untyped_defs`. | Add `[tool.mypy]` with explicit `files` and strictness flags; gate in CI. |
| Q-C3 | **Crit** | Tests | `.venv/bin/python3 -m pytest --co` | `SyntaxError` in `.venv/lib/python3.12/site-packages/pytest_mock/plugin.py:230` — the venv's `pytest-mock` is incompatible with the installed `pytest` 9.x. Local test collection fails before any test runs. | Pin compatible `pytest-mock`/`pytest` in `[dependency-groups].dev`; recreate the lock. |
| Q-H1 | High | Complexity | `nlp/generation.py:1152,1738,905,580`, `core/ingestion.py:~460`, `routes/news.py:470,431`, `routes/intelligence.py:217`, `core/ai_engine.py` | 8+ god-functions 150–530 LOC (`ingest_all_sources_async` ~530, `synthesize_cluster_fallback` 259, `get_cluster_detail` 470, `fetch_news_data` 431, `generate_local_placeholder` 268). Untestable monoliths. | Extract stages into named helpers ≤ ~50 LOC each. |
| Q-H2 | High | Errors | 25 confirmed `except Exception: pass` sites (enumerated in §Q-H2 of raw notes); 412 total broad excepts | Silent swallows across `core/limiter.py:29-30`, `core/api_fast.py:226-227`, `core/llm_router.py:239-240`, `core/crawler.py:135-136`, `core/ai_engine.py:240-241,1032-1033,1038-1039`, `core/entities.py:613-614`, `core/database.py:290-291,302-303,308-309`, `core/synthesis_quality.py:79-80,229-230,240-241`, `routes/stats.py:875-876`, `routes/security.py:98-99,487-488`, `routes/common.py:221-222`, `routes/system.py:755-756,764-765,774-775,985-986`, `tasks/intelligence/synthesis_merge.py:62-63`, `tasks/maintenance.py:961-962`, `nlp/generation.py:835-836`. | Narrow exception types; at minimum `logger.exception(...)`; enable ruff `E722,S110,S112,B902,T20`. |
| Q-H3 | High | Dead code | `scripts/` (~60 of 87 tracked .py unreferenced) | One-off backfills/prototypes sitting in VCS: `backfill_briefings.py`, `backfill_cluster_centroids.py`, `prototype_*.py`, `inspect_*.py`, `repair_*.py`, `split_mixed_cluster.py`, `take_all_screenshots.py`, and ~50 more (full list in raw notes). | `git mv` to `scripts/archive/` (history preserved) or delete. |
| Q-H4 | High | Duplication | `scripts/analyze_dependencies.py` (278 LOC) vs `_fixed.py` (92 LOC); root `update_broadsheet.py` vs `update_broadsheet_v2.py`; `tests/test_ft_fix.py` vs `test_ft_fix_v2.py` | `_v2/_fixed` variants indicate the original was patched elsewhere instead of revised. | Replace the original in place; delete the superseded variant. |
| Q-H5 | High | Duplication | `tasks/synthesis_sanitize.py:14` & `tasks/intelligence/synthesis_scoring.py:10` | `_paragraph_fingerprint(text)` defined identically in both. `core/mk_copy_quality.py` is a 7-line shim re-exporting 3 names. `core/translated_prompts.py` (49 LOC) is dead. | Extract to `nlp/utils.py` or `tasks/utils.py`; delete `mk_copy_quality.py` and `translated_prompts.py` after migration. |
| Q-H6 | High | Config | 228 `os.getenv` outside `core/config.py`; `core/runtime_limits.py` (48 reads), `core/llm_router.py` (15), `core/ai_engine.py` (14), `core/digest.py` (10), `core/admin_tokens.py` (9) | Multiple shadow configs; scattered magic timeouts (`core/ingestion.py` `timedelta(minutes=30)/(days=14)`, `core/crawler.py:260-261` `timeout=30000`, `core/audio_service.py` `timeout=30/60`, `core/ai_engine.py:230,290,803,878`). | Centralize env reads + timeouts/sleeps as named constants in `core/config.py` Settings. |
| Q-H7 | High | Hygiene | repo root | `homepage.html` (162 KB), `scratch_svg.png` (40 KB), `ui_inspection.png` (163 KB), `ui_inspection_full.png` (803 KB), `scratch/test_briefing.py`, root `health.py` (12-line `sys.modules` alias shim) — all tracked despite `.gitignore` partially listing them. | `git rm` the scratch artifacts; replace tests' `import health` with `core.health`; delete the root shim. |
| Q-H8 | High | Docs | repo root | 34 tracked `.md`: 10 date-stamped `AUDIT_REPORT_YYYYMMDD.md` + `COMPREHENSIVE_IMPROVEMENT_REPORT.md`, `FINAL_IMPROVEMENT_REPORT.md`, `IMPROVEMENT_PLAN_20260626.md`, `IMPROVEMENT_SUMMARY_20260626.md`, `FIXES_SUMMARY_20260702.md`, `IMPLEMENTATION_COMPLETE.md`, `ROUTER_ENHANCEMENTS_SUMMARY.md`, `BUG_SEARCH_RESULTS.md`, `DEPENDENCY_ANALYSIS_REPORT.md`, `CATEGORY_COVERAGE_ANALYSIS.md`, `FREE_API_OPTIMIZATION.md`, `GEMMA_4_E2B_FIX.md`, `IMAGE_PROXY_TROUBLESHOOTING.md`, `MIGRATION_PLAN.md`, `SECURITY_AUDIT_SUMMARY.md`, `TEST_INFRA.md`. | Move dated audits/improvements/fixes into `docs/audits/`. Keep only `README`, `CHANGELOG`, `DESIGN`, `PROJECT`, `SECURITY*`, `PRIVACY_POLICY`, `TERMS_OF_SERVICE` at root. |
| Q-M1 | Med | Tests | `tests/` (115 files / 893 fns) | Source modules lacking a matching `test_*.py`: `core/opentelemetry_config.py`, `core/dependency_injector.py` (dead), `core/db_monitoring.py`, `core/queue_monitoring.py`, `core/research_helpers.py`, `core/text_extraction.py`, `core/topic_discovery.py`, `core/source_catalog.py`, `core/editorial_quality.py`. Security-critical `core/auth.py` (4 KB) only has `test_auth.py`; `core/crawler.py` only SSRF-minimally covered. | Add unit tests for `auth`, `crawler` (full URL-validation matrix), `synthesis_quality`, `*_monitoring`. |
| Q-M2 | Med | Logging | `core/logging_config.py` (`StructuredFormatter`, JSON) | Only 8 modules import from `logging_config`; 11 `print(` remain in production source (`core/digest.py:808,813`, `core/clustering.py`, `tasks/intelligence/synthesis_scoring.py`, `tasks/synthesis_sanitize.py`). | Replace prints with `get_logger(__name__).info`; enable ruff `T20`. |
| Q-M3 | Med | Hygiene | root `health.py` | `sys.modules[__name__] = _health` alias shim — clever but breaks IDE navigation/mypy and duplicates the canonical module. | Rename test patch targets to `core.health`; delete the shim. |
| Q-M4 | Med | Tooling | `.pre-commit-config.yaml`, `pyproject.toml` `[project.optional-dependencies].Dev`, `[dependency-groups].dev` | Three disjoint version sources (pre-commit pins ruff v0.1.6 / black 24.8.0 / isort / flake8; `Dev` block black 26.x / mypy 1.11.2 / flake8 7.1.1; `dev` group ruff>=0.15.12). Both ruff and black format (conflicting); flake8 redundant after ruff. | Pick one formatter (`ruff format`); drop black/isort/flake8; align all three version sources. |
| Q-L1 | Low | Misc | `models/` symlink → `/home/emiloffingen/presek-runtime/shared/models` | Models correctly externalized via symlink + gitignored (`*.gguf`, `*.safetensors`, `*.bin`); **no binary AI models tracked in git**. `core/database.db` appears untracked (spot-verify). | None — positive finding. |

**Top remediation priorities:** (1) Fix the broken `pytest-mock` lock so tests can run (Q-C3). (2) Add a CI lint+types job (Q-C1, Q-C2). (3) Enable ruff `E722,S110,S112,B902,T20` and fix the 25 swallow sites (Q-H2, Q-M2). (4) `git rm` scratch files; archive dated `.md` (Q-H7, Q-H8). (5) `scripts/archive/` the ~60 dead scripts + delete `_fixed`/`_v2` duplicates (Q-H3, Q-H4).

---

## 5. Frontend (Astro)

Posture: No reflected/stored XSS sink bypass found — all `set:html` sinks route through DOMPurify (`src/lib/sanitize.ts:21`), `renderSynthesisHtml`, `formatBriefing`, `highlightFactText`, `highlightScores`, or `safeJsonForScript`. No React `dangerouslySetInnerHTML` with unsanitized data (5 occurrences all wrapped). No JWT in `localStorage`/`sessionStorage` (admin token held in React `useState` in-memory; `$syncToken` is an opaque reader-profile sync token, not auth). No hardcoded VAPID/API keys (fetched per session).

| # | Sev | Area | File:Line | Issue | Remediation |
|---|---|---|---|---|---|
| F-H1 | High | CSP | `src/middleware.ts:40`, `src/lib/csp.ts:14` | (Same as S-H1 — repeated for completeness, this is the frontend-side fix.) Nonce generated per request but never inserted into the policy; `script-src 'unsafe-inline'` degrades to permissive. The entire XSS mitigation currently rests on continued correctness of every `set:html` sanitizer call. | Append `'nonce-<nonce>'`; drop `'unsafe-inline'`. |
| F-M1 | Med | XSS (contract) | `BriefingContent.astro:11`, `EditorialNarrative.astro:137,144`, `CredibilityAnalysis.astro:140,152,166,175,227,228` | Sanitization is implicit — sinks trust that the caller (`formatBriefing()`, `renderSynthesisHtml()`) sanitized. A future caller passing raw API/AI content introduces stored XSS. Origin is AI/backend synthesis text — attacker-influential server content. | Defense-in-depth: call `sanitizeHtml()` inside each component immediately before `set:html`, or adopt a branded `SafeHtml` type. |
| F-M2 | Med | CSP | `cluster/[slug].astro:796`, `briefing.astro:337`, `pulse.astro:90`, `ClusterAnalysisSection.astro:57`, `HomePage.astro:566`, `LayoutBodyChrome.astro:20-23` (4), `LayoutHead.astro:58` | Multiple `is:inline` scripts lack `nonce`; will break once F-H1 is fixed. | Thread `cspNonce` into each. |
| F-M3 | Med | Trackers | `LayoutHead.astro:44-57` | Google Analytics (`gtag`) loaded from `googletagmanager.com` and `google-analytics.com` / `analytics.google.com` / `region1.google-analytics.com` allowlisted in CSP — contradicts the "no external trackers" expectation and the two-CDN allowlist described in `SECURITY.md`. Default consent is fully denied (good). | If GA is intentional, document it; otherwise remove and drop the google-analytics domains from CSP. |
| F-M4 | Med | SSR fetch | `cluster/[slug].astro:88`, `briefing.astro:49-50,59`, `archive.astro:46-47`, `rss.xml.ts:32`, `sitemap.xml.ts:27`, `og/cluster/[id].svg.ts:46`, `og-image.svg.ts:9`, `status.astro:34`, `admin/status.astro:10`, `NativeAdSlot.astro:19`, `loadEntitySubject.ts:20-23` | ~20 SSR `fetch()` calls have no `AbortController`/timeout; `Promise.all` faults on any branch; some have no `try/catch` (rss/sitemap/og) → a slow backend stalls SSR indefinitely. | Route through `fetchJsonCached()`; add 5–10s `AbortController`; `Promise.allSettled` where partial data is OK. |
| F-L1 | Low | CSP | `Breadcrumbs.astro:61` | JSON-LD `<script is:inline set:html={...}>` omits `nonce` (siblings tag nonces). | Add `nonce={cspNonce}` or drop `is:inline` and emit via a bundled module. |
| F-L2 | Low | CSP | `src/lib/tinyadz.ts:1`, `TinyAdzScript.astro:24-31` | TinyAdz loader at `cdn.apitiny.net` is **not** in CSP. Feature fully disabled today (`shouldLoadTinyAdzScript()` returns false, zero call sites). | Before re-enable: add `cdn.apitiny.net` to `script-src`/`connect-src` or self-host. |
| F-L3 | Low | Privacy | `pages/support.astro:61` | External ko-fi image — Referer leak / possible tracking pixel. | Self-host the icon. |
| F-L4 | Low | Robustness | `src/lib/loadEntitySubject.ts:12` | `decodeURIComponent(params.name)` without try/catch — malformed `%` throws `URIError` before the fetch. | Wrap; return 404 on malformed input. |
| F-L5 | Low | AuthZ | `src/middleware.ts:62-76` | (Same as S-M1.) Admin-gate token via query string and `!==` comparison. | Header-only; `crypto.timingSafeEqual`. |
| F-L6 | Low | i18n | `LayoutHead.astro:76` | hreflang `sr-Latn-RS` — confirm validator acceptance (BCP-47 prefers `sr-Latn-RS`). | Verify; minor. |
| F-L7 | Low | Types | `astro.config.mjs:1` | `@ts-nocheck` escapes type-checking entirely; masks future type errors. | Remove; add targeted `// @ts-expect-error` where needed. |

**Net posture:** The DOMPurify-based sanitizers are correctly applied at every sink today; the single highest-impact issue is that CSP keeps `'unsafe-inline'`, so the entire XSS mitigation rests on every individual sanitizer's continued correctness (F-M1) rather than being backed by a strict CSP. Fixing F-H1 + F-M2 closes that gap; adding defense-in-depth sanitizer calls at the AI-synthesis text sinks (F-M1) hardens the path that consumes attacker-influential server content.

---

## Cross-cutting remediation plan (prioritized)

### Immediate (runtime correctness / security)

1. **Fix the three P0 async-blockers** (P-H1, P-H2, P-H3) — localized changes each, biggest availability win.
2. **Restore strict CSP on the frontend** (S-H1 / F-H1) — drop `'unsafe-inline'`, thread nonces (F-M2 lists the sites).
3. **Pin `PUBLIC_SITE_URL` for the marketing flow** (S-H2) — relace Host-header-derived `base_url`.
4. **Harden admin page gate** (S-M1 / F-L5) — header-only + constant-time.
5. **Add CSRF to `/marketing/checkout` + click/impression/request-access** (S-M2, S-M3).
6. **Fix `pytest-mock` lock** (Q-C3) — local tests can't run today.

### Short term (CI / quality gates)

7. **Add a CI `lint` job** running `ruff check`, `ruff format --check`, `mypy`, `pre-commit run --all-files`; enable ruff rules `E722 S110 S112 B902 T20` (Q-C1, Q-C2, Q-H2, Q-M2).
8. **Fix the 25 `except Exception: pass` swallow sites** with narrow exceptions + `logger.exception` (Q-H2).
9. **Invalidate cluster caches on plain ingestion** (P-M5) — `invalidate_cluster_caches` for each `modified_cluster_ids`; add `api:search:semantic:` and `api:cluster:*:historical:` to the prefix-blow list.
10. **Bound `summarize_articles_*_batch_task`** per-item; add `soft_time_limit` to `generate_embeddings_task` (P-M6).

### Medium term (architecture / performance)

11. **Move query-embedding + node synthesis off the API event loop** into `fast-track` Celery tasks (P-H1, P-H2 long-term).
12. **Replace `SELECT *` on article-list hot paths** with projected columns; add the composite `articles(cluster_id, created_at DESC)` and functional indexes (P-M1, P-M4).
13. **Fix N+1 loops** in `tasks/intelligence/metadata.py:91-95,200-204` and `core/embeddings.py:135-152` (P-M2).
14. **Sub-quadratic batch clustering** in `core/ingestion.py:1197-1322` (P-M3).
15. **Cut `core ↔ tasks` / `core ↔ routes` import inversions** (A-1, A-2) — move `monitor_errors` / `monitor_synthesis_quality` / `security_monitoring` out of `scripts/` into `core/ops/`; move `_client_ip_for_request` to `core/`; delete `core/dependency_injector.py`.
16. **Commit an OpenAPI schema** and generate `web/src/types/api.ts` (A-6).
17. **Stop double-mounting routers** under `/api` and `/api/v1`; pick one prefix (A-5).
18. **Introduce a repository layer or SQLAlchemy models + alembic autogenerate** (A-4, A-12).

### Hygiene (low-risk, parallel)

19. **`git rm` scratch files** (`homepage.html`, PNGs, `scratch/`, root `health.py`, root scripts) (Q-H7, A-13).
20. **Archive dated audit/improvement .md reports** to `docs/audits/` — this file included (Q-H8, A-13).
21. **Move ~60 dead `scripts/` into `scripts/archive/`**; delete `_fixed`/`_v2` duplicates (Q-H3, Q-H4).
22. **Extract `_paragraph_fingerprint`** to `nlp/utils.py`; remove `core/mk_copy_quality.py` and `core/translated_prompts.py` (Q-H5, A-14).
23. **Remove unused `passlib`** (S-L4).
24. **Delete orphan `private_key.pem`/`public_key.pem`** on disk (S-I1).

---

## Appendix — raw agent artifacts

The five source audits this report synthesizes are preserved in the conversation history:
- Security audit (run #2): 13 focus areas verified, 12 findings.
- Code quality audit: 23 findings across complexity, dead code, dup, config, hygiene.
- Architecture audit: 16 findings across layering, DI, DB, queues, migrations, deploy seam.
- Performance audit: 14 findings P0–P3 with `file:line` evidence.
- Frontend audit: 12 findings (H/M/L) across XSS, CSP, trackers, SSR, auth.

---

*© 2026 Presek. Generated 2026-07-04T18:41:08Z.*