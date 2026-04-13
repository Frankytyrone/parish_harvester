"""
stitcher.py — Mega PDF stitcher for the Parish Bulletin Harvester.

Merges all downloaded PDFs (A–Z) into one mega PDF.
Creates clickable link pages for HTML-only and failed parishes.
"""
from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fetcher import FetchResult


def _xml_escape(text: str) -> str:
    """Escape XML/HTML special characters for use in ReportLab markup."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def stitch_mega_pdf(
    results: list["FetchResult"],
    current_dir: Path,
    bulletins_dir: Path,
    target: date,
    contacts_path: Path | None = None,
) -> None:
    """
    Merge all downloaded PDFs and create placeholder pages for HTML-only
    and failed parishes, then write a single A–Z mega PDF.
    """
    try:
        import PyPDF2
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
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

    # Build map: key → (pdf_path | None, url, display_name)
    parish_map: dict[str, tuple[Path | None, str, str]] = {}
    for r in results:
        key = r.key
        if r.status == "ok" and r.file_path:
            pdf_path: Path | None = current_dir / r.file_path.name
            if not (pdf_path and pdf_path.exists()):
                pdf_path = None
            parish_map[key] = (pdf_path, r.url, r.display_name)
        elif r.status == "html_link":
            parish_map[key] = (None, r.url, r.display_name)
        else:
            parish_map.setdefault(key, (None, r.url, r.display_name))

    sorted_entries = sorted(parish_map.items())

    output_path = bulletins_dir / f"all_bulletins_{target}.pdf"
    merger = PyPDF2.PdfWriter()
    real_count = 0
    placeholder_count = 0
    styles = getSampleStyleSheet()

    for parish_key, (pdf_path, parish_url, display_name) in sorted_entries:
        # Try to look up contacts info
        info = contacts.get(parish_key, {})
        if not display_name:
            display_name = info.get("display_name") or parish_key.replace("_", " ").title()
        website = info.get("website")
        facebook = info.get("facebook")

        if pdf_path and pdf_path.exists():
            try:
                reader = PyPDF2.PdfReader(str(pdf_path))
                for page in reader.pages:
                    merger.add_page(page)
                real_count += 1
                continue
            except Exception as exc:
                print(f"    ⚠️  Could not merge {parish_key}: {exc}")

        # Placeholder page for missing/failed bulletins
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            topMargin=3 * cm, bottomMargin=3 * cm,
            leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        )

        link_items: list[str] = []

        # If parish_url is an HTML link (html_link status or no PDF found)
        if parish_url and parish_url.startswith("http"):
            safe_url = _xml_escape(parish_url)
            link_items.append(
                f'📋 <b>Click here to view the bulletin online</b>: '
                f'<link href="{parish_url}" color="blue">{safe_url}</link>'
            )

        if website and website != parish_url:
            link_items.append(
                f'🌐 Parish Website: <link href="{website}" color="blue">'
                f'{_xml_escape(website)}</link>'
            )
        if facebook:
            link_items.append(
                f'📘 Facebook: <link href="{facebook}" color="blue">'
                f'{_xml_escape(facebook)}</link>'
            )
        if not link_items:
            link_items.append("Please contact the parish directly.")

        story = [
            Paragraph(display_name, styles["Title"]),
            Spacer(1, 0.5 * cm),
            HRFlowable(width="100%", thickness=1, color=colors.grey),
            Spacer(1, 0.5 * cm),
            Paragraph(
                f"This week's bulletin for <b>{display_name}</b> "
                "is not available as a PDF.",
                styles["Heading2"],
            ),
            Spacer(1, 0.4 * cm),
            Paragraph("To find the bulletin, please visit:", styles["Normal"]),
            Spacer(1, 0.3 * cm),
        ]
        for item in link_items:
            story.append(Paragraph(item, styles["Normal"]))
            story.append(Spacer(1, 0.2 * cm))

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
        bulletins_dir.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as fh:
            merger.write(fh)
        print(f"  📖 Mega PDF      : {output_path}")
        print(f"     Real PDFs      : {real_count}")
        print(f"     Placeholders   : {placeholder_count}")
    else:
        print("  ⚠️  No pages to include in mega PDF — skipping.")
