import logging
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

from ai_engine import PROVIDERS, sync_call_ai
from prompts import SUMMARY_SYSTEM_PROMPT


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    test_prompt = "Тест на системот: Напиши една реченица за времето во Скопје."

    print("\n--- PHASE 1: Testing System (Local -> Mistral cascade) ---")
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="synthesis")
    print(f"Result from {provider}: {res[:100] if res else 'None'}...")

    print("\n--- PHASE 2: Testing Fallback to Mistral (by disabling Local) ---")
    original_local_call = PROVIDERS["local"].call
    PROVIDERS["local"].call = lambda *args, **kwargs: None

    try:
        res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="synthesis")
        print(f"Result from {provider}: {res[:100] if res else 'None'}...")
    finally:
        PROVIDERS["local"].call = original_local_call


if __name__ == "__main__":
    main()
