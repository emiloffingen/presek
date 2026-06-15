# Presek Changelog

## v8.3.2 (2026-06-15)

### Fix
- Recluster/repair-split tasks: import `cosine_dist`, downstream rebuild tasks, and `_split_cluster_merge_score` in `cluster_ops`

## v8.3.1 (2026-06-15)

### Homepage editorial supply
- Fix feed offset bug: homepage feed now starts at cluster index 4 (was 5), recovering a dropped story slot
- Developing feed sorted by synthesis + source count; up to 10 multi-source clusters (was uncapped/unordered)
- Wire section capped at 8 singleton clusters (was 12) with fewer wire cards in API payload
- Homepage news pool increased to 72 scored clusters (was 56)

### Clustering
- Recluster/repair-split tasks now run unless intel queue is full (800+), not at soft defer (80+)
- Relaxed recluster batch matching and split-cluster merge thresholds to combine near-duplicate singletons
- Multi-source clusters get ranking boost on homepage; singletons penalized more strongly
- Recluster every 20 min, repair-split every 30 min; new `boost_homepage_cluster_supply_task`

### Frontend
- Homepage developing section shows up to 6 featured + 4 compact items (was 4 + 2)

## v8.3.0 (2026-06-15)

### Synthesis quality
- Relaxed fact-grounding gate: allow up to 2 soft-ungrounded numbers in full mode (was 1), with thousands-separator normalization and year-token handling
- Synthesis prompts now explicitly forbid inventing numbers, percentages, or scores not present in sources
- New `prioritize_homepage_syntheses_task` enqueues full synthesis for homepage-visible clusters missing or stale summaries (every 15 min)

## v8.2.3 (2026-06-14)

### Frontend & UX
- Mobile header: centered logo, symmetric top bar grid, and responsive logo sizing
- Hide duplicate in-header search on mobile (floating FAB only); collapse utilities into `⋯` menu from 768px down
- Keep discovery nav pinned on mobile scroll; logo shrinks from center in compact mode

## v8.2.2 (2026-06-14)

### Fixes
- Personalized news semantic search now filters by `MK`/`RS` country codes (was lowercase, breaking MK sync)
- MK briefing lead extraction recognizes Cyrillic `големата слика` heading
- `NewsCard` transliterates Cyrillic titles/summaries on SR and uses `sr-Latn-RS` date locale
- Cluster research UI wired into deep-tools; locale-aware topic label and MK Cyrillic API errors
- Concept onboarding waits for consent dismissal and allows more homepage sessions before suppressing
- Synthesis test mocks updated for fact-grounding gate and history-context isolation

## v8.2.1 (2026-06-14)

### Frontend & UX
- Lead freshness badge hidden on mobile when footer already shows time
- Concept tour deferred until feed scroll on first visit; second-visit fallback retained
- Lead verification strip collapsed on mobile (chip details expand on tap)

## v8.2.0 (2026-06-14)

### Frontend & UX
- Feed cards show at most one signal badge; mobile hides trust chips, signal rows, and conflict previews on non-lead cards
- Za Vas cold-start merges briefing teaser, onboarding, and email signup into one unified panel
- Homepage first visit on mobile: lead and feed surface first; media-analysis CTA and start-here guide move below the fold
- Lead story kicker quieted on mobile (synthesis/status/freshness badges hidden; time stays in footer)

## v8.1.0 (2026-06-14)

### Synthesis intelligence
- Fast-mode syntheses now schedule a deferred full-quality upgrade (~20 min)
- Quality-aware provider routing uses rolling synthesis scores
- Fact grounding gate rejects ungrounded numbers and sports scores
- Local source-comparison analysis is injected into LLM prompts
- Per-language historical context for MK and SR syntheses
- Maintenance jobs: low-score refresh, cluster synthesis catch-up, ingestion freshness recovery
- Inline `[1]`/`[2]` citation markers now link to the source footer on cluster pages

### Frontend & UX
- Mobile feed density reduced; cookie banner footprint shrunk
- Homepage, cluster page, and header UI polish
- Mobile header layout fix for branding and nav alignment

### Ops
- `intel-heavy` worker concurrency defaults to 6 (configurable via `INTEL_HEAVY_CONCURRENCY`)
- Synthesis tasks prioritized in intel-heavy queue grooming

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
