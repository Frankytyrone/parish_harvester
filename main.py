"""
main.py — CLI entry point for the Parish Bulletin Harvester v2.

Usage:
    python main.py [--diocese DIOCESE] [--target-date YYYY-MM-DD] [--dry-run]
    python main.py --train "Parish Name" [--diocese DIOCESE]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

from harvester.config import (
    BULLETINS_DIR,
    CURRENT_DIR,
    PARISHES_DIR,
    RAW_DIR,
    REPORT_JSON,
    REPORT_TXT,
    target_sunday,
)
from harvester.email_notifier import send_harvest_notification
from harvester.fetcher import fetch_all, parse_evidence_file
from harvester.harvest_log import log_result, print_summary
from harvester.report import generate_report
from harvester.stitcher import stitch_mega_pdf
from train import run_training


def _silence_playwright_shutdown(
    loop: asyncio.AbstractEventLoop, context: dict
) -> None:
    """Suppress TargetClosedError futures that surface during Playwright shutdown."""
    exc = context.get("exception")
    if exc is not None and type(exc).__name__ == "TargetClosedError":
        return
    loop.default_exception_handler(context)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parish Bulletin Harvester — evidence-driven downloader."
    )
    parser.add_argument(
        "--diocese",
        default="derry_diocese",
        help="Diocese name (default: derry_diocese)",
    )
    parser.add_argument(
        "--target-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Target Sunday date (default: auto-calculate)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch only; do not move files or stitch mega PDF",
    )
    parser.add_argument(
        "--train",
        default=None,
        metavar="PARISH_NAME",
        help="Interactive training mode: record browser steps for a parish",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.WARNING)
    harvest_start = time.monotonic()

    if args.train:
        try:
            asyncio.run(
                run_training(
                    parish_query=args.train,
                    diocese=args.diocese,
                    parishes_dir=PARISHES_DIR,
                )
            )
            return 0
        except Exception as exc:
            print(f"💥 Training failed: {exc}", file=sys.stderr)
            return 1

    # Resolve target date
    if args.target_date:
        try:
            target = datetime.strptime(args.target_date, "%Y-%m-%d").date()
        except ValueError:
            print(f"💥 Invalid --target-date format: {args.target_date}", file=sys.stderr)
            return 1
    else:
        target = target_sunday()

    print(f"🗓️  Target date  : {target}")
    print(f"📋 Diocese      : {args.diocese}")

    # Parse evidence file
    try:
        entries = parse_evidence_file(args.diocese, PARISHES_DIR)
    except FileNotFoundError as exc:
        print(f"💥 {exc}", file=sys.stderr)
        return 1

    print(f"⛪ Parishes     : {len(entries)}")

    # Fetch all bulletins
    print("\n── Fetch ───────────────────────────────────────────────────")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    loop = asyncio.new_event_loop()
    loop.set_exception_handler(_silence_playwright_shutdown)
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(fetch_all(entries, RAW_DIR, target))
    finally:
        loop.close()

    ok_count = sum(1 for r in results if r.status == "ok")
    html_count = sum(1 for r in results if r.status == "html_link")
    err_count = sum(1 for r in results if r.status == "error")

    # Log every result to harvest_log.json
    for r in results:
        log_result(r, r.key, r.display_name)

    print(f"  ✅ Downloaded  : {ok_count}")
    print(f"  🔗 HTML links  : {html_count}")
    print(f"  💥 Failed      : {err_count}")

    if err_count:
        print(f"\n  Failed parishes ({err_count}):")
        for i, r in enumerate(
            (r for r in results if r.status == "error"), start=1
        ):
            print(f"  {i:2d}. {r.display_name}")
            print(f"       URL    : {r.url}")
            print(f"       Reason : {r.error}")

    if args.dry_run:
        print("\n⚠️  --dry-run: stopping after fetch.")
        return 0

    # Generate report
    print("\n── Report ──────────────────────────────────────────────────")
    contacts_path = PARISHES_DIR / f"{args.diocese}_contacts.json"
    generate_report(
        results,
        raw_dir=RAW_DIR,
        current_dir=CURRENT_DIR,
        report_json=REPORT_JSON,
        report_txt=REPORT_TXT,
        target=target,
    )
    print(f"  📄 Report JSON : {REPORT_JSON}")
    print(f"  📄 Report TXT  : {REPORT_TXT}")

    # Stitch mega PDF
    print("\n── Stitch Mega PDF ─────────────────────────────────────────")
    try:
        stitch_mega_pdf(
            results,
            current_dir=CURRENT_DIR,
            bulletins_dir=BULLETINS_DIR,
            target=target,
            contacts_path=contacts_path if contacts_path.exists() else None,
        )
    except Exception as exc:
        print(f"  ⚠️  Mega PDF generation failed (non-fatal): {exc}")

    # Print harvest log summary
    print_summary()

    # Send email notification
    print("\n── Notification ────────────────────────────────────────────")
    send_harvest_notification(REPORT_JSON, duration_seconds=time.monotonic() - harvest_start)

    return 0


if __name__ == "__main__":
    sys.exit(main())
