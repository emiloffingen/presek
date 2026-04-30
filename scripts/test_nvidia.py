import os
import httpx
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
NVIDIA_API_URL = os.environ.get("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")

def test_nvidia():
    if not NVIDIA_API_KEY:
        print("NVIDIA_API_KEY not found!")
        return

    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": "Ти си корисен асистент на македонски јазик."},
            {"role": "user", "content": "Напиши една реченица за вештачката интелигенција."}
        ],
        "max_tokens": 128,
        "temperature": 0.2,
        "top_p": 0.7
    }
    
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }

    print(f"Testing NVIDIA NIM URL: {NVIDIA_API_URL}")
    print(f"Model: {NVIDIA_MODEL}")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(NVIDIA_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            print("\nResponse:")
            print(data["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"\nError: {e}")
        if hasattr(e, 'response'):
            print(f"Status Code: {e.response.status_code}")
            print(f"Response: {e.response.text}")

if __name__ == "__main__":
    test_nvidia()
