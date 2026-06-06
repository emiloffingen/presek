import asyncio
import os
from routes.home import get_home
from tasks.intelligence import synthesize_cluster_task
from unittest.mock import patch

async def regenerate_frontpage():
    cluster_ids = set()
    for lang in ["sr", "mk"]:
        print(f"Fetching frontpage clusters for {lang}...")
        response = await get_home(lang=lang)
        data = response
        if hasattr(data, "dict"):
            data = data.dict()
        
        # Collect all cluster IDs from sections that have synthesis
        sections = ["synthesis_picks", "lead", "supporting", "developing", "live_now", "global_"]
        for section in sections:
            item = data.get(section)
            if not item:
                continue
            if isinstance(item, list):
                for c in item:
                    if c.get("cluster_id"):
                        cluster_ids.add(c["cluster_id"])
            elif isinstance(item, dict):
                if item.get("cluster_id"):
                    cluster_ids.add(item["cluster_id"])

    print(f"Found {len(cluster_ids)} unique clusters on frontpage: {cluster_ids}")

    # Mock SmartModelRouter to force 'local'
    with patch("core.llm_router.SmartModelRouter.route_cluster", return_value="local"):
        for cid in cluster_ids:
            print(f"Regenerating synthesis for cluster {cid} using Gemma 4 E2B...")
            # We call the task synchronously for the script
            # synthesize_cluster_task is a celery task, but we can call the function directly
            try:
                # We need to provide 'content' if it's expected, but it seems it can be None
                # if it loads from articles.
                synthesize_cluster_task(cid, content=None, fast_mode=False)
                print(f"Successfully regenerated {cid}")
            except Exception as e:
                print(f"Failed to regenerate {cid}: {e}")

if __name__ == "__main__":
    # Ensure environment is set for the script
    os.environ["ENV"] = "development"
    os.environ["CSRF_TOKEN_SECRET"] = "test"
    asyncio.run(regenerate_frontpage())
