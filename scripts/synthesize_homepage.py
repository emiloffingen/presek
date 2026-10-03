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
    parser.add_argument("--no-force-llm", action="store_true", help="Allow deterministic fallback instead of forcing an LLM.")
    parser.add_argument("--dry-run", action="store_true", help="List targets without regenerating.")
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
    upgraded = 0
    failed = 0
    for idx, cid in enumerate(targets, 1):
        print(f"[{idx}/{len(targets)}] {cid} (force_llm={force_llm}) ...", flush=True)
        try:
            rows = _load_cluster_articles_for_synthesis(cid)
            content = _build_cluster_synthesis_content(rows)
            run_cluster_synthesis(cid, content, fast_mode=args.fast, force_llm=force_llm)
            for row in _summarize(cid) or []:
                print(f"    -> {row['lang']}: {row['generation_provider']} / {row['generation_model']}")
            upgraded += 1
        except Exception as exc:
            failed += 1
            print(f"    error: {exc}")
    print(f"done: upgraded {upgraded}, failed {failed}, of {len(targets)}")
    if failed and upgraded == 0:
        raise SystemExit(1)


def main():
    args = _parse_args()
    try:
        _run(args)
    finally:
        _close_pools()


if __name__ == "__main__":
    main()
