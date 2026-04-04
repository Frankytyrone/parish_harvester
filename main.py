"""
main.py — CLI entry point for the Parish Bulletin Harvester.

Usage:
    python main.py [--diocese DIOCESE] [--target-date YYYY-MM-DD]
                   [--skip-verify] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from harvester.config import (
    BULLETINS_DIR,
    CURRENT_DIR,
    PARISHES_DIR,
    RAW_DIR,
    REPORT_JSON,
    REPORT_TXT,
    next_sunday,
)
from harvester.fetcher import fetch_all
from harvester.verifier import verify_file
from harvester.cleaner import clean


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _silence_playwright_shutdown(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    """Suppress TargetClosedError futures that surface during Playwright shutdown."""
    exc = context.get("exception")
    if exc is not None and type(exc).__name__ == "TargetClosedError":
        return  # silently ignore
    loop.default_exception_handler(context)


def load_urls(diocese: str) -> list[str]:
    txt_file = PARISHES_DIR / f"{diocese}.txt"
    if not txt_file.exists():
        print(f"💥 Parish list not found: {txt_file}", file=sys.stderr)
        sys.exit(1)
    urls = [
        line.strip()
        for line in txt_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return urls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Harvest parish bulletins for the Derry Diocese."
    )
    parser.add_argument(
        "--diocese",
        default="derry_diocese",
        help="Parish list name (default: derry_diocese)",
    )
    parser.add_argument(
        "--target-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Target Sunday date (default: auto-calculate next Sunday)",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip AI verification (Stage 2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch only; do not clean or move files",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()

    # Resolve target date
    if args.target_date:
        try:
            target = datetime.strptime(args.target_date, "%Y-%m-%d").date()
        except ValueError:
            print(f"💥 Invalid --target-date format: {args.target_date}", file=sys.stderr)
            return 1
    else:
        target = next_sunday()

    print(f"🗓️  Target date  : {target}")
    print(f"📋 Diocese      : {args.diocese}")
    print(f"📁 Output dir   : {RAW_DIR}")

    urls = load_urls(args.diocese)
    print(f"🌐 Parishes     : {len(urls)}")

    # ------------------------------------------------------------------
    # Stage 1: Fetch
    # ------------------------------------------------------------------
    print("\n── Stage 1: Fetch ──────────────────────────────────────────")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    loop = asyncio.new_event_loop()
    loop.set_exception_handler(_silence_playwright_shutdown)
    asyncio.set_event_loop(loop)
    try:
        fetch_results = loop.run_until_complete(fetch_all(urls, RAW_DIR, target))
    finally:
        loop.close()

    ok_count = sum(1 for r in fetch_results if r.status == "ok")
    err_count = sum(1 for r in fetch_results if r.status == "error")
    print(f"  ✅ Fetched : {ok_count}")
    print(f"  💥 Errors  : {err_count}")
    for r in fetch_results:
        if r.status == "error":
            print(f"     {r.parish}: {r.error}")

    if args.dry_run:
        print("\n⚠️  --dry-run: stopping after fetch.")
        return 0

    # ------------------------------------------------------------------
    # Stage 2: Verify
    # ------------------------------------------------------------------
    verdicts: dict[str, str] = {}

    if args.skip_verify:
        print("\n── Stage 2: Verify (skipped) ───────────────────────────────")
        for r in fetch_results:
            if r.status == "ok" and r.file_path:
                verdicts[r.file_path.name] = "UNKNOWN"
    else:
        print("\n── Stage 2: Verify ─────────────────────────────────────────")
        for r in fetch_results:
            if r.status != "ok" or not r.file_path or not r.file_path.exists():
                continue
            verdict = verify_file(r.file_path, target)
            verdicts[r.file_path.name] = verdict
            icon = {"FRESH": "✅", "STALE": "❌", "UNKNOWN": "⚠️ "}.get(
                verdict.split(":")[0], "💥"
            )
            print(f"  {icon} {r.parish}: {verdict}")

    # ------------------------------------------------------------------
    # Stage 3: Clean
    # ------------------------------------------------------------------
    print("\n── Stage 3: Clean ──────────────────────────────────────────")
    result = clean(
        verdicts=verdicts,
        raw_dir=RAW_DIR,
        current_dir=CURRENT_DIR,
        report_json=REPORT_JSON,
        report_txt=REPORT_TXT,
        target=target,
    )

    print(f"  ✅ Fresh   : {len(result.fresh)}")
    print(f"  ❌ Stale   : {len(result.stale)}")
    print(f"  ⚠️  Unknown  : {len(result.unknown)}")
    print(f"  💥 Errors  : {len(result.errors)}")
    print(f"\n📄 Report  : {REPORT_JSON}")
    print(f"📄 Report  : {REPORT_TXT}")

    return 0 if len(result.errors) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
