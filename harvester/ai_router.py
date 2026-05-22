from __future__ import annotations

"""Multi-provider AI router — Gemini Flash → Groq Llama → Mistral.

All providers are FREE tier only.  No paid dependencies.

Usage::

    from harvester.ai_router import call_ai

    text, provider = call_ai("Your prompt here")
    if text is None:
        # all providers failed or no keys configured
        ...

Returns ``(response_text, provider_name)`` on success,
or ``(None, None)`` when every provider is unavailable or fails.
"""

import json
import os
from urllib import error, request

TIMEOUT_SECONDS = 30

# ---------------------------------------------------------------------------
# Gemini Flash (free tier — 15 req/min, 1500/day)
# ---------------------------------------------------------------------------
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent?key={api_key}"
)
GEMINI_MODEL = "gemini-1.5-flash"

# ---------------------------------------------------------------------------
# Groq (free tier — LLaMA 3.3 70B, 30 req/min)
# ---------------------------------------------------------------------------
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ---------------------------------------------------------------------------
# Mistral (free tier — rate limited ~1 req/sec)
# ---------------------------------------------------------------------------
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small"


def _gemini(prompt: str, api_key: str) -> str | None:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
    }
    req = request.Request(
        GEMINI_URL.format(api_key=api_key),
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:  # noqa: BLE001
        print(f"[ai_router] Gemini failed: {exc}")
        return None


def _openai_compat(prompt: str, api_key: str, url: str, model: str, label: str) -> str | None:
    """Shared helper for Groq and Mistral (both use OpenAI-compatible API)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        print(f"[ai_router] {label} failed: {exc}")
        return None


def call_ai(prompt: str) -> tuple[str | None, str | None]:
    """Try AI providers in priority order.

    Returns ``(response_text, provider_name)`` or ``(None, None)`` if every
    provider is unavailable or errors out.  Never raises.
    """
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        result = _gemini(prompt, gemini_key)
        if result is not None:
            return result, "gemini"

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        result = _openai_compat(prompt, groq_key, GROQ_URL, GROQ_MODEL, "Groq")
        if result is not None:
            return result, "groq"

    mistral_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if mistral_key:
        result = _openai_compat(prompt, mistral_key, MISTRAL_URL, MISTRAL_MODEL, "Mistral")
        if result is not None:
            return result, "mistral"

    print("[ai_router] No AI provider available (no API keys set or all failed).")
    return None, None
