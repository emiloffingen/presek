"""Regenerate synthesis for the clusters that actually appear on the homepage.

Homepage-only by construction: it reuses ``_collect_homepage_synthesis_targets``
(hero sections first) and regenerates only those rows, using the full provider
cascade (``force_llm``) instead of deterministic ``enhanced_fallback`` output.
Intended to run on a host that can reach the local API and holds the AI keys.

Example (bounded trial):
    python scripts/synthesize_homepage.py --limit 3
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import db_manager as db
from tasks.intelligence.synthesis_pipeline import run_cluster_synthesis
from tasks.intelligence.synthesis_prompt import _build_cluster_synthesis_content, _load_cluster_articles_for_synthesis
from tasks.maintenance import _collect_homepage_synthesis_targets


def _parse_args():
    parser = argparse.ArgumentParser(description="Regenerate homepage cluster syntheses via the real cascade.")
    parser.add_argument("--limit", type=int, default=0, help="Max clusters to process (0 = all).")
    parser.add_argument("--cluster-id", action="append", help="Restrict to specific cluster IDs.")
    parser.add_argument("--provider", help="Force a primary provider (e.g. gemini3); router default otherwise.")
    parser.add_argument("--fast", action="store_true", help="Use fast mode (shorter output).")
    parser.add_argument(
        "--no-force-llm", action="store_true", help="Allow deterministic fallback instead of forcing an LLM."
    )
    parser.add_argument("--dry-run", action="store_true", help="List targets without regenerating.")
    parser.add_argument(
        "--pause",
        type=float,
        default=3.0,
        help="Seconds to wait between clusters so the free-tier providers' per-minute limits are not hit in a burst.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Extra passes over clusters whose synthesis persisted nothing (0 disables).",
    )
    parser.add_argument(
        "--retry-wait", type=float, default=90.0, help="Seconds to wait before each retry pass (rate limits recover)."
    )
    return parser.parse_args()


def _close_pools():
    for attr in ("_pool", "_read_pool"):
        pool = getattr(db, attr, None)
        if pool is not None:
            try:
                pool.close()
            except Exception:
                pass


def _targets(args):
    if args.cluster_id:
        return list(dict.fromkeys(str(cid).strip() for cid in args.cluster_id if str(cid).strip()))
    targets = _collect_homepage_synthesis_targets()
    if args.limit and args.limit > 0:
        targets = targets[: args.limit]
    return targets


def _summarize(cid):
    return db.execute(
        "SELECT lang, generation_provider, generation_model FROM cluster_summaries WHERE cluster_id = %s",
        (cid,),
    )


def _run(args):
    targets = _targets(args)
    print(f"homepage synthesis targets: {len(targets)}")
    if args.dry_run or not targets:
        for cid in targets:
            print(cid)
        return

    if args.provider:
        from core.llm_router import SmartModelRouter

        SmartModelRouter.route_cluster = staticmethod(lambda _articles, lang="sr": args.provider)
        print(f"forcing primary provider: {args.provider}")

    force_llm = not args.no_force_llm
    done, pending = _pass(targets, args, force_llm)
    upgraded = len(done)
    for attempt in range(1, max(0, args.retries) + 1):
        if not pending:
            break
        print(
            f"retrying {len(pending)} cluster(s) that persisted nothing in {args.retry_wait:g}s "
            f"(attempt {attempt}/{args.retries})",
            flush=True,
        )
        time.sleep(args.retry_wait)
        done, pending = _pass(pending, args, force_llm)
        upgraded += len(done)
    failed = len(pending)
    print(f"done: upgraded {upgraded}, failed {failed}, of {len(targets)}")
    if failed and upgraded == 0:
        raise SystemExit(1)


def _synthesize_one(cid, args, force_llm):
    """True when the cluster's synthesis was persisted."""
    try:
        rows = _load_cluster_articles_for_synthesis(cid)
        content = _build_cluster_synthesis_content(rows)
        persisted = run_cluster_synthesis(cid, content, fast_mode=args.fast, force_llm=force_llm)
        if persisted is False:
            # Every language failed inside the pipeline (errors are logged there); the cluster
            # keeps its previous summary. Do not report it as upgraded.
            print("    error: nothing was persisted (see the synthesis errors above)")
            return False
        for row in _summarize(cid) or []:
            print(f"    -> {row['lang']}: {row['generation_provider']} / {row['generation_model']}")
        return True
    except Exception as exc:
        print(f"    error: {exc}")
        return False


def _pass(cluster_ids, args, force_llm):
    """One pass over the clusters, pausing between them. Returns (persisted_ids, failed_ids)."""
    persisted, failed = [], []
    for idx, cid in enumerate(cluster_ids, 1):
        if idx > 1 and args.pause > 0:
            time.sleep(args.pause)
        print(f"[{idx}/{len(cluster_ids)}] {cid} (force_llm={force_llm}) ...", flush=True)
        (persisted if _synthesize_one(cid, args, force_llm) else failed).append(cid)
    return persisted, failed


def main():
    args = _parse_args()
    try:
        _run(args)
    finally:
        _close_pools()


if __name__ == "__main__":
    main()
