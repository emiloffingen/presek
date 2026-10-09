import asyncio
import os
import sys

# Ensure project root is in python path
sys.path.append("/home/emiloffingen/presek")

from core.audio_service import AudioService, select_cluster_audio_text
from core.database import db_manager as db
from tasks.intelligence import synthesize_cluster_task


async def regenerate_cluster(cluster_id: str):
    print("\n==================================================")
    print(f"REGENERATING CLUSTER {cluster_id}")
    print("==================================================")

    print(f"Deleting existing cluster summaries for {cluster_id} to force clean AI regeneration...")
    await db.async_execute("DELETE FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,), fetch=False)

    print(f"Triggering synthesize_cluster_task synchronously for {cluster_id}...")
    # Run the task directly
    synthesize_cluster_task(cluster_id, None, fast_mode=False)

    # Verify the new summary
    row = await db.async_execute_one(
        "SELECT generated_article, summary FROM cluster_summaries WHERE cluster_id = %s AND lang = %s",
        (cluster_id, "sr"),
    )

    if not row or (not row.get("generated_article") and not row.get("summary")):
        print(f"Error: AI synthesis failed or returned empty content for {cluster_id}!")
        return

    content = select_cluster_audio_text(row.get("generated_article"), row.get("summary"))
    print(f"\n--- NEW AI GENERATED ARTICLE ({cluster_id}) ---")
    print(content)
    print("--------------------------------\n")

    # Delete the old MP3 file if it exists
    filepath, _ = AudioService.get_cluster_audio_path_and_url(cluster_id, "sr")
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            print(f"Deleted old audio file: {filepath}")
        except Exception as e:
            print(f"Warning: failed to delete old file: {e}")

    print(f"Synthesizing new speed-adjusted audio for {cluster_id}...")
    audio_url = AudioService.generate_cluster_audio(cluster_id, content, "sr", force=True)
    print(f"Generated new Audio URL for {cluster_id}: {audio_url}")


async def main():
    target_clusters = ["1e54ebcce23a", "3374b3ae8b5d"]
    for cid in target_clusters:
        try:
            await regenerate_cluster(cid)
        except Exception as e:
            print(f"Error regenerating cluster {cid}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
