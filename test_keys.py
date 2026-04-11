
import os
import json
import urllib.request
import pytest
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

load_dotenv()
RUN_LIVE_KEY_TESTS = os.environ.get("RUN_LIVE_KEY_TESTS") == "1"

def test_gemini():
    if not RUN_LIVE_KEY_TESTS:
        pytest.skip("Live key validation is disabled")
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        pytest.skip("GOOGLE_API_KEY not configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "Say hi"}]}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 200
    except Exception as e:
        pytest.fail(f"Gemini key check failed: {e}")

def check_openai_compatible(env_key, url, model):
    if not RUN_LIVE_KEY_TESTS:
        pytest.skip("Live key validation is disabled")
    key = os.environ.get(env_key)
    if not key:
        pytest.skip(f"{env_key} not configured")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 200
    except Exception as e:
        pytest.fail(f"{env_key} key check failed: {e}")

@pytest.mark.parametrize(
    ("env_key", "url", "model"),
    [
        ("GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
        ("MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions", "mistral-small-latest"),
        ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1/chat/completions", "llama3.1-8b"),
        ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", "openrouter/auto"),
        ("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
    ],
)
def test_openai_compatible(env_key, url, model):
    check_openai_compatible(env_key, url, model)

if __name__ == "__main__":
    print(f"Gemini: {test_gemini()}")
    print(f"Groq: {check_openai_compatible('GROQ_API_KEY', 'https://api.groq.com/openai/v1/chat/completions', 'llama-3.3-70b-versatile')}")
    print(f"Mistral: {check_openai_compatible('MISTRAL_API_KEY', 'https://api.mistral.ai/v1/chat/completions', 'mistral-small-latest')}")
    print(f"Cerebras: {check_openai_compatible('CEREBRAS_API_KEY', 'https://api.cerebras.ai/v1/chat/completions', 'llama3.1-8b')}")
    print(f"OpenRouter: {check_openai_compatible('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1/chat/completions', 'openrouter/auto')}")
    print(f"OpenAI: {check_openai_compatible('OPENAI_API_KEY', 'https://api.openai.com/v1/chat/completions', 'gpt-4o-mini')}")
