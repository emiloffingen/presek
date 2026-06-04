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
        description="Refresh today's local/fallback synthesis rows using the current synthesis logic."
    )
    parser.add_argument(
        "--provider",
        action="append",
        default=["local", "enhanced_fallback"],
        help="Generation provider to refresh. Can be repeated. Default: local and enhanced_fallback.",
    )
    parser.add_argument("--cluster-id", action="append", help="Specific cluster ID to refresh. Can be repeated.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of clusters to process.")
    parser.add_argument("--dry-run", action="store_true", help="List clusters without regenerating synthesis.")
    parser.add_argument(
        "--delete-first",
        action="store_true",
        help="Delete existing summaries before regenerating. Off by default because interrupted runs can leave gaps.",
    )
    return parser.parse_args()


def _load_cluster_ids(args):
    if args.cluster_id:
        return list(dict.fromkeys(args.cluster_id))

    sql = """
        SELECT DISTINCT cluster_id
        FROM cluster_summaries
        WHERE created_at >= CURRENT_DATE
          AND generation_provider = ANY(%s)
        ORDER BY cluster_id
    """
    rows = db.execute(sql, (args.provider,))
    cluster_ids = [row["cluster_id"] for row in rows]
    if args.limit and args.limit > 0:
        cluster_ids = cluster_ids[: args.limit]
    return cluster_ids


def main():
    args = _parse_args()
    print("--- Starting Today's Synthesis Refresh ---")
    print(f"Providers: {args.provider}")
    print(f"Delete first: {args.delete_first}")

    cluster_ids = _load_cluster_ids(args)
    print(f"Found {len(cluster_ids)} clusters to refresh: {cluster_ids}")

    if args.dry_run:
        print("--- Dry run complete; no synthesis was regenerated. ---")
        return

    for idx, cid in enumerate(cluster_ids, 1):
        print(f"\n[{idx}/{len(cluster_ids)}] Processing cluster {cid}...")

        try:
            if args.delete_first:
                print(f"  Clearing existing summaries for {cid}...")
                db.execute("DELETE FROM cluster_summaries WHERE cluster_id = %s", (cid,), fetch=False)

            print("  Triggering synthesize_cluster_task...")
            synthesize_cluster_task(cid, None, fast_mode=False)
            print("  Task finished.")

            # Verify new status
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
