import argparse
import sys
from pathlib import Path

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import db_manager as db
from tasks.intelligence import synthesize_cluster_task


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Refresh local/fallback synthesis rows using the current synthesis logic."
    )
    parser.add_argument(
        "--provider",
        action="append",
        default=None,
        help="Generation provider to refresh. Can be repeated. Default: local and enhanced_fallback.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Lookback window in days (default: 1 = today only).",
    )
    parser.add_argument("--cluster-id", action="append", help="Specific cluster ID to refresh. Can be repeated.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of clusters to process.")
    parser.add_argument(
        "--queue",
        action="store_true",
        help="Queue Celery synthesis tasks instead of running synchronously.",
    )
    parser.add_argument("--dry-run", action="store_true", help="List clusters without regenerating synthesis.")
    parser.add_argument(
        "--target-provider",
        choices=["nvidia", "local"],
        help="Force regenerated synthesis through a remote provider instead of the router.",
    )
    parser.add_argument(
        "--delete-first",
        action="store_true",
        help="Delete existing summaries before regenerating. Off by default because interrupted runs can leave gaps.",
    )
    return parser.parse_args()


def _load_cluster_ids(args):
    if args.cluster_id:
        return list(dict.fromkeys(args.cluster_id))

    include_missing_provider = "" in args.provider
    sql = """
        SELECT DISTINCT cluster_id
        FROM cluster_summaries
        WHERE created_at >= NOW() - make_interval(days => %s)
          AND (
            generation_provider = ANY(%s)
            OR (%s AND (generation_provider IS NULL OR generation_provider = ''))
          )
        ORDER BY cluster_id
    """
    rows = db.execute(sql, (args.days, args.provider, include_missing_provider))
    cluster_ids = [row["cluster_id"] for row in rows]
    if args.limit and args.limit > 0:
        cluster_ids = cluster_ids[: args.limit]
    return cluster_ids


def main():
    args = _parse_args()
    if args.provider is None:
        args.provider = ["local", "enhanced_fallback"]

    print("--- Starting Synthesis Refresh ---")
    print(f"Window: last {args.days} day(s)")
    print(f"Providers: {args.provider}")
    print(f"Target provider: {args.target_provider or 'router'}")
    print(f"Queue via Celery: {args.queue}")
    print(f"Delete first: {args.delete_first}")

    cluster_ids = _load_cluster_ids(args)
    print(f"Found {len(cluster_ids)} clusters to refresh: {cluster_ids}")

    if args.dry_run:
        print("--- Dry run complete; no synthesis was regenerated. ---")
        return

    if args.target_provider:
        from core.llm_router import SmartModelRouter

        SmartModelRouter.route_cluster = staticmethod(lambda _articles, lang="sr": args.target_provider)

    from tasks.intelligence import _build_cluster_synthesis_content, _load_cluster_articles_for_synthesis

    for idx, cid in enumerate(cluster_ids, 1):
        print(f"\n[{idx}/{len(cluster_ids)}] Processing cluster {cid}...")

        try:
            if args.delete_first:
                print(f"  Clearing existing summaries for {cid}...")
                db.execute("DELETE FROM cluster_summaries WHERE cluster_id = %s", (cid,), fetch=False)

            if args.queue:
                article_rows = _load_cluster_articles_for_synthesis(cid)
                content = _build_cluster_synthesis_content(article_rows)
                if not content:
                    print(f"  Skipping {cid}: no synthesis content available")
                    continue
                print("  Queueing synthesize_cluster_task via Celery...")
                synthesize_cluster_task.delay(cid, content, fast_mode=False)
                print("  Task queued.")
                continue

            print("  Triggering synthesize_cluster_task...")
            synthesize_cluster_task(cid, None, fast_mode=False)
            print("  Task finished.")

            new_rows = db.execute(
                "SELECT lang, generation_provider, generation_model FROM cluster_summaries WHERE cluster_id = %s",
                (cid,),
            )
            for nr in new_rows:
                print(f"  -> Lang: {nr['lang']} | Provider: {nr['generation_provider']} | Model: {nr['generation_model']}")
        except Exception as e:
            print(f"  Error processing cluster {cid}: {e}")

    print("\n--- Synthesis Refresh Complete ---")


if __name__ == "__main__":
    main()
