import asyncio
import os

# Ensure project root in path for ai_engine import
import sys
import time

from dotenv import load_dotenv

sys.path.append(os.getcwd())

from core.ai_engine import PROVIDERS

load_dotenv()


async def test_provider(name, provider, prompt, system):
    print(f"\n>>> Testing {name.upper()}...")
    start = time.time()
    try:
        # We use a thread to run the synchronous .call()
        res = await asyncio.to_thread(provider.call, prompt, system, 256, False)
        elapsed = time.time() - start
        if res:
            print(f"Time: {elapsed:.2f}s")
            print(f"Response: {res[:500]}...")
        else:
            print(f"FAILED: {name} returned empty response.")
    except Exception as e:
        print(f"ERROR ({name}): {e}")


async def main():
    test_prompt = "Napisi kratka analiza za vlijanieto na vestackata inteligencija vrz novinarstvoto vo 2026 godina."
    test_system = "Ti si profesionalen novinarski analiticar. odgovori na literaturen makedonski jazik."

    # 1. Test Nvidia
    await test_provider("nvidia", PROVIDERS["nvidia"], test_prompt, test_system)


if __name__ == "__main__":
    asyncio.run(main())
