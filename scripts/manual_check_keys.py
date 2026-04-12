import json
import os
import urllib.request

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False


def test_gemini():
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("GOOGLE_API_KEY not configured")
        return
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "Say hi"}]}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"Gemini status: {resp.status}")


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
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"{env_key} status: {resp.status}")


def main():
    load_dotenv()
    test_gemini()
    check_openai_compatible("GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile")
    check_openai_compatible("MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions", "mistral-small-latest")
    check_openai_compatible("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1/chat/completions", "llama3.1-8b")
    check_openai_compatible("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", "openrouter/auto")
    check_openai_compatible("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini")


if __name__ == "__main__":
    main()
