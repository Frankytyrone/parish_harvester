"""
main.py — CLI entry point for the Parish Bulletin Harvester v2.

Usage:
    python main.py [--diocese DIOCESE] [--target-date YYYY-MM-DD] [--dry-run]
    python main.py --train "Parish Name" [--diocese DIOCESE]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
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
from harvester.dashboard_generator import generate_dashboard
from harvester.email_notifier import send_harvest_notification
from harvester.fetcher import FetchResult, fetch_all, parse_evidence_file
from harvester.harvest_log import (
    log_result,
    print_summary,
    update_consecutive_failures,
    update_stale_bulletins,
)
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


def _discover_dioceses(parishes_dir: Path) -> list[str]:
    """Return sorted list of diocese names from evidence files in *parishes_dir*."""
    return sorted(
        p.stem.replace("_bulletin_urls", "")
        for p in parishes_dir.glob("*_bulletin_urls.txt")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parish Bulletin Harvester — evidence-driven downloader."
    )
    parser.add_argument(
        "--diocese",
        default="all",
        help=(
            "Diocese name or 'all' to run every diocese found in parishes/. "
            "(default: all)"
        ),
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
    parser.add_argument(
        "--target-parish",
        default=None,
        metavar="PARISH_KEY",
        help=(
            "Instantly rebuild the Mega PDF for a single parish key only. "
            "The fetcher runs only for that parish; all other PDFs are "
            "reused from the existing Bulletins/current/ cache."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.WARNING)
    harvest_start = time.monotonic()

    if args.train:
        # Training always targets a single diocese
        diocese = args.diocese if args.diocese != "all" else "derry_diocese"
        try:
            asyncio.run(
                run_training(
                    parish_query=args.train,
                    diocese=diocese,
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

    # Determine which dioceses to run
    if args.diocese == "all":
        dioceses = _discover_dioceses(PARISHES_DIR)
        if not dioceses:
            print("💥 No diocese evidence files found in parishes/", file=sys.stderr)
            return 1
        print(f"📋 Dioceses     : {', '.join(dioceses)}")
    else:
        dioceses = [args.diocese]
        print(f"📋 Diocese      : {args.diocese}")

    # Fetch bulletins for all requested dioceses
    all_results = []
    # Track results per diocese for per-diocese mega PDFs
    diocese_results: dict[str, list] = {}
    for diocese in dioceses:
        if len(dioceses) > 1:
            print(f"\n{'═' * 58}")
            print(f"📍 Diocese: {diocese}")
            print('═' * 58)
        try:
            entries = parse_evidence_file(diocese, PARISHES_DIR)
        except FileNotFoundError as exc:
            print(f"💥 {exc}", file=sys.stderr)
            if len(dioceses) == 1:
                return 1
            continue

        # When --target-parish is set, only fetch that one parish.
        target_parish_key = (args.target_parish or "").strip().lower()
        if target_parish_key:
            entries = [e for e in entries if e.key == target_parish_key]
            if not entries:
                print(
                    f"⚠️  Parish key '{target_parish_key}' not found in {diocese}.",
                    file=sys.stderr,
                )
                continue

        print(f"⛪ Parishes     : {len(entries)}")
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

        all_results.extend(results)
        diocese_results[diocese] = results

    if args.dry_run:
        print("\n⚠️  --dry-run: stopping after fetch.")
        return 0

    if not all_results:
        print("⚠️  No results to report.", file=sys.stderr)
        return 1

    update_consecutive_failures(all_results)
    update_stale_bulletins(all_results)

    # Generate combined report (across all dioceses)
    print("\n── Report ──────────────────────────────────────────────────")
    # Use first diocese for contacts lookup when running a single diocese
    primary_diocese = dioceses[0]
    contacts_path = PARISHES_DIR / f"{primary_diocese}_contacts.json"

    target_parish_key = (args.target_parish or "").strip().lower()

    if target_parish_key:
        # ── Instant single-parish rebuild ──────────────────────────────
        # Update only the target parish's PDF in current_dir (do NOT purge
        # the other parishes' cached PDFs so they remain in the Mega PDF).
        CURRENT_DIR.mkdir(parents=True, exist_ok=True)
        target_result = next(
            (r for r in all_results if r.key == target_parish_key and r.status == "ok"),
            None,
        )
        if target_result and target_result.file_path and target_result.file_path.exists():
            dest = CURRENT_DIR / target_result.file_path.name
            shutil.copy2(target_result.file_path, dest)
            print(f"  📄 Updated     : {dest.name}")
        else:
            status_r = next((r for r in all_results if r.key == target_parish_key), None)
            reason = getattr(status_r, "error", None) or "unknown"
            print(f"  ⚠️  No PDF downloaded for '{target_parish_key}': {reason}")

        # Load contacts for display name lookup
        contacts: dict = {}
        if contacts_path.exists():
            try:
                contacts = json.loads(contacts_path.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"  ⚠️  Could not load contacts: {exc}")

        # Build FetchResult stubs for every PDF already in current_dir so
        # the stitcher produces a complete Mega PDF with all parishes.
        stitch_results: list[FetchResult] = []
        for pdf in sorted(CURRENT_DIR.glob("*.pdf")):
            key = pdf.stem
            info = contacts.get(key, {})
            display_name = info.get("display_name") or key.replace("_", " ").title()
            stitch_results.append(
                FetchResult(
                    key=key,
                    display_name=display_name,
                    status="ok",
                    url=info.get("website", ""),
                    file_path=pdf,
                )
            )

        print(
            f"  📚 Stitching   : {len(stitch_results)} parish PDF(s) from cache + new fetch"
        )
    else:
        generate_report(
            all_results,
            raw_dir=RAW_DIR,
            current_dir=CURRENT_DIR,
            report_json=REPORT_JSON,
            report_txt=REPORT_TXT,
            target=target,
        )
        stitch_results = all_results

    print(f"  📄 Report JSON : {REPORT_JSON}")
    print(f"  📄 Report TXT  : {REPORT_TXT}")

    # Generate dashboard
    print("\n── Dashboard ───────────────────────────────────────────────")
    dashboard_path = BULLETINS_DIR / "dashboard.html"
    try:
        generate_dashboard(
            report_path=REPORT_JSON,
            log_path=Path("harvest_log.json"),
            output_path=dashboard_path,
        )
    except Exception as exc:
        print(f"  ⚠️  Dashboard generation failed (non-fatal): {exc}")

    # Stitch mega PDF
    print("\n── Stitch Mega PDF ─────────────────────────────────────────")
    try:
        stitch_mega_pdf(
            stitch_results,
            current_dir=CURRENT_DIR,
            bulletins_dir=BULLETINS_DIR,
            target=target,
            contacts_path=contacts_path if contacts_path.exists() else None,
            mega_excludes_path=PARISHES_DIR / "mega_excludes.json",
        )
    except Exception as exc:
        print(f"  ⚠️  Mega PDF generation failed (non-fatal): {exc}")

    # Stitch per-diocese mega PDFs (skip when running a single-parish rebuild)
    if not target_parish_key and diocese_results:
        print("\n── Per-Diocese Mega PDFs ───────────────────────────────────")
        mega_pdf_dir = Path("mega_pdf")
        mega_pdf_dir.mkdir(exist_ok=True)
        for d_name, d_results in sorted(diocese_results.items()):
            # Normalise diocese name for the output filename
            # (e.g. 'derry_diocese' → 'derry', 'down_and_connor' unchanged)
            short = d_name.removesuffix("_diocese")
            diocese_pdf = mega_pdf_dir / f"{short}_mega_bulletin.pdf"
            d_contacts = PARISHES_DIR / f"{d_name}_contacts.json"
            try:
                stitch_mega_pdf(
                    d_results,
                    current_dir=CURRENT_DIR,
                    bulletins_dir=BULLETINS_DIR,
                    target=target,
                    contacts_path=d_contacts if d_contacts.exists() else None,
                    mega_excludes_path=PARISHES_DIR / "mega_excludes.json",
                    output_path=diocese_pdf,
                )
                print(f"  📖 {short} mega PDF : {diocese_pdf}")
            except Exception as exc:
                print(f"  ⚠️  {short} mega PDF failed (non-fatal): {exc}")

    # Print harvest log summary
    print_summary()

    # Send email notification
    print("\n── Notification ────────────────────────────────────────────")
    send_harvest_notification(REPORT_JSON, duration_seconds=time.monotonic() - harvest_start)

    return 0


if __name__ == "__main__":
    sys.exit(main())
