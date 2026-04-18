import os
import httpx

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

def check_openai_compatible(env_key, url, model):
    key = os.environ.get(env_key)
    if not key:
        print(f"{env_key} not configured")
        return
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
    }
    headers = {
        "Authorization": f"Bearer {key}",
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload, headers=headers)
        print(f"{env_key} status: {resp.status_code}")
    except Exception as e:
        print(f"{env_key} error: {e}")


def main():
    load_dotenv()
    check_openai_compatible("GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile")
    check_openai_compatible("MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions", "mistral-small-latest")
    check_openai_compatible("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1/chat/completions", "llama3.1-8b")
    check_openai_compatible("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", "openrouter/auto")
    check_openai_compatible("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini")


if __name__ == "__main__":
    main()
