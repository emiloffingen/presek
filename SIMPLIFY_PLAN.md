# Presek Simplification Plan

**Goal:** MK-only news aggregator with minimal local AI (Gemma 2B only)
**Target:** Runs on Termux/proot with ~4GB RAM

---

## Architecture Overview

### Before (Current)
- 119 Python files
- 9 systemd services
- 7 Celery worker types
- 25+ database tables
- 57 frontend pages (SR + MK)
- 6GB venv (PyTorch, spaCy, llama-cpp, sentence-transformers)
- Multiple cloud LLM providers (Gemini, Groq, Nvidia, OpenRouter)
- ~200 RSS feeds (SR + MK + International)

### After (Simplified)
- ~30 Python files
- 3 systemd services (api, worker, beat)
- 2 Celery workers (ingestion + summarization)
- 10 database tables
- ~25 frontend pages (MK only)
- ~500MB venv (llama-cpp-python only)
- Local Gemma 2B only (no cloud APIs)
- ~33 RSS feeds (MK sources only)

---

## Phase 1: Database Schema Simplification

### Tables to KEEP (10 tables)

| Table | Purpose | Changes |
|---|---|---|
| `articles` | Core article store | Remove `embedding` column (vector 384), keep `search_vector` (tsvector) |
| `sources` | RSS source config | Keep as-is, remove Serbian sources |
| `cluster_summaries` | AI-generated summaries | Remove `lang` column (MK only), keep single-language columns |
| `cluster_metadata` | Cluster tags/topics | Remove `centroid` column (vector 384) |
| `subscribers` | Newsletter subscribers | Remove `locale` column (MK only) |
| `failed_tasks` | Dead letter queue | Keep as-is |
| `system_metadata` | Key-value config | Keep as-is |
| `advertising_campaigns` | Ad campaigns | Keep as-is |
| `delivery_tracking_events` | Send tracking | Keep as-is |
| `mv_article_stats` | Materialized view | Keep as-is |

### Tables to DELETE (15 tables)

| Table | Reason |
|---|---|
| `feed_sources` | Duplicate of `sources` (newer table, consolidate to `sources`) |
| `cluster_summary_history` | Version history not needed for minimal version |
| `cluster_entities` | Entity extraction removed |
| `knowledge_entities` | Knowledge graph removed |
| `knowledge_relationships` | Knowledge graph removed |
| `entity_mentions_daily` | Entity tracking removed |
| `entity_knowledge` | Entity knowledge removed |
| `storylines_v2` | Storyline tracking removed |
| `storyline_clusters_v2` | Storyline tracking removed |
| `synced_reader_profiles` | Personalization removed |
| `synced_delivery_subscriptions` | Personalized delivery removed |
| `suggestion_surface_events` | UI tracking removed |
| `daily_briefings` | AI briefings removed |
| `saved_insights` | Research insights removed |

### Migration Strategy

Create a single migration that:
1. Drops all tables marked for deletion
2. Drops `embedding` column from `articles`
3. Drops `centroid` column from `cluster_metadata`
4. Drops `lang` from `cluster_summaries`
5. Drops `locale` from `subscribers`
6. Consolidates `feed_sources` into `sources` (if any data exists)
7. Recreates indexes for the simplified schema

---

## Phase 2: Backend Simplification

### Files to DELETE entirely

**Core (14 files):**
```
core/ai_engine.py              # Multi-provider LLM router
core/embeddings.py             # Sentence-transformer embeddings
core/clustering.py             # Vector-based clustering
core/entities.py               # Entity extraction
core/synthesis_quality.py      # Synthesis quality scoring
core/synthesis_trace.py        # Synthesis debugging
core/personalization_score.py  # Personalization scoring
core/personalization_reasons.py # Personalization explanations
core/topic_discovery.py        # AI topic discovery
core/editorial_quality.py      # Editorial quality scoring
core/copy_quality.py           # Copy quality checking
core/cross_lingual.py          # SR<->MK translation
core/research_helpers.py       # Research query helpers
core/briefing_quick_read.py    # Briefing quick-read mode
```

**NLP (6 files):**
```
nlp/sentiment.py               # Sentiment analysis
nlp/keywords.py                # Keyword extraction (KeyBERT)
nlp/extraction.py              # Entity extraction (spaCy)
nlp/generation.py              # Text generation
nlp/local_analyst.py           # REPLACE with simplified version
nlp/ai_engine.py               # NLP AI engine
```

**Tasks (26 files):**
```
tasks/intelligence/            # ENTIRE DIRECTORY (19 files)
tasks/synthesis_sanitize.py    # Synthesis sanitization
tasks/delivery/briefing.py     # AI briefing generation
tasks/delivery/briefing_alerts.py  # AI breaking alerts
tasks/delivery/briefing_quality.py # AI briefing quality
```

**Routes (1 file):**
```
routes/intelligence.py         # Entire intelligence router
```

**Frontend (20+ pages):**
```
web/src/pages/briefing.astro
web/src/pages/pulse.astro
web/src/pages/stats.astro (redirect to /archive)
web/src/pages/graf.astro
web/src/pages/grafik.astro
web/src/pages/for-you.astro
web/src/pages/subjekt/[name].astro
web/src/pages/debug/recommendations.astro
web/src/pages/admin/index.astro
web/src/pages/admin/status.astro
web/src/pages/mk/briefing.astro
web/src/pages/mk/pulse.astro
web/src/pages/mk/graf.astro
web/src/pages/mk/subjekt/[name].astro
web/src/pages/mk/debug/recommendations.astro
web/src/pages/mk/admin/index.astro
web/src/pages/mk/admin/status.astro
```

**Frontend Components (25+ islands):**
```
web/src/components/KnowledgeGraphIsland.tsx
web/src/components/IntelligenceGraph.tsx
web/src/components/MediaPulseRadar.tsx
web/src/components/NationalMoodIsland.tsx
web/src/components/EntityIsland.tsx
web/src/components/EntityContextCard.tsx
web/src/components/PulseClientContainer.tsx
web/src/components/PulseLandscapeIsland.tsx
web/src/components/pulse/SentimentRadarIsland.tsx
web/src/components/pulse/PulseHeatmapIsland.tsx
web/src/components/pulse/DivergenceGaugeIsland.tsx
web/src/components/SourceComparisonIsland.tsx
web/src/components/SourceMapIsland.tsx
web/src/components/ForYouPageIsland.tsx
web/src/components/ForYouIsland.tsx
web/src/components/ForYouBriefingCard.tsx
web/src/components/BriefingDeliveryIsland.tsx
web/src/components/MorningEmailSignup.tsx
web/src/components/StorylineHistoryIsland.tsx
web/src/components/ClusterHistoryIsland.tsx
web/src/components/ClusterFollowSuggestionsIsland.tsx
web/src/components/TopicFollowSuggestionsIsland.tsx
web/src/components/HomeRailSuggestionsIsland.tsx
web/src/components/PersonalizationWhyChip.tsx
web/src/components/SettingsProfileIsland.tsx
web/src/components/briefing/* (all briefing components)
```

### Files to MODIFY

**Core files to simplify:**

1. `core/api_fast.py`
   - Remove AI provider imports from lifespan
   - Remove intelligence router include
   - Simplify health endpoint (remove synthesis quality check)

2. `core/celery_app.py`
   - Remove 6 queues, keep only: `celery`, `ingestion`, `ingestion-crawl`, `summarization`
   - Remove 20+ beat schedule entries, keep only:
     - `ingest-regular-feeds` (10 min)
     - `auto-summarize-clusters` (15 min)
     - `prune-database` (3:00 UTC daily)
     - `auto-repair-sources` (6:00 UTC daily)
   - Remove worker memory limits (no PyTorch to worry about)

3. `core/config.py`
   - Remove all AI provider config (OPENAI_API_KEY, PROVIDER_FALLBACK_ORDER, etc.)
   - Remove Serbian language config
   - Remove personalization config
   - Keep: DATABASE_URL, REDIS_URL, SECRET_KEY, SMTP config, basic feature flags

4. `core/health.py`
   - Remove synthesis quality snapshot
   - Keep: DB health, Redis health, basic article stats

5. `routes/home.py`
   - Remove synthesis hero cluster logic
   - Remove knowledge entities
   - Remove personalization/for-you logic
   - Simplify to: latest clusters + trending + basic stats

6. `routes/news.py`
   - Remove semantic search (pgvector)
   - Remove synthesis display from cluster detail
   - Keep: basic keyword search (tsvector), article listing, cluster detail

7. `routes/admin.py`
   - Remove synthesis task triggers
   - Remove synthesis trace endpoints
   - Keep: dashboard, queue health, DB health, token management

8. `routes/stats.py`
   - Remove sentiment-trends, mood endpoints
   - Remove daily-briefing, on-this-day endpoints
   - Keep: basic stats, archive, heatmap, source listing

9. `routes/system.py`
   - Remove navigation top-entities (AI-extracted)
   - Keep: health, proxy, weather, trending, categories

10. `routes/profile.py`
    - Remove personalized-news endpoint
    - Keep: sync, delivery, VAPID key

11. `tasks/ingestion_task.py`
    - Remove AI task dispatch chains after ingestion
    - Keep: crawl_article_task, auto_repair_sources_task, run_ingestion

12. `tasks/maintenance.py`
    - Remove synthesis maintenance tasks
    - Keep: run_prune_db, invalidate caches, prune queues

### Files to CREATE

1. `nlp/summarizer.py` (NEW - simplified version of local_analyst.py)
   - Single Gemma 2B model via llama-cpp-python
   - Two tasks: `summarize_article` and `synthesize_cluster`
   - No provider cascade, no quality gates, no grammar constraints
   - Simple prompt -> parse JSON response -> store

2. `tasks/summarization.py` (NEW - replaces intelligence/summarization.py)
   - `summarize_article_task`: Generate article summary
   - `synthesize_cluster_task`: Generate cluster synthesis
   - Both call `nlp/summarizer.py`

---

## Phase 3: Frontend Simplification

### Pages to KEEP (MK only, ~25 pages)

| Page | Path | Description |
|---|---|---|
| Homepage | `/index.astro` | Simplified: latest clusters, trending, no synthesis hero |
| Archive | `/archive.astro` | Date-based article browser |
| Topic | `/tema/[topic].astro` | Topic filtering |
| Cluster Detail | `/cluster/[slug].astro` | Article cluster view (no synthesis) |
| Sources | `/izvori.astro` | Source directory |
| About | `/about.astro` | Static |
| Contact | `/contact.astro` | Static |
| Privacy | `/privacy.astro` | Static |
| Terms | `/terms.astro` | Static |
| Cookies | `/cookies.astro` | Static |
| Editorial | `/editorial.astro` | Static |
| Methodology | `/methodology.astro` | Static |
| Marketing | `/marketing.astro` | Ad booking |
| Marketing Status | `/marketing/status.astro` | Campaign status |
| Support | `/support.astro` | Static |
| Status | `/status.astro` | System status |
| Settings | `/settings.astro` | User settings (simplified) |
| 404 | `/404.astro` | Error page |
| Offline | `/offline.astro` | Offline fallback |
| RSS | `/rss.xml.ts` | Feed generation |
| Sitemap | `/sitemap.xml.ts` | SEO |
| Robots | `/robots.txt.ts` | SEO |
| OG Image | `/og-image.svg.ts` | Social sharing |
| Cluster OG | `/og/cluster/[id].svg.ts` | Social sharing |
| Manifest | `/manifest.json.ts` | PWA |

### Pages to DELETE

All SR-only pages, all AI-dependent pages (briefing, pulse, graf, for-you, subjekt, admin, debug).

### Components to KEEP

- Article cards, cluster cards, navigation, footer, header
- Search bar (keyword search only)
- Archive calendar/heatmap
- Source listing components
- Basic ad slots

### Components to DELETE

All AI visualization islands (knowledge graph, pulse radar, mood, entity, personalization, briefing delivery).

---

## Phase 4: Dependency Simplification

### pyproject.toml changes

**Remove from dependencies:**
```
numpy              # Only needed for vector math
pgvector           # Only needed for vector search
sentence-transformers  # Embeddings
spacy              # NER
keybert            # Keywords
fasttext           # Language detection
numba              # JIT compilation
edge-tts           # TTS
gTTS               # TTS
omnivoice          # TTS
playwright         # Browser scraping (use trafilatura only)
```

**Keep:**
```
llama-cpp-python   # Local Gemma inference
fastapi            # Web framework
uvicorn            # ASGI server
celery             # Task queue
redis              # Broker
psycopg            # PostgreSQL
sqlalchemy         # ORM
alembic            # Migrations
feedparser         # RSS parsing
trafilatura        # Content extraction
bleach             # HTML sanitization
httpx              # HTTP client
pillow             # Image processing
pydantic           # Validation
sentry-sdk         # Error tracking
prometheus-client  # Metrics
pywebpush          # Push notifications
stripe             # Payments
```

**Result:** ~500MB venv instead of ~6GB

---

## Phase 5: Deployment Simplification

### Systemd Services (3 instead of 9)

1. `presek-api.service` - FastAPI + Astro SSR
2. `presek-worker.service` - Celery worker (ingestion + summarization)
3. `presek-beat.service` - Celery beat scheduler

### Docker Compose (optional, for local dev)

```yaml
services:
  api:
    build: .
    ports: ["5001:5001"]
    depends_on: [postgres, redis]
  worker:
    build: .
    command: celery -A core.celery_app worker
    depends_on: [postgres, redis]
  postgres:
    image: pgvector/pgvector:pg16
  redis:
    image: redis:7-alpine
```

### Cloudflare Tunnel

Same setup, but simpler:
- Tunnel points to `http://localhost:5001` (API serves everything)
- No separate Astro SSR process needed (FastAPI serves static files)

---

## Implementation Order

### Step 1: Create branch and backup
```bash
git checkout -b simplify/mk-only-minimal-ai
git tag pre-simplify
```

### Step 2: Database migration
- Create migration to drop tables and columns
- Test on dev database

### Step 3: Backend cleanup
- Delete files marked for deletion
- Modify files marked for modification
- Create new summarizer

### Step 4: Frontend cleanup
- Delete pages and components
- Simplify remaining pages

### Step 5: Dependency cleanup
- Update pyproject.toml
- Regenerate uv.lock
- Test venv size

### Step 6: Configuration cleanup
- Update .env.example
- Remove unused env vars
- Simplify config.py

### Step 7: Testing
- Run backend tests
- Run frontend tests
- Manual smoke test

### Step 8: Deployment
- Update systemd units
- Test on production
- Monitor for issues

---

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Breaking existing data | Migration tested on backup first |
| Losing useful features | Git tag allows easy rollback |
| Gemma 2B quality too low | Can upgrade to Gemma 4 E2B later |
| Missing Serbian users | Can add SR back later as separate deployment |
| Frontend breakage | Test each page individually |

---

## Success Metrics

| Metric | Before | After |
|---|---|---|
| Python files | 119 | ~30 |
| Venv size | ~6GB | ~500MB |
| RAM usage | ~2GB+ | ~500MB |
| Cold start time | ~30s | ~5s |
| Deploy time | ~5min | ~1min |
| DB tables | 25+ | 10 |
| Celery workers | 7 | 2 |
| Systemd services | 9 | 3 |
| Frontend pages | 57 | ~25 |
| RSS feeds | ~200 | ~33 |
