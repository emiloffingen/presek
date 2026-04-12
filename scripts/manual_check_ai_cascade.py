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

    print("\n--- PHASE 1: Testing Primary (Mistral) ---")
    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="synthesis")
    print(f"Result from {provider}: {res[:100] if res else 'None'}...")

    print("\n--- PHASE 2: Testing Final Fallback to Local NLP ---")
    original_mistral_call = PROVIDERS["mistral"].call
    PROVIDERS["mistral"].call = lambda *args, **kwargs: None

    try:
        res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="synthesis")
        print(f"Result from {provider}: {res[:100] if res else 'None'}...")
    finally:
        PROVIDERS["mistral"].call = original_mistral_call


if __name__ == "__main__":
    main()
