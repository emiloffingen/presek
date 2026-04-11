
import os
import sys
import json
import logging
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

# Load .env file explicitly
load_dotenv()

# Setup basic logging to see the cascade in action
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek_test")

# Mock the environment or ensure config is loaded
os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "postgresql://localhost/presek")

from ai_engine import sync_call_ai, PROVIDERS
from prompts import SUMMARY_SYSTEM_PROMPT

def test_cascade():
    test_prompt = "Тест на системот: Напиши една реченица за времето во Скопје."
    
    print("\n--- PHASE 1: Testing Primary (Gemini) ---")
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
    print(f"Result from {provider}: {res[:100]}...")

    # Force fail Gemini to test next fallback
    print("\n--- PHASE 2: Testing Failover Beyond Gemini (Simulated Gemini failure) ---")
    original_gemini_call = PROVIDERS["gemini"].call
    PROVIDERS["gemini"].call = lambda *args, **kwargs: None # Simulate failure
    
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
    print(f"Result from {provider}: {res[:100]}...")

    # Force fail the remaining hosted providers to test final local fallback
    print("\n--- PHASE 3: Testing Final Fallback to Local NLP (Simulated hosted-provider failure) ---")
    original_mistral_call = PROVIDERS["mistral"].call
    original_cf_call = PROVIDERS["cloudflare"].call
    PROVIDERS["mistral"].call = lambda *args, **kwargs: None
    PROVIDERS["cloudflare"].call = lambda *args, **kwargs: None
    
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
    print(f"Result from {provider}: {res[:100]}...")

    # Restore original methods
    PROVIDERS["gemini"].call = original_gemini_call
    PROVIDERS["mistral"].call = original_mistral_call
    PROVIDERS["cloudflare"].call = original_cf_call

if __name__ == "__main__":
    test_cascade()
