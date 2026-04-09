
import os
import json
import logging
from dotenv import load_dotenv

# Load .env file explicitly
load_dotenv()
logging.basicConfig(level=logging.INFO)

from ai_engine import sync_call_ai
from prompts import SUMMARY_SYSTEM_PROMPT

def test_cloudflare_cascade():
    test_prompt = "Тест на системот: Напиши една реченица за Македонија."
    
    print("\n--- Testing Cloudflare via Cascade ---")
    # Force Gemini and Mistral to fail to reach Cloudflare
    from ai_engine import PROVIDERS
    
    old_gemini_call = PROVIDERS["gemini"].call
    old_mistral_call = PROVIDERS["mistral"].call
    
    PROVIDERS["gemini"].call = lambda *args, **kwargs: None
    PROVIDERS["mistral"].call = lambda *args, **kwargs: None
    
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
    print(f"Provider used: {provider}")
    print(f"Result: {res}")
    
    # Restore
    PROVIDERS["gemini"].call = old_gemini_call
    PROVIDERS["mistral"].call = old_mistral_call

if __name__ == "__main__":
    test_cloudflare_cascade()
