import os
import asyncio
import httpx
import time
from dotenv import load_dotenv

# Ensure project root in path for ai_engine import
import sys
sys.path.append(os.getcwd())

from ai_engine import PROVIDERS
from prompts import SUMMARY_SYSTEM_PROMPT

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
    test_prompt = "Напиши кратка анализа за влијанието на вештачката интелигенција врз новинарството во 2026 година."
    test_system = "Ти си професионален новинарски аналитичар. Одговори на литературен македонски јазик."
    
    # 1. Test Nvidia
    await test_provider("nvidia", PROVIDERS["nvidia"], test_prompt, test_system)
    
    # 2. Test Gemini
    await test_provider("gemini", PROVIDERS["gemini"], test_prompt, test_system)

if __name__ == "__main__":
    asyncio.run(main())
