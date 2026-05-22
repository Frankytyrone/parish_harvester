from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib import error, request

MISTRAL_SUMMARY_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small"
MAX_INPUT_CHARS = 12_000
TIMEOUT_SECONDS = 20
EXPECTED_BULLET_COUNT = 3


def _parse_bullets(content: str) -> list[str] | None:
    bullets: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line[:1] in {"-", "*", "•"}:
            line = line[1:].strip()
        bullets.append(line)
    if len(bullets) != EXPECTED_BULLET_COUNT:
        return None
    return bullets


def summarise_bulletin(text: str, parish_name: str, mistral_api_key: str | None) -> dict | None:
    api_key = (mistral_api_key or "").strip()
    if not api_key:
        return None

    truncated_text = (text or "")[:MAX_INPUT_CHARS]
    prompt = (
        f"You are summarising a Catholic parish bulletin for {parish_name}. "
        "Produce exactly 3 short bullet points (max 20 words each) covering the most important events, "
        "Mass times, and notices for the coming week. Plain text only, one bullet per line, no markdown."
    )

    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {
                "role": "user",
                "content": f"{prompt}\n\n{truncated_text}",
            }
        ],
        "temperature": 0.1,
    }

    req = request.Request(
        MISTRAL_SUMMARY_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None)
            if status is None or status >= 400:
                print(f"Summary request failed for {parish_name}: HTTP {status}")
                return None
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        print(f"Summary request failed for {parish_name}: HTTP {exc.code}")
        return None
    except error.URLError as exc:
        print(f"Summary request failed for {parish_name}: {exc}")
        return None
    except TimeoutError:
        print(f"Summary request timed out for {parish_name}")
        return None
    except Exception as exc:
        print(f"Summary request failed for {parish_name}: {exc}")
        return None

    try:
        data = json.loads(body)
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            return None
        bullets = _parse_bullets(content)
        if bullets is None:
            return None
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return {
            "bullets": bullets,
            "model": MISTRAL_MODEL,
            "generated_at": generated_at,
        }
    except Exception as exc:
        print(f"Summary response parsing failed for {parish_name}: {exc}")
        return None
