# Implementation Checklist

## Pre-Flight
- [ ] `git checkout -b simplify/mk-only-minimal-ai`
- [ ] `git tag pre-simplify`
- [ ] `git push --tags`

## Step 1: Database Migration
- [ ] Create `migrations/versions/simplify_mk_only.py`
- [ ] Drop tables: `feed_sources`, `cluster_summary_history`, `cluster_entities`, `knowledge_entities`, `knowledge_relationships`, `entity_mentions_daily`, `entity_knowledge`, `storylines_v2`, `storyline_clusters_v2`, `synced_reader_profiles`, `synced_delivery_subscriptions`, `suggestion_surface_events`, `daily_briefings`, `saved_insights`
- [ ] Drop columns: `articles.embedding`, `cluster_metadata.centroid`, `cluster_summaries.lang`, `subscribers.locale`
- [ ] Remove Serbian sources from `sources` table
- [ ] Test: `alembic upgrade head`

## Step 2: Backend File Deletions
- [ ] Delete `core/ai_engine.py`
- [ ] Delete `core/embeddings.py`
- [ ] Delete `core/clustering.py`
- [ ] Delete `core/entities.py`
- [ ] Delete `core/synthesis_quality.py`
- [ ] Delete `core/synthesis_trace.py`
- [ ] Delete `core/personalization_score.py`
- [ ] Delete `core/personalization_reasons.py`
- [ ] Delete `core/topic_discovery.py`
- [ ] Delete `core/editorial_quality.py`
- [ ] Delete `core/copy_quality.py`
- [ ] Delete `core/cross_lingual.py`
- [ ] Delete `core/research_helpers.py`
- [ ] Delete `core/briefing_quick_read.py`
- [ ] Delete `core/digest.py`
- [ ] Delete `core/audio_service.py`
- [ ] Delete `core/services/research_service.py`
- [ ] Delete `nlp/sentiment.py`
- [ ] Delete `nlp/keywords.py`
- [ ] Delete `nlp/extraction.py`
- [ ] Delete `nlp/generation.py`
- [ ] Delete `nlp/ai_engine.py`
- [ ] Delete `nlp/local_analyst.py`
- [ ] Delete `tasks/intelligence/` (entire directory)
- [ ] Delete `tasks/synthesis_sanitize.py`
- [ ] Delete `tasks/delivery/briefing.py`
- [ ] Delete `tasks/delivery/briefing_alerts.py`
- [ ] Delete `tasks/delivery/briefing_quality.py`
- [ ] Delete `routes/intelligence.py`

## Step 3: Backend File Modifications

### core/api_fast.py
- [ ] Remove AI provider imports from lifespan
- [ ] Remove `routes.intelligence` router include
- [ ] Simplify health endpoint (remove synthesis quality)

### core/celery_app.py
- [ ] Remove queues: `fast-track`, `synthesis`, `intel-heavy`, `delivery`, `maintenance`
- [ ] Keep queues: `celery`, `ingestion`, `ingestion-crawl`, `summarization`
- [ ] Remove beat entries: all except `ingest-regular-feeds`, `auto-summarize-clusters`, `prune-database`, `auto-repair-sources`
- [ ] Remove worker memory limits

### core/config.py
- [ ] Remove AI provider config (OPENAI_API_KEY, PROVIDER_FALLBACK_ORDER, etc.)
- [ ] Remove Serbian language config (`LANGUAGE_CONFIG["sr"]`)
- [ ] Remove personalization config
- [ ] Remove synthesis/clustering thresholds
- [ ] Keep: DATABASE_URL, REDIS_URL, SECRET_KEY, SMTP, basic feature flags

### core/health.py
- [ ] Remove `get_synthesis_quality_snapshot()`
- [ ] Keep: DB health, Redis health, article stats

### routes/home.py
- [ ] Remove synthesis hero cluster logic
- [ ] Remove knowledge entities loading
- [ ] Remove personalization/for-you logic
- [ ] Simplify to: latest clusters + trending + basic stats

### routes/news.py
- [ ] Remove semantic search (pgvector)
- [ ] Remove synthesis display from cluster detail
- [ ] Keep: keyword search (tsvector), article listing, cluster detail

### routes/admin.py
- [ ] Remove synthesis task triggers
- [ ] Remove synthesis trace endpoints
- [ ] Keep: dashboard, queue health, DB health, token management

### routes/stats.py
- [ ] Remove sentiment-trends, mood endpoints
- [ ] Remove daily-briefing, on-this-day endpoints
- [ ] Keep: basic stats, archive, heatmap, source listing

### routes/system.py
- [ ] Remove navigation top-entities
- [ ] Keep: health, proxy, weather, trending, categories

### routes/profile.py
- [ ] Remove personalized-news endpoint
- [ ] Keep: sync, delivery, VAPID key

### tasks/ingestion_task.py
- [ ] Remove AI task dispatch chains after ingestion
- [ ] Keep: crawl_article_task, auto_repair_sources_task, run_ingestion

### tasks/maintenance.py
- [ ] Remove synthesis maintenance tasks
- [ ] Keep: run_prune_db, invalidate caches, prune queues

### tasks/__init__.py
- [ ] Remove intelligence task re-exports
- [ ] Keep: ingestion, maintenance task re-exports

## Step 4: Create New Files

### nlp/summarizer.py (NEW)
- [ ] Create simplified Gemma 2B wrapper
- [ ] `summarize_article(title, content) -> str`
- [ ] `synthesize_cluster(articles) -> dict`
- [ ] No provider cascade, no grammar constraints
- [ ] Simple prompt -> JSON parse -> store

### tasks/summarization.py (NEW)
- [ ] `summarize_article_task(article_id)` Celery task
- [ ] `synthesize_cluster_task(cluster_id)` Celery task
- [ ] Both call `nlp/summarizer.py`

## Step 5: Frontend Deletions
- [ ] Delete `web/src/pages/briefing.astro`
- [ ] Delete `web/src/pages/pulse.astro`
- [ ] Delete `web/src/pages/stats.astro` (redirect to /archive)
- [ ] Delete `web/src/pages/graf.astro`
- [ ] Delete `web/src/pages/grafik.astro`
- [ ] Delete `web/src/pages/for-you.astro`
- [ ] Delete `web/src/pages/subjekt/[name].astro`
- [ ] Delete `web/src/pages/debug/recommendations.astro`
- [ ] Delete `web/src/pages/admin/index.astro`
- [ ] Delete `web/src/pages/admin/status.astro`
- [ ] Delete all `/mk/` duplicate pages
- [ ] Delete AI component islands (25+ files)

## Step 6: Dependency Cleanup
- [ ] Update `pyproject.toml`: remove torch, spacy, keybert, sentence-transformers, fasttext, numba, edge-tts, gTTS, omnivoice, playwright, numpy, pgvector
- [ ] Keep: llama-cpp-python, fastapi, celery, redis, psycopg, feedparser, trafilatura
- [ ] Run `uv lock` to regenerate lockfile
- [ ] Verify venv size < 600MB

## Step 7: Configuration Cleanup
- [ ] Update `.env.example`: remove AI provider vars
- [ ] Add `LOCAL_MODEL_PATH` for Gemma 2B
- [ ] Add `MODEL_THREADS=2` for Termux
- [ ] Update `start.sh`: simplify worker startup

## Step 8: Testing
- [ ] `uv run pytest tests/ -x --timeout=60 -q`
- [ ] `cd web && npm test`
- [ ] Manual: start services, verify homepage loads
- [ ] Manual: verify search works
- [ ] Manual: verify archive loads
- [ ] Manual: verify RSS feed generates

## Step 9: Deployment
- [ ] Update systemd units (3 services)
- [ ] Test on production server
- [ ] Monitor logs for 24 hours
- [ ] Verify Cloudflare tunnel works

## Rollback Plan
If anything breaks:
```bash
git checkout main
git branch -D simplify/mk-only-minimal-ai
alembic downgrade pre-simplify
```
