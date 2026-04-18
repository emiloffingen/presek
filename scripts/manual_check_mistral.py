import logging
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

    res, provider = sync_call_ai(test_prompt, SUMMARY_SYSTEM_PROMPT, task_type="summarize")
    print(f"Provider used: {provider}")
    print(f"Result: {res}")


if __name__ == "__main__":
    main()
