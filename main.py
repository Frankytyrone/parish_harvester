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
# Stage 4: Stitch A–Z mega PDF
# ---------------------------------------------------------------------------

def _stitch_mega_pdf(
    urls: list[str],
    fetch_results: list,
    current_dir: Path,
    target: date,
) -> None:
    """
    Merge all fresh PDFs in *current_dir* into a single A–Z mega PDF.
    Parishes with no valid PDF get a placeholder page with a clickable link.
    """
    try:
        import PyPDF2
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        from reportlab.lib import colors
        from reportlab.platypus.flowables import HRFlowable
        import io
    except ImportError as exc:
        print(f"  ⚠️  Skipping mega PDF — missing library: {exc}")
        return

    from harvester.utils import parish_name_from_url

    # Build a mapping: parish_key → (pdf_path | None, parish_url)
    # parish_key is the sanitized parish name used as filename prefix
    parish_map: dict[str, tuple[Path | None, str]] = {}
    for fr in fetch_results:
        key = fr.parish
        if fr.status == "ok" and fr.file_path:
            pdf_path = current_dir / fr.file_path.name
            if not pdf_path.exists():
                # may still be in raw if verifier marked stale
                pdf_path = None
            parish_map[key] = (pdf_path if (pdf_path and pdf_path.exists()) else None, fr.url)
        else:
            parish_map.setdefault(key, (None, fr.url))

    # Sort entries A–Z by parish key
    sorted_entries = sorted(parish_map.items())

    output_path = BULLETINS_DIR / f"all_bulletins_{target}.pdf"
    merger = PyPDF2.PdfWriter()
    real_count = 0
    placeholder_count = 0

    styles = getSampleStyleSheet()

    for parish_key, (pdf_path, parish_url) in sorted_entries:
        if pdf_path and pdf_path.exists():
            try:
                reader = PyPDF2.PdfReader(str(pdf_path))
                for page in reader.pages:
                    merger.add_page(page)
                real_count += 1
            except Exception as exc:
                print(f"    ⚠️  Could not merge {parish_key}: {exc}")
                pdf_path = None  # fall through to placeholder

        if not pdf_path or not pdf_path.exists():
            # Generate a placeholder page via reportlab
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4,
                                    topMargin=3*cm, bottomMargin=3*cm,
                                    leftMargin=2.5*cm, rightMargin=2.5*cm)
            parish_display = parish_key.replace("_", " ").title()
            link_para = (
                f'<link href="{parish_url}" color="blue">'
                f'{parish_url}'
                f'</link>'
            )
            story = [
                Paragraph(parish_display, styles["Title"]),
                Spacer(1, 0.5*cm),
                HRFlowable(width="100%", thickness=1, color=colors.grey),
                Spacer(1, 0.5*cm),
                Paragraph("Bulletin not available this week", styles["Heading2"]),
                Spacer(1, 0.5*cm),
                Paragraph(
                    "Please visit the parish website to find the bulletin:",
                    styles["Normal"],
                ),
                Spacer(1, 0.3*cm),
                Paragraph(link_para, styles["Normal"]),
            ]
            try:
                doc.build(story)
                buf.seek(0)
                placeholder_reader = PyPDF2.PdfReader(buf)
                for page in placeholder_reader.pages:
                    merger.add_page(page)
                placeholder_count += 1
            except Exception as exc:
                print(f"    ⚠️  Could not create placeholder for {parish_key}: {exc}")

    if real_count + placeholder_count > 0:
        with output_path.open("wb") as fh:
            merger.write(fh)
        print(f"  📖 Mega PDF  : {output_path}")
        print(f"     Real PDFs      : {real_count}")
        print(f"     Placeholders   : {placeholder_count}")
    else:
        print("  ⚠️  No pages to include in mega PDF — skipping.")


# ---------------------------------------------------------------------------
# Stage 5: Write Copilot review file
# ---------------------------------------------------------------------------

def _write_copilot_review(
    fetch_results: list,
    result,
    target: date,
    history_dir: Path,
) -> None:
    """Write a Copilot-readable review file summarising this run."""
    from harvester.cleaner import HISTORY_DIR

    review_path = BULLETINS_DIR / "copilot_review.md"
    lines = [
        "# Copilot Review — Parish Bulletin Harvester",
        "",
        f"**Run date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Target Sunday:** {target}",
        "",
        "## Summary",
        "",
        f"| Category | Count |",
        f"|----------|-------|",
        f"| ✅ Fresh   | {len(result.fresh)} |",
        f"| ❌ Stale   | {len(result.stale)} |",
        f"| ⚠️ Unknown | {len(result.unknown)} |",
        f"| 💥 Errors  | {len(result.errors)} |",
        "",
    ]

    if result.errors:
        lines += [
            "## Errors this run",
            "",
        ]
        for e in result.errors:
            lines.append(f"- **{e['parish']}**: {e['verdict']}")
        lines.append("")

    # Check history for consistently failing parishes
    consistent_failures: dict[str, int] = {}
    history_dir_path = HISTORY_DIR
    if history_dir_path.exists():
        history_files = sorted(history_dir_path.glob("report_*.json"))[-8:]  # last 8 reports
        for hf in history_files:
            try:
                import json
                data = json.loads(hf.read_text(encoding="utf-8"))
                for err_entry in data.get("errors", []):
                    p = err_entry.get("parish", "")
                    consistent_failures[p] = consistent_failures.get(p, 0) + 1
            except Exception:
                pass

    if consistent_failures:
        lines += [
            "## Consistently failing parishes (last 8 reports)",
            "",
        ]
        for parish, count in sorted(consistent_failures.items(), key=lambda x: -x[1]):
            if count >= 2:
                lines.append(f"- **{parish}**: failed {count} time(s) in recent runs")
                if count >= 4:
                    lines.append(
                        f"  > 💡 Suggestion: Consider removing **{parish}** — "
                        f"it has failed {count} time(s) in recent runs."
                    )
        lines.append("")

    lines += [
        "## Suggestions for next run",
        "",
        "- Review the errors above and check whether the parish websites are still active.",
        "- Parishes consistently failing may have changed their URL structure.",
        "- If a parish always returns 'No PDF found', consider adding its URL directly to the list.",
        "",
        "---",
        "_This file is auto-generated by the Parish Bulletin Harvester. "
        "It is committed to the repository so Copilot can read it in future PRs._",
    ]

    BULLETINS_DIR.mkdir(parents=True, exist_ok=True)
    review_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  🤖 Copilot review: {review_path}")


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
        verify_queue = [
            r for r in fetch_results
            if r.status == "ok" and r.file_path and r.file_path.exists()
        ]
        total_verify = len(verify_queue)
        for i, r in enumerate(verify_queue):
            verdict = verify_file(r.file_path, target)
            verdicts[r.file_path.name] = verdict
            icon = {"FRESH": "✅", "STALE": "❌", "UNKNOWN": "⚠️ "}.get(
                verdict.split(":")[0], "💥"
            )
            print(f"  {icon} {r.parish}: {verdict}")
            # Rate-limit: stay under 10 requests per 60 s
            if i < total_verify - 1:
                print(f"  ⏳ Rate limit pause ({i + 1}/{total_verify})...")
                time.sleep(7)

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

    # ------------------------------------------------------------------
    # Stage 4: Stitch A–Z mega PDF
    # ------------------------------------------------------------------
    print("\n── Stage 4: Stitch Mega PDF ────────────────────────────────")
    try:
        _stitch_mega_pdf(urls, fetch_results, CURRENT_DIR, target)
    except Exception as exc:
        print(f"  ⚠️  Mega PDF generation failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Stage 5: Write Copilot review
    # ------------------------------------------------------------------
    print("\n── Stage 5: Copilot Review ─────────────────────────────────")
    try:
        from harvester.cleaner import HISTORY_DIR
        _write_copilot_review(fetch_results, result, target, HISTORY_DIR)
    except Exception as exc:
        print(f"  ⚠️  Copilot review failed (non-fatal): {exc}")

    # Exit 0 always — errors are logged in the reports.
    # Only return 1 if something truly catastrophic happened (unhandled exception above).
    return 0


if __name__ == "__main__":
    sys.exit(main())
