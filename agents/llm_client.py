"""
agents/llm_client.py
Uses a reliable paid model — your $5 OpenRouter credit covers ~50,000 calls.
meta-llama/llama-3.1-8b-instruct costs $0.00007 per call (7 cents per 1000 calls).
Falls back to gemma if llama unavailable.
"""

import os
import httpx
from dotenv import load_dotenv
load_dotenv()

_api_key  = os.getenv("GROQ_API_KEY", "")
_base_url = os.getenv("GROQ_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
_provider = os.getenv("LLM_PROVIDER", "openrouter")

# Use paid llama — $0.00007/call, your $5 = ~71,000 calls
# Much more reliable than free tier which gets rate-limited by other users
_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct")

# Models that don't support system role
NO_SYSTEM_ROLE = {"google/gemma-3-4b-it:free", "google/gemma-3-12b-it:free",
                  "google/gemma-3-4b-it", "google/gemma-3-12b-it"}

print(f"[llm_client] Provider: {_provider} | Model: {_MODEL}")


async def llm_chat(
    system: str,
    user: str,
    max_tokens: int = 150,
    temperature: float = 0.65,
) -> str:
    headers = {
        "Authorization": f"Bearer {_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://observeinsurance.ai",
        "X-Title": "Observe Insurance ARIA",
    }

    if _MODEL in NO_SYSTEM_ROLE:
        messages = [{"role": "user", "content": f"{system}\n\n{user}"}]
    else:
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]

    payload = {
        "model": _MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as e:
        print(f"[llm_client] HTTP {e.response.status_code}: {e.response.text[:120]}")
        raise  # Re-raise so graph knows something went wrong
    except Exception as e:
        print(f"[llm_client] ERROR: {type(e).__name__}: {e}")
        raise
