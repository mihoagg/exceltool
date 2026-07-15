import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    print("ERROR: OPENROUTER_API_KEY not set in .env or environment")
    sys.exit(1)

payload = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "say hello in one word"}],
    "max_tokens": 10,
}

try:
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    print(f"Status: {resp.status_code}")
    print(f"Model:  {MODEL}")
    print()

    if resp.status_code == 200:
        data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content")
        if content:
            print(f"Response: {content.strip()}")
        else:
            reasoning = msg.get("reasoning", "")
            print(f"Response: (reasoning only) {reasoning.strip()[:100]}")
    else:
        retry = resp.headers.get("Retry-After")
        remaining = resp.headers.get("x-ratelimit-remaining-requests")
        print(f"Status: {resp.status_code}")
        if retry:
            print(f"Retry-After: {retry}s")
        if remaining:
            print(f"Requests remaining: {remaining}")
        print(f"Body: {resp.text[:500]}")

except Exception as e:
    print(f"Error: {e}")
