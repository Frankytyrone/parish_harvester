"""
stitcher.py — Mega PDF stitcher for the Parish Bulletin Harvester.

Merges all downloaded PDFs (A-Z) into one mega PDF.
Appends a compact summary section for HTML-only and failed parishes.
"""
from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fetcher import FetchResult


# Characters that are considered "filler" and should not count as real content
# when deciding whether a PDF page is blank/near-blank.
# Covers whitespace, ALL ASCII control chars (incl. form feed \x0c),
# invisible Unicode (NBSP, soft-hyphen, zero-width chars, BOM),
# bullets, dashes, smart-quotes, ellipsis, and standalone punctuation.
_FILLER_PATTERN = re.compile(
    r'[\s\x00-\x1f\x7f\xa0\xad'
    r'\u200b\u200c\u200d\ufeff'
    r'\u2022\u00b7\u2019\u2018\u2026\u2013\u2014'
    r'.,:;!?\-_|]+')
# Minimum number of meaningful characters for a page to be kept.
# Real bulletin pages always contain hundreds of characters; this threshold
# catches truly blank pages (0 chars), dot/dash separator pages,
# near-blank pages with only a page number, and control-character-only pages.
_MIN_MEANINGFUL_CHARS = 30
# Parish bulletins are never longer than 4 pages.  Any PDF with more pages
# is almost certainly a full document (parish magazine, booklet, etc.) that
# was accidentally downloaded instead of the weekly bulletin.
_MAX_BULLETIN_PAGES = 4

_HEADER_BANNER_HEIGHT = 18
_HEADER_TOP_MARGIN = 8
_HEADER_SIDE_MARGIN = 20
_HEADER_RULE_SIDE_PADDING = 16
_HEADER_BACKGROUND_ALPHA = 0.75
_HEADER_BACKGROUND_OFFSET = 4

def _xml_escape(text: str) -> str:
    """Escape XML/HTML special characters for use in ReportLab markup."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_parish_header_pdf(
    display_name: str,
    website: str | None,
    pagesize: tuple[float, float],
    colors_module,
    canvas_module,
) -> io.BytesIO:
    """Create a transparent top-banner overlay with parish name + website link."""
    buf = io.BytesIO()
    width, height = pagesize
    c = canvas_module.Canvas(buf, pagesize=pagesize)

    banner_h = _HEADER_BANNER_HEIGHT
    top = height - _HEADER_TOP_MARGIN
    c.setFillColor(colors_module.Color(1, 1, 1, alpha=_HEADER_BACKGROUND_ALPHA))
    c.rect(0, height - banner_h - _HEADER_BACKGROUND_OFFSET, width, banner_h + _HEADER_BACKGROUND_OFFSET, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors_module.black)
    c.drawString(_HEADER_SIDE_MARGIN, top - 8, display_name)

    if website:
        c.setFont("Helvetica", 8)
        c.setFillColor(colors_module.blue)
        c.drawRightString(width - _HEADER_SIDE_MARGIN, top - 8, website)
        text_w = c.stringWidth(website, "Helvetica", 8)
        c.linkURL(
            website,
            (
                width - _HEADER_SIDE_MARGIN - text_w,
                top - 11,
                width - _HEADER_SIDE_MARGIN,
                top - 2,
            ),
            relative=0,
            thickness=0,
            color=colors_module.blue,
        )

    c.setStrokeColor(colors_module.Color(0.85, 0.85, 0.85))
    c.line(_HEADER_RULE_SIDE_PADDING, height - banner_h - _HEADER_BACKGROUND_OFFSET, width - _HEADER_RULE_SIDE_PADDING, height - banner_h - _HEADER_BACKGROUND_OFFSET)
    c.save()
    buf.seek(0)
    return buf


def stitch_mega_pdf(
    results: list["FetchResult"],
    current_dir: Path,
    bulletins_dir: Path,
    target: date,
    contacts_path: Path | None = None,
) -> None:
    """
    Merge all downloaded PDFs (A-Z by display name) into one mega PDF, then
    append a single compact summary page listing all HTML-only and unavailable
    parishes.
    """
    try:
        import PyPDF2
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
    except ImportError as exc:
        print(f"  ⚠️  Skipping mega PDF — missing library: {exc}")
        return

    # Load parish contacts for display names / website links
    contacts: dict = {}
    if contacts_path and contacts_path.exists():
        try:
            contacts = json.loads(contacts_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  ⚠️  Could not load contacts file: {exc}")

    # Build map: key -> (pdf_path | None, url, display_name)
    parish_map: dict[str, tuple[Path | None, str, str]] = {}
    for r in results:
        key = r.key
        # Keep stale historical fallback results out of the mega PDF.
        if r.is_fallback:
            continue
        if r.status == "ok" and r.file_path:
            pdf_path: Path | None = current_dir / r.file_path.name
            if not (pdf_path and pdf_path.exists()):
                pdf_path = None
            parish_map[key] = (pdf_path, r.url, r.display_name)
        elif r.status == "html_link":
            parish_map[key] = (None, r.url, r.display_name)
        else:
            parish_map.setdefault(key, (None, r.url, r.display_name))

    # Sort A-Z by human display name (not domain key)
    sorted_entries = sorted(
        parish_map.items(),
        key=lambda item: item[1][2].lower() if item[1][2] else item[0].lower()
    )

    output_path = bulletins_dir / f"all_bulletins_{target}.pdf"
    merger = PyPDF2.PdfWriter()
    real_count = 0
    styles = getSampleStyleSheet()

    # Collect parishes without a PDF for the compact summary section
    missing_entries: list[tuple[str, str, str | None]] = []

    for parish_key, (pdf_path, parish_url, display_name) in sorted_entries:
        info = contacts.get(parish_key, {})
        if not display_name:
            display_name = info.get("display_name") or parish_key.replace("_", " ").title()
        website: str | None = info.get("website")

        if pdf_path and pdf_path.exists():
            try:
                if website and website.startswith("http"):
                    link_url = website
                elif parish_url and parish_url.startswith("http"):
                    link_url = parish_url
                else:
                    link_url = None
                reader = PyPDF2.PdfReader(str(pdf_path))
                page_count = len(reader.pages)
                if page_count > _MAX_BULLETIN_PAGES:
                    print(
                        f"    ⚠️  Skipping {parish_key}: {page_count} pages exceeds "
                        f"the {_MAX_BULLETIN_PAGES}-page bulletin limit (likely a full document)"
                    )
                    missing_entries.append((display_name, parish_url, website))
                    continue
                for idx, page in enumerate(reader.pages):
                    if idx == 0:
                        page_w = float(page.mediabox.width)
                        page_h = float(page.mediabox.height)
                        header_pdf = _build_parish_header_pdf(
                            display_name,
                            link_url,
                            (page_w, page_h),
                            colors,
                            canvas,
                        )
                        header_reader = PyPDF2.PdfReader(header_pdf)
                        if header_reader.pages:
                            page.merge_page(header_reader.pages[0])
                    # Skip blank or near-blank pages (no real text content).
                    # Strips all invisible/filler characters before counting —
                    # catches form-feed-only pages, dot-separator pages, etc.
                    try:
                        text = page.extract_text() or ""
                        meaningful = _FILLER_PATTERN.sub('', text)
                        if len(meaningful) < _MIN_MEANINGFUL_CHARS:
                            continue
                    except Exception:
                        pass  # If we can't extract text, include the page to be safe
                    merger.add_page(page)
                real_count += 1
            except Exception as exc:
                print(f"    ⚠️  Could not merge {parish_key}: {exc}")
                missing_entries.append((display_name, parish_url, website))
        else:
            missing_entries.append((display_name, parish_url, website))

    # Build a single compact summary page for all missing/HTML parishes
    summary_page_count = 0
    if missing_entries:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
            leftMargin=2 * cm, rightMargin=2 * cm,
        )
        story: list = [
            Paragraph("Missing &amp; Online-Only Bulletins", styles["Title"]),
            Spacer(1, 0.25 * cm),
            HRFlowable(width="100%", thickness=1, color=colors.grey),
            Spacer(1, 0.2 * cm),
            Paragraph(
                "The following parishes do not have a downloadable PDF bulletin. "
                "Click a link to view the bulletin online.",
                styles["Normal"],
            ),
            Spacer(1, 0.15 * cm),
        ]
        small_style = styles["Normal"].clone("Small")
        small_style.fontSize = 9
        small_style.leading = 11
        # Sort missing entries A-Z by display name
        missing_entries.sort(key=lambda x: x[0].lower())
        for display_name, parish_url, website in missing_entries:
            name_esc = _xml_escape(display_name)
            link_url = parish_url if (parish_url and parish_url.startswith("http")) else website
            if link_url:
                safe_link = _xml_escape(link_url)
                line = (
                    f'<b>{name_esc}</b>: '
                    f'<link href="{link_url}" color="blue">{safe_link}</link>'
                )
            else:
                line = f'<b>{name_esc}</b>: contact parish directly'
            story.append(Paragraph(line, small_style))
            story.append(Spacer(1, 0.05 * cm))

        try:
            doc.build(story)
            buf.seek(0)
            summary_reader = PyPDF2.PdfReader(buf)
            for page in summary_reader.pages:
                merger.add_page(page)
            summary_page_count = len(summary_reader.pages)
        except Exception as exc:
            print(f"    ⚠️  Could not create summary page: {exc}")

    if real_count + summary_page_count > 0:
        bulletins_dir.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as fh:
            merger.write(fh)
        print(f"  📖 Mega PDF      : {output_path}")
        print(f"     Real PDFs      : {real_count}")
        print(f"     Online-only    : {len(missing_entries)} (condensed to {summary_page_count} summary page(s))")
    else:
        print("  ⚠️  No pages to include in mega PDF — skipping.")
