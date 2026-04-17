import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GOOGLE_API_KEY")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"

def test_gemini():
    # Attempt with explicit 'role' and 'parts'
    payload = {
        "system_instruction": {
            "parts": [{"text": "You are a helpful assistant."}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": "Write one sentence about the weather."}]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 100,
            "temperature": 0.1
        }
    }
    
    print(f"Testing URL: {URL.replace(API_KEY, 'REDACTED')}")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(URL, json=payload)
            print(f"Status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"Response Body: {resp.text}")
            else:
                data = resp.json()
                print("Success!")
                print(f"Text: {data['candidates'][0]['content']['parts'][0]['text']}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_gemini()
