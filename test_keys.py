
import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()

def test_gemini():
    key = os.environ.get("GOOGLE_API_KEY")
    if not key: return "Missing"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "Say hi"}]}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return "Valid" if resp.status == 200 else f"Error {resp.status}"
    except Exception as e:
        return f"Failed: {e}"

def test_openai_compatible(env_key, url, model):
    key = os.environ.get(env_key)
    if not key: return "Missing"
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
            return "Valid" if resp.status == 200 else f"Error {resp.status}"
    except Exception as e:
        return f"Failed: {e}"

if __name__ == "__main__":
    print(f"Gemini: {test_gemini()}")
    print(f"Groq: {test_openai_compatible('GROQ_API_KEY', 'https://api.groq.com/openai/v1/chat/completions', 'llama-3.3-70b-versatile')}")
    print(f"Mistral: {test_openai_compatible('MISTRAL_API_KEY', 'https://api.mistral.ai/v1/chat/completions', 'mistral-small-latest')}")
    print(f"Cerebras: {test_openai_compatible('CEREBRAS_API_KEY', 'https://api.cerebras.ai/v1/chat/completions', 'llama3.1-8b')}")
    print(f"OpenRouter: {test_openai_compatible('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1/chat/completions', 'openrouter/auto')}")
    print(f"OpenAI: {test_openai_compatible('OPENAI_API_KEY', 'https://api.openai.com/v1/chat/completions', 'gpt-4o-mini')}")
