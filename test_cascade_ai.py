
import os
import sys
import json
import logging
from dotenv import load_dotenv

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

    # Force fail Gemini to test failover
    print("\n--- PHASE 2: Testing Failover to OpenClaw (Simulated Gemini failure) ---")
    original_gemini_call = PROVIDERS["gemini"].call
    PROVIDERS["gemini"].call = lambda *args, **kwargs: None # Simulate failure
    
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
    print(f"Result from {provider}: {res[:100]}...")

    # Force fail OpenClaw to test final local fallback
    print("\n--- PHASE 3: Testing Final Fallback to Local NLP (Simulated Gemini + OpenClaw failure) ---")
    if "openclaw" in PROVIDERS:
        original_oc_call = PROVIDERS["openclaw"].call
        PROVIDERS["openclaw"].call = lambda *args, **kwargs: None
    
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
    print(f"Result from {provider}: {res[:100]}...")

    # Restore original methods
    PROVIDERS["gemini"].call = original_gemini_call
    if "openclaw" in PROVIDERS:
        PROVIDERS["openclaw"].call = original_oc_call

if __name__ == "__main__":
    test_cascade()
