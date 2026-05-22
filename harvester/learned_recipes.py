from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .config import BASE_DIR

LEARNED_DIR = BASE_DIR / "recipes" / "learned"


def _path_for(parish_key: str) -> Path:
    return LEARNED_DIR / f"{parish_key}.json"


def _coerce_dom_markers(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for marker in value:
        text = str(marker or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _coerce_playbook(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for step in value:
        if isinstance(step, dict):
            out.append(step)
    return out


def _fingerprint_from_playbook(playbook: list[dict]) -> dict:
    host = ""
    path_hint = ""
    dom_markers: list[str] = []

    for step in playbook:
        action = str(step.get("action") or "").strip().lower()
        if action == "goto":
            url = str(step.get("url") or "").strip()
            if url:
                parsed = urlparse(url)
                host = parsed.netloc.lower()
                path_hint = parsed.path or "/"
                break

    for step in playbook:
        if str(step.get("action") or "").strip().lower() != "click":
            continue
        selector = str(step.get("selector") or "").strip()
        if selector and selector not in dom_markers:
            dom_markers.append(selector)

    return {
        "host": host,
        "path_hint": path_hint,
        "dom_markers": dom_markers,
    }


def _normalize(parish_key: str, data: dict | None = None) -> dict:
    source = data if isinstance(data, dict) else {}
    playbook = _coerce_playbook(source.get("playbook"))

    source_fingerprint = source.get("fingerprint") if isinstance(source.get("fingerprint"), dict) else {}
    derived_fingerprint = _fingerprint_from_playbook(playbook)

    host = str(source_fingerprint.get("host") or derived_fingerprint["host"] or "").strip()
    path_hint = str(source_fingerprint.get("path_hint") or derived_fingerprint["path_hint"] or "").strip()
    dom_markers = _coerce_dom_markers(source_fingerprint.get("dom_markers")) or derived_fingerprint["dom_markers"]

    success_count = max(int(source.get("success_count") or 0), 0)
    failure_count = max(int(source.get("failure_count") or 0), 0)
    total = success_count + failure_count
    success_rate = round(success_count / total, 2) if total else 0.0

    return {
        "parish_key": parish_key,
        "fingerprint": {
            "host": host,
            "path_hint": path_hint,
            "dom_markers": dom_markers,
        },
        "last_success_date": str(source.get("last_success_date") or ""),
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": success_rate,
        "playbook": playbook,
        "last_strategy": str(source.get("last_strategy") or ""),
    }


def load(parish_key: str) -> dict | None:
    path = _path_for(parish_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return _normalize(parish_key, data)


def save(parish_key: str, data: dict) -> None:
    LEARNED_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(parish_key)
    payload = _normalize(parish_key, data)

    fd, temp_path = tempfile.mkstemp(prefix=f"{parish_key}-", suffix=".tmp", dir=LEARNED_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def record_success(parish_key: str, strategy: str, playbook: list) -> None:
    data = _normalize(parish_key, load(parish_key))
    data["last_success_date"] = date.today().isoformat()
    data["success_count"] = int(data["success_count"]) + 1
    data["playbook"] = _coerce_playbook(playbook)
    data["last_strategy"] = str(strategy or "")

    fingerprint = _fingerprint_from_playbook(data["playbook"])
    existing_fp = data.get("fingerprint") if isinstance(data.get("fingerprint"), dict) else {}
    data["fingerprint"] = {
        "host": str(existing_fp.get("host") or fingerprint["host"] or "").strip(),
        "path_hint": str(existing_fp.get("path_hint") or fingerprint["path_hint"] or "").strip(),
        "dom_markers": _coerce_dom_markers(existing_fp.get("dom_markers")) or fingerprint["dom_markers"],
    }

    total = int(data["success_count"]) + int(data["failure_count"])
    data["success_rate"] = round(int(data["success_count"]) / total, 2) if total else 0.0
    save(parish_key, data)


def record_failure(parish_key: str) -> None:
    data = _normalize(parish_key, load(parish_key))
    data["failure_count"] = int(data["failure_count"]) + 1
    total = int(data["success_count"]) + int(data["failure_count"])
    data["success_rate"] = round(int(data["success_count"]) / total, 2) if total else 0.0
    save(parish_key, data)
