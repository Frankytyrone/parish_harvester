from __future__ import annotations

import json
from pathlib import Path


def _load_failures(failures_path: Path) -> dict[str, int]:
    if not failures_path.exists():
        return {}
    try:
        payload = json.loads(failures_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}

    failures: dict[str, int] = {}
    for key, value in payload.items():
        parish_key = str(key).strip()
        if not parish_key:
            continue
        try:
            failures[parish_key] = int(value)
        except (TypeError, ValueError):
            continue
    return failures


def prioritise(
    parish_keys: list[str],
    failures_path: Path = Path("parishes/consecutive_failures.json"),
) -> list[str]:
    failures = _load_failures(failures_path)
    known = [key for key in parish_keys if key in failures]
    unknown = [key for key in parish_keys if key not in failures]

    known.sort(key=lambda parish_key: (-failures[parish_key], parish_key))
    return known + unknown
