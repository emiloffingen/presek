#!/usr/bin/env python3
"""Run one Presek ingestion + synthesis cycle in-process, then exit.

Replaces an always-on Celery worker/beat on hosts that can only run short
scheduled jobs (e.g. GitHub Actions cron). Celery is switched to eager mode,
so every ``.delay()`` / ``.apply_async()`` a task fans out runs inline in this
process instead of being queued. Redis is still used for locks and caches.

Each step is guarded by a wall-clock budget: once ``--budget`` minutes are
spent, remaining steps are skipped (they run again next cycle). A failing step
is logged and the cycle continues.

Usage:
    python scripts/batch_worker.py [--budget 20] [--only STEP ...] [--list]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

log = logging.getLogger("batch_worker")

# (step name, task name, kwargs) in pipeline order: ingest -> crawl -> embed ->
# cluster -> overview -> synthesize -> quality. Queue-pruning beat tasks are
# omitted: in eager mode nothing is ever queued.
EVERY_RUN = [
    ("ingest", "tasks.ingestion_task.run_ingestion", {}),
    ("deferred-crawls", "tasks.maintenance.catch_up_deferred_crawls_task", {}),
    ("embed", "tasks.maintenance.embed_recent_articles_task", {}),
    ("recluster", "tasks.extractive.recluster_recent_articles_task", {}),
    ("repair-clusters", "tasks.extractive.repair_split_clusters_task", {}),
    ("extractive", "tasks.summarization.build_extractive_clusters_task", {}),
    ("homepage-supply", "tasks.maintenance.boost_homepage_cluster_supply_task", {}),
    ("homepage-synth", "tasks.maintenance.prioritize_homepage_syntheses_task", {}),
    ("auto-summarize", "tasks.intelligence.auto_summarize_task", {}),
    ("upgrade-to-ai", "tasks.summarization.upgrade_extractive_to_ai_task", {}),
    ("catch-up-synth", "tasks.maintenance.catch_up_cluster_syntheses_task", {}),
    ("catch-up-summaries", "tasks.maintenance.catch_up_recent_summaries_task", {}),
    ("stuck-fast", "tasks.maintenance.upgrade_stuck_fast_syntheses_task", {}),
    ("quality", "tasks.maintenance.refresh_synthesis_quality_task", {}),
    ("fallback", "tasks.maintenance.refresh_fallback_syntheses_task", {}),
    ("low-score", "tasks.maintenance.refresh_low_score_syntheses_task", {}),
    ("self-heal", "tasks.maintenance.self_heal_low_score_syntheses_task", {}),
    ("sentiment", "tasks.extractive.refine_knowledge_graph_sentiment_task", {}),
    ("freshness", "tasks.maintenance.ensure_ingestion_freshness_task", {}),
]

# Steps that only run when the cycle starts in a given UTC hour.
HOURLY = {
    0: [("backfill-sr", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "sr"}),
        ("backfill-mk", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "mk"})],
    3: [("prune-db", "tasks.maintenance.run_prune_db", {})],
    6: [("backfill-sr", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "sr"}),
        ("backfill-mk", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "mk"})],
    12: [("backfill-sr", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "sr"}),
         ("backfill-mk", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "mk"})],
    18: [("backfill-sr", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "sr"}),
         ("backfill-mk", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "mk"})],
}


def plan(hour: int) -> list[tuple[str, str, dict]]:
    return EVERY_RUN + HOURLY.get(hour, [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--budget", type=float, default=float(os.environ.get("BATCH_BUDGET_MINUTES", "20")),
                    help="wall-clock minutes before remaining steps are skipped")
    ap.add_argument("--only", nargs="+", metavar="STEP", help="run only these step names")
    ap.add_argument("--list", action="store_true", help="list steps and verify task names, then exit")
    args = ap.parse_args()

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from core.celery_app import celery_app

    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    celery_app.loader.import_default_modules()  # register tasks from `include=`

    steps = plan(datetime.now(timezone.utc).hour)
    if args.only:
        steps = [s for s in steps if s[0] in args.only]

    missing = [task for _, task, _ in steps if task not in celery_app.tasks]
    if args.list or missing:
        for name, task, kwargs in steps:
            mark = "MISSING" if task in missing else "ok"
            print(f"{mark:8} {name:20} {task} {kwargs or ''}")
        return 1 if missing else 0

    deadline = time.monotonic() + args.budget * 60
    failed, skipped = [], []
    for name, task, kwargs in steps:
        if time.monotonic() >= deadline:
            skipped.append(name)
            continue
        t0 = time.monotonic()
        try:
            celery_app.tasks[task].apply(kwargs=kwargs, throw=True)
            log.info("step %s ok (%.1fs)", name, time.monotonic() - t0)
        except Exception:
            failed.append(name)
            log.error("step %s failed (%.1fs)\n%s", name, time.monotonic() - t0, traceback.format_exc())

    log.info("cycle done: %d steps, failed=%s skipped(budget)=%s", len(steps), failed or "-", skipped or "-")
    # Only fail the job when nothing succeeded; single-step failures are normal noise.
    return 1 if failed and len(failed) == len(steps) - len(skipped) else 0


if __name__ == "__main__":
    sys.exit(main())
