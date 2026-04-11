
import os
import json
import logging
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

load_dotenv()
logging.basicConfig(level=logging.INFO)

from ai_engine import sync_call_ai
from prompts import SUMMARY_SYSTEM_PROMPT

def test_mistral_cascade():
    test_prompt = "Тест на системот: Напиши една реченица за вештачка интелигенција."
    
    print("\n--- Testing Mistral via Cascade ---")
    # We force Gemini to fail by temporarily removing its key from environment
    old_key = os.environ.get("GOOGLE_API_KEY")
    os.environ["GOOGLE_API_KEY"] = ""
    
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
    print(f"Provider used: {provider}")
    print(f"Result: {res}")
    
    os.environ["GOOGLE_API_KEY"] = old_key

if __name__ == "__main__":
    test_mistral_cascade()
