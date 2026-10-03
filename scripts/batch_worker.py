#!/usr/bin/env python3
"""Run one Presek ingestion + synthesis cycle, then exit.

Replaces an always-on Celery worker/beat on hosts that can only run short
scheduled jobs (e.g. GitHub Actions cron). Celery is switched to eager mode,
so every ``.delay()`` / ``.apply_async()`` a task fans out runs inline in the
child process instead of being queued. Redis is still used for locks and caches.

Each step runs in its own subprocess with the remaining cycle budget (or a
per-step cap) as a hard timeout, so a single slow task is killed instead of
hanging the whole run. Steps are split into a small CORE plus four ROTATING
groups selected from the UTC slot, so heavy work is spread across cycles
without a cursor: slot = hour // BATCH_SLOT_HOURS, group = slot % 4.

BATCH_CORE=0 turns off the CORE steps (hybrid: a host keeps ingest/crawl/embed
and CI only runs the heavy rotating work). --group N forces a group for manual
runs. A step's cap overrides the remaining-budget timeout.

Usage:
    python scripts/batch_worker.py [--budget 20] [--group N] [--only STEP ...] [--list]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

log = logging.getLogger("batch_worker")

# (step, task, kwargs, cap_seconds or None)
CORE = [
    ("ingest", "tasks.ingestion_task.run_ingestion", {}, None),
    ("deferred-crawls", "tasks.maintenance.catch_up_deferred_crawls_task", {}, None),
    ("embed", "tasks.maintenance.embed_recent_articles_task", {}, None),
]

GROUPS = [
    [  # 0: clustering
        ("recluster", "tasks.extractive.recluster_recent_articles_task", {}, 240),
        ("repair-clusters", "tasks.extractive.repair_split_clusters_task", {}, None),
        ("extractive", "tasks.summarization.build_extractive_clusters_task", {}, None),
    ],
    [  # 1: homepage + first synthesis
        ("homepage-supply", "tasks.maintenance.boost_homepage_cluster_supply_task", {}, None),
        ("homepage-synth", "tasks.maintenance.prioritize_homepage_syntheses_task", {}, None),
        ("auto-summarize", "tasks.intelligence.auto_summarize_task", {}, None),
        ("upgrade-to-ai", "tasks.summarization.upgrade_extractive_to_ai_task", {}, None),
    ],
    [  # 2: catch-up
        ("catch-up-synth", "tasks.maintenance.catch_up_cluster_syntheses_task", {}, None),
        ("catch-up-summaries", "tasks.maintenance.catch_up_recent_summaries_task", {}, None),
        ("stuck-fast", "tasks.maintenance.upgrade_stuck_fast_syntheses_task", {}, None),
    ],
    [  # 3: quality
        ("quality", "tasks.maintenance.refresh_synthesis_quality_task", {}, None),
        ("fallback", "tasks.maintenance.refresh_fallback_syntheses_task", {}, None),
        ("low-score", "tasks.maintenance.refresh_low_score_syntheses_task", {}, None),
        ("self-heal", "tasks.maintenance.self_heal_low_score_syntheses_task", {}, None),
        ("sentiment", "tasks.extractive.refine_knowledge_graph_sentiment_task", {}, None),
    ],
]

BACKFILL = [
    ("backfill-sr", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "sr"}, None),
    ("backfill-mk", "tasks.extractive.schedule_backfill_cluster_summaries_task", {"lang": "mk"}, None),
]

SLOT_HOURS = int(os.environ.get("BATCH_SLOT_HOURS", "3"))  # must match the cron cadence


def plan(now: datetime, group: int | None = None) -> list[tuple[str, str, dict, int | None]]:
    if group is None:
        group = (now.hour // SLOT_HOURS) % len(GROUPS)
    steps = list(CORE) if os.environ.get("BATCH_CORE", "1") == "1" else []
    steps += GROUPS[group]
    if now.hour % 6 < SLOT_HOURS:  # first slot of each 6h window
        steps += BACKFILL
    if now.hour // SLOT_HOURS == 3 // SLOT_HOURS:  # slot containing 03:00 UTC
        steps.append(("prune-db", "tasks.maintenance.run_prune_db", {}, None))
    steps.append(("freshness", "tasks.maintenance.ensure_ingestion_freshness_task", {}, 60))
    return steps


def _celery_app():
    from core.celery_app import celery_app

    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    celery_app.loader.import_default_modules()  # register tasks from `include=`
    return celery_app


def _run_single_step(step: str) -> int:
    """Child entrypoint: run exactly one step in eager mode, then exit."""
    task = os.environ["BATCH_STEP_TASK"]
    kwargs = json.loads(os.environ.get("BATCH_STEP_KWARGS") or "{}")
    _celery_app().tasks[task].apply(kwargs=kwargs, throw=True)
    log.info("step %s done", step)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--budget",
        type=float,
        default=float(os.environ.get("BATCH_BUDGET_MINUTES", "20")),
        help="wall-clock minutes before remaining steps are skipped",
    )
    ap.add_argument("--group", type=int, choices=range(len(GROUPS)), help="force a rotation group")
    ap.add_argument("--only", nargs="+", metavar="STEP", help="run only these step names")
    ap.add_argument("--list", action="store_true", help="list steps and verify task names, then exit")
    ap.add_argument("--run-step", metavar="STEP", help=argparse.SUPPRESS)  # internal child mode
    args = ap.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    if args.run_step:
        return _run_single_step(args.run_step)

    now = datetime.now(timezone.utc)
    group = args.group if args.group is not None else (now.hour // SLOT_HOURS) % len(GROUPS)
    steps = plan(now, args.group)
    if args.only:
        steps = [s for s in steps if s[0] in args.only]

    celery_app = _celery_app()
    missing = [task for _name, task, _kwargs, _cap in steps if task not in celery_app.tasks]
    if args.list or missing:
        print(f"group={group} slot_hours={SLOT_HOURS} core={os.environ.get('BATCH_CORE', '1')}")
        for name, task, kwargs, cap in steps:
            mark = "MISSING" if task in missing else "ok"
            print(f"{mark:8} {name:20} cap={cap} {task} {kwargs or ''}")
        return 1 if missing else 0

    deadline = time.monotonic() + args.budget * 60
    self_path = os.path.abspath(__file__)
    failed, skipped = [], []
    for name, task, kwargs, cap in steps:
        remaining = deadline - time.monotonic()
        if remaining <= 2:
            skipped.append(name)
            continue
        # The step runs as a child so a hung task is killed at the timeout
        # instead of blocking the rest of the cycle (and the whole CI job).
        timeout = min(remaining, cap) if cap else remaining
        child_env = dict(os.environ, BATCH_STEP_TASK=task, BATCH_STEP_KWARGS=json.dumps(kwargs))
        t0 = time.monotonic()
        try:
            subprocess.run(
                [sys.executable, self_path, "--run-step", name],
                timeout=timeout,
                check=True,
                env=child_env,
            )
            log.info("step %s ok (%.1fs)", name, time.monotonic() - t0)
        except subprocess.TimeoutExpired:
            failed.append(f"{name}:timeout")
            log.warning("step %s TIMEOUT after %.1fs (cap=%s, child killed)", name, time.monotonic() - t0, cap)
        except subprocess.CalledProcessError as exc:
            failed.append(name)
            log.error("step %s failed (%.1fs, exit %s)", name, time.monotonic() - t0, exc.returncode)

    log.info(
        "cycle done: group=%d steps=%d failed=%s skipped(budget)=%s", group, len(steps), failed or "-", skipped or "-"
    )
    # Only fail the job when nothing succeeded; single-step failures are normal noise.
    return 1 if failed and len(failed) == len(steps) - len(skipped) else 0


if __name__ == "__main__":
    sys.exit(main())
