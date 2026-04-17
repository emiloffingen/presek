import os
import httpx
from dotenv import load_dotenv

load_dotenv()

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
MISTRAL_API_URL = os.environ.get("MISTRAL_API_URL", "https://api.mistral.ai/v1/chat/completions")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

def test_mistral():
    if not MISTRAL_API_KEY:
        print("MISTRAL_API_KEY not found!")
        return

    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Write one sentence about the weather in Skopje."}
        ],
        "max_tokens": 100
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
    }
    
    print(f"Testing Mistral URL: {MISTRAL_API_URL}")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(MISTRAL_API_URL, json=payload, headers=headers)
            print(f"Status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"Response Body: {resp.text}")
            else:
                data = resp.json()
                print("Success!")
                print(f"Text: {data['choices'][0]['message']['content']}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_mistral()
