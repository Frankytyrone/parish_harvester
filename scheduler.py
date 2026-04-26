"""
scheduler.py — Automatic scheduled harvesting for the Parish Bulletin Harvester.

Runs the full harvest once a week (every Sunday at 08:00 by default).

Usage:
    python scheduler.py

The schedule time is configurable via the HARVEST_SCHEDULE environment variable:
    HARVEST_SCHEDULE="sunday 08:00" python scheduler.py
    HARVEST_SCHEDULE="monday 06:30" python scheduler.py

Valid day values: monday, tuesday, wednesday, thursday, friday, saturday, sunday
Time format: HH:MM (24-hour clock)

The scheduler uses Python's lightweight `schedule` package (pip install schedule).
It costs nothing — no cloud services or subscriptions required.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

try:
    import schedule
except ImportError:
    print(
        "💥 The 'schedule' package is required. Install it with:\n"
        "   pip install schedule\n"
        "   or:  pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

import time

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


def _silence_playwright_shutdown(
    loop: asyncio.AbstractEventLoop, context: dict
) -> None:
    exc = context.get("exception")
    if exc is not None and type(exc).__name__ == "TargetClosedError":
        return
    loop.default_exception_handler(context)


def run_harvest(diocese: str = "derry_diocese") -> None:
    """Run the full harvest pipeline — same logic as main.py."""
    start = datetime.now(timezone.utc)
    print(f"\n🕐 Scheduled harvest started at {start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"📋 Diocese: {diocese}")

    target = target_sunday()
    print(f"🗓️  Target date: {target}")

    try:
        entries = parse_evidence_file(diocese, PARISHES_DIR)
    except FileNotFoundError as exc:
        print(f"💥 {exc}", file=sys.stderr)
        return

    print(f"⛪ Parishes: {len(entries)}")
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

    for r in results:
        log_result(r, r.key, r.display_name)

    print(f"  ✅ Downloaded  : {ok_count}")
    print(f"  🔗 HTML links  : {html_count}")
    print(f"  💥 Failed      : {err_count}")

    print("\n── Report ──────────────────────────────────────────────────")
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

    print("\n── Stitch Mega PDF ─────────────────────────────────────────")
    contacts_path = PARISHES_DIR / f"{diocese}_contacts.json"
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

    print_summary()

    end = datetime.now(timezone.utc)
    duration = (end - start).total_seconds()

    # Send email notification
    print("\n── Notification ────────────────────────────────────────────")
    send_harvest_notification(REPORT_JSON, duration_seconds=duration)

    print(f"\n✅ Scheduled harvest finished at {end.strftime('%Y-%m-%d %H:%M:%S UTC')} "
          f"(took {duration:.0f}s)")


def _parse_schedule(spec: str) -> tuple[str, str]:
    """Parse a schedule spec like 'sunday 08:00' into (day, time).

    Returns (day_lower, time_str) or raises ValueError.
    """
    parts = spec.strip().lower().split()
    if len(parts) != 2:
        raise ValueError(
            f"Invalid HARVEST_SCHEDULE format: {spec!r}. "
            "Expected 'DAY HH:MM', e.g. 'sunday 08:00'."
        )
    day, time_str = parts
    valid_days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    if day not in valid_days:
        raise ValueError(f"Invalid day: {day!r}. Must be one of: {', '.join(sorted(valid_days))}")
    # Basic time format check
    h, _, m = time_str.partition(":")
    if not (h.isdigit() and m.isdigit() and 0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ValueError(f"Invalid time: {time_str!r}. Expected HH:MM (24-hour).")
    return day, time_str


def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    harvest_spec = os.environ.get("HARVEST_SCHEDULE", "sunday 08:00")
    diocese = os.environ.get("HARVEST_DIOCESE", "derry_diocese")

    try:
        day, run_time = _parse_schedule(harvest_spec)
    except ValueError as exc:
        print(f"💥 {exc}", file=sys.stderr)
        sys.exit(1)

    day_job = getattr(schedule.every(), day)
    day_job.at(run_time).do(run_harvest, diocese=diocese)

    print(f"⏰ Parish Bulletin Harvester scheduler started.")
    print(f"   Schedule : every {day.capitalize()} at {run_time}")
    print(f"   Diocese  : {diocese}")
    print(f"   Override : set HARVEST_SCHEDULE='<day> HH:MM' or HARVEST_DIOCESE='<name>'")
    print(f"   Stop     : press Ctrl+C\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
