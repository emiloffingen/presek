import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ModuleNotFoundError:
    pass

# Force the correct model path BEFORE any other imports
model_path = str(PROJECT_ROOT / "models/gemma-4-E2B-it-Q4_K_M.gguf")
os.environ["LOCAL_MODEL_PATH"] = model_path
os.environ["ENV"] = "production"
os.environ.setdefault("CSRF_TOKEN_SECRET", "test")

import asyncio
from unittest.mock import patch

from routes.home import get_home
from tasks.intelligence import synthesize_cluster_task
from utils import redis_client


async def regenerate_frontpage():
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}")
        return

    # Clear the local LLM lock to prevent timeouts if other workers are stuck or busy
    print("Clearing local LLM inference lock...")
    redis_client.delete("lock:local_llm_inference")

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
            try:
                # We call the task synchronously for the script
                synthesize_cluster_task(cid, content=None, fast_mode=False)
                print(f"Successfully regenerated {cid}")
                # Clear lock after each one just in case it got stuck or we want to ensure next one starts fresh
                redis_client.delete("lock:local_llm_inference")
            except Exception as e:
                print(f"Failed to regenerate {cid}: {e}")


if __name__ == "__main__":
    # Ensure environment is set for the script
    os.environ["ENV"] = "production"
    os.environ.setdefault("CSRF_TOKEN_SECRET", "test")
    asyncio.run(regenerate_frontpage())
