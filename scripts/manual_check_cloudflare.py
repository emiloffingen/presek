import logging

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

    test_prompt = "Тест на системот: Напиши една реченица за Македонија."
    print("\n--- Testing Cloudflare via Cascade ---")

    old_mistral_call = PROVIDERS["mistral"].call
    PROVIDERS["mistral"].call = lambda *args, **kwargs: None

    old_gemini_call = None
    if "gemini" in PROVIDERS:
        old_gemini_call = PROVIDERS["gemini"].call
        PROVIDERS["gemini"].call = lambda *args, **kwargs: None

    try:
        res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
        print(f"Provider used: {provider}")
        print(f"Result: {res}")
    finally:
        PROVIDERS["mistral"].call = old_mistral_call
        if old_gemini_call:
            PROVIDERS["gemini"].call = old_gemini_call


if __name__ == "__main__":
    main()
