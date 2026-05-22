from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .config import BASE_DIR

LEARNED_DIR = BASE_DIR / "recipes" / "learned"


def _path_for(parish_key: str, diocese: str = "") -> Path:
    """Return the file path for a learned recipe.

    New layout: ``LEARNED_DIR/<diocese>/<parish_key>.json``
    Legacy flat layout: ``LEARNED_DIR/<parish_key>.json``
    Writing always uses the new layout (diocese defaults to "unknown" when blank).
    """
    folder = (diocese or "").strip()
    if folder:
        return LEARNED_DIR / folder / f"{parish_key}.json"
    return LEARNED_DIR / "unknown" / f"{parish_key}.json"


def _flat_path_for(parish_key: str) -> Path:
    """Legacy flat path — used only as a read fallback."""
    return LEARNED_DIR / f"{parish_key}.json"


def _update_index(diocese: str, parish_key: str, last_updated: str) -> None:
    """Atomically update the per-diocese ``_index.json`` file."""
    folder = (diocese or "unknown").strip()
    index_dir = LEARNED_DIR / folder
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "_index.json"

    # Load existing index.
    entries: dict[str, str] = {}
    if index_path.exists():
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("entries"), dict):
                entries = raw["entries"]
        except Exception:
            entries = {}

    entries[parish_key] = last_updated

    payload = {"diocese": folder, "entries": entries}
    fd, tmp = tempfile.mkstemp(prefix="_index-", suffix=".tmp", dir=index_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, index_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


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
        "diocese": str(source.get("diocese") or "").strip(),
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


def load(parish_key: str, diocese: str = "") -> dict | None:
    """Load a learned recipe.

    Tries the new per-diocese path first.  If that is missing and a legacy
    flat file exists, falls back to the flat path (one read attempt, no error
    if missing).  The returned dict will have ``diocese`` set if it was stored.
    """
    # Guard: _index.json is not a learned recipe.
    if parish_key == "_index":
        return None

    # New path: LEARNED_DIR/<diocese>/<parish_key>.json
    new_path = _path_for(parish_key, diocese)
    for path in [new_path, _flat_path_for(parish_key)]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        # Prefer diocese from the caller over what's stored.
        if diocese:
            data["diocese"] = diocese
        return _normalize(parish_key, data)
    return None


def save(parish_key: str, data: dict) -> None:
    """Save a learned recipe to the per-diocese path and update ``_index.json``."""
    diocese = str((data or {}).get("diocese") or "").strip()
    path = _path_for(parish_key, diocese)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = _normalize(parish_key, data)

    fd, temp_path = tempfile.mkstemp(prefix=f"{parish_key}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    _update_index(diocese, parish_key, date.today().isoformat())


def record_success(parish_key: str, strategy: str, playbook: list, diocese: str = "") -> None:
    data = _normalize(parish_key, load(parish_key, diocese))
    if diocese:
        data["diocese"] = diocese
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


def record_failure(parish_key: str, diocese: str = "") -> None:
    data = _normalize(parish_key, load(parish_key, diocese))
    if diocese:
        data["diocese"] = diocese
    data["failure_count"] = int(data["failure_count"]) + 1
    total = int(data["success_count"]) + int(data["failure_count"])
    data["success_rate"] = round(int(data["success_count"]) / total, 2) if total else 0.0
    save(parish_key, data)
