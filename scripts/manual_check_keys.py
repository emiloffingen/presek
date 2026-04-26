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
    check_openai_compatible("MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions", "mistral-large-latest")


if __name__ == "__main__":
    main()
