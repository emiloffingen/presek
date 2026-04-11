
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
    
    print("\n--- PHASE 1: Testing Primary (Mistral) ---")
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="synthesis")
    print(f"Result from {provider}: {res[:100] if res else 'None'}...")

    # Force fail hosted providers to test final local fallback
    print("\n--- PHASE 2: Testing Final Fallback to Local NLP ---")
    
    original_mistral_call = PROVIDERS["mistral"].call
    PROVIDERS["mistral"].call = lambda *args, **kwargs: None # Simulate failure
    
    try:
        res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="synthesis")
        print(f"Result from {provider}: {res[:100] if res else 'None'}...")
        assert provider == "local"
    finally:
        # Restore original methods
        PROVIDERS["mistral"].call = original_mistral_call

if __name__ == "__main__":
    test_cascade()
