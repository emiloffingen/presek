import asyncio
import os
import sys
import time

# Ensure project root in path for ai_engine import
sys.path.append(os.getcwd())

from core.ai_engine import PROVIDERS


async def test_provider(name, provider):
    print(f"\n>>> Testing {name.upper()}...")
    # Check if api_key exists as an attribute (some providers might not have it)
    if not getattr(provider, "api_key", None) and name != "local":
        print(f"SKIPPED: {name} (no API key attribute found)")
        return

    start = time.time()
    try:
        # Use a simple test prompt
        res = await asyncio.to_thread(provider.call, "Hello, world!", "You are a helpful assistant.", 50, False)
        elapsed = time.time() - start
        if res:
            print(f"SUCCESS: {name} (Time: {elapsed:.2f}s)")
        else:
            print(f"FAILED: {name} returned empty response.")
    except Exception as e:
        print(f"ERROR ({name}): {e}")


async def main():
    for name, provider in PROVIDERS.items():
        await test_provider(name, provider)


if __name__ == "__main__":
    asyncio.run(main())
