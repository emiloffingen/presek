import logging
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

from ai_engine import sync_call_ai
from prompts import SUMMARY_SYSTEM_PROMPT


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    test_prompt = "Тест на системот: Напиши една реченица за вештачка интелигенција."
    print("\n--- Testing Mistral via Cascade ---")

    old_key = os.environ.get("GOOGLE_API_KEY")
    os.environ["GOOGLE_API_KEY"] = ""
    try:
        res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
        print(f"Provider used: {provider}")
        print(f"Result: {res}")
    finally:
        if old_key is None:
            os.environ.pop("GOOGLE_API_KEY", None)
        else:
            os.environ["GOOGLE_API_KEY"] = old_key


if __name__ == "__main__":
    main()
