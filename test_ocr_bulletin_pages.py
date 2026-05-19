from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ocr.generate_bulletin_pages import (
    DioceseConfig,
    extract_ocr_fragment,
    parse_parish_links,
    render_viewer_page,
)


class OcrBulletinPageTests(unittest.TestCase):
    def test_parse_parish_links_uses_first_url_after_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = Path(tmpdir) / "bulletin_urls.txt"
            evidence.write_text(
                "# --- Parish One ---\n"
                "# comment\n"
                "https://example.com/one\n"
                "https://example.com/one-older\n"
                "\n"
                "# --- Parish Two ---\n"
                "https://example.com/two\n",
                encoding="utf-8",
            )

            self.assertEqual(
                parse_parish_links(evidence),
                [
                    ("Parish One", "https://example.com/one"),
                    ("Parish Two", "https://example.com/two"),
                ],
            )

    def test_extract_ocr_fragment_and_render_viewer_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ocr_html = tmp / "bulletin.html"
            ocr_html.write_text(
                "<html><body><div class=\"scrollable-viewer\">"
                "<h2>Page 1</h2><p>Call 028 1234 5678</p><hr><h2>Page 2</h2><p>Email test@example.com</p>"
                "</div></body></html>",
                encoding="utf-8",
            )
            fragment = extract_ocr_fragment(ocr_html)
            self.assertIn("<h3>PAGE 1</h3>", fragment)
            self.assertIn("<h3>PAGE 2</h3>", fragment)

            config = DioceseConfig(
                key="test",
                display_name="Test Diocese",
                headline="TEST DIOCESE BIG BULLETIN",
                evidence_path=tmp / "unused.txt",
                pdf_filename="test_mega_bulletin.pdf",
            )

            html_output = render_viewer_page(
                config=config,
                bulletin_date="2026-05-19",
                page_count=2,
                ocr_fragment=fragment,
                parish_links=[("Parish One", "https://example.com/one")],
            )

            self.assertIn("TEST DIOCESE BIG BULLETIN", html_output)
            self.assertIn("Page 1 of 2", html_output)
            self.assertIn("../mega_pdf/test_mega_bulletin.pdf", html_output)
            self.assertIn("PARISHES WITH WORKING BULLETIN LINKS", html_output.upper())
            self.assertIn("https://example.com/one", html_output)


if __name__ == "__main__":
    unittest.main()
