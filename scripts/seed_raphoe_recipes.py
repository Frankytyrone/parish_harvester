from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
URLS_PATH = Path(__file__).resolve().parent / "raphoe_seed_urls.txt"
OUT_DIR = REPO_ROOT / "parishes" / "recipes" / "raphoe"


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "raphoe-parish"


def _domain_label(host: str) -> str:
    host = host.lower().replace("www.", "")
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 2:
        return parts[-2]
    return host or "raphoe"


def _derive_parish_key(url: str) -> tuple[str, str | None]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path_bits = [part for part in parsed.path.split("/") if part]

    if host == "drive.google.com":
        token = ""
        if "folders" in path_bits:
            token = path_bits[-1]
        elif "d" in path_bits:
            token = path_bits[-2] if path_bits[-1] == "view" and len(path_bits) >= 2 else path_bits[-1]
        key = _slugify(f"drive-{token[:10]}")
        return key, f"ambiguous Google Drive URL, best guess key '{key}' from path token"

    if host == "mcn.live" or host.endswith(".mcn.live"):
        guess = _slugify(path_bits[-1] if path_bits else _domain_label(host))
        return guess, f"ambiguous mcn.live URL, best guess key '{guess}' from camera path"

    if host == "parishpress.net" or host.endswith(".parishpress.net"):
        guess = _slugify(path_bits[-2] if len(path_bits) >= 2 else _domain_label(host))
        return guess, f"ambiguous parishpress.net file URL, best guess key '{guess}' from path"

    return _slugify(_domain_label(host)), None


def _display_name_from_key(key: str) -> str:
    return " ".join(part.capitalize() for part in key.replace("_", "-").split("-") if part)


def main() -> int:
    urls = [line.strip() for line in URLS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0
    for url in urls:
        parish_key, note = _derive_parish_key(url)
        target = OUT_DIR / f"{parish_key}.json"
        if target.exists():
            print(f"[skip] {parish_key}: already present")
            skipped += 1
            continue

        display_name = _display_name_from_key(parish_key)
        payload = {
            "parish_key": parish_key,
            "parish_name": display_name,
            "display_name": display_name,
            "recorded_date": date.today().isoformat(),
            "start_url": url,
            "steps": [{"action": "goto", "url": url}],
            "version": 1,
            "diocese": "raphoe",
        }
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        created += 1
        if note:
            print(f"[create] {parish_key}: {note}")
        else:
            print(f"[create] {parish_key}: derived from domain")

    print(f"done: created={created}, skipped={skipped}, total={len(urls)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
