from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from harvester.fetcher import parse_evidence_file
from harvester.stitcher import _MAX_BULLETIN_PAGES, stitch_mega_pdf
from train import _CLICK_TRACKER_JS, _build_mark_step, _match_parish


class ParishMatchingTests(unittest.TestCase):
    def _write_evidence(self, root: Path, diocese: str, content: str) -> None:
        (root / f"{diocese}_bulletin_urls.txt").write_text(content, encoding="utf-8")

    def test_parse_evidence_file_handles_header_and_url_format_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._write_evidence(
                base,
                "down_and_connor",
                """
# -- Antrim --
# page: https://www.antrimparish.com/bulletinpage/
# html_link
- https://www.antrimparish.com

# ——— Aghagallon and Ballinderry ———
# Pattern D
# html_link
• https://www.aghagallonandballinderryparish.ie
                """.strip(),
            )

            entries = parse_evidence_file("down_and_connor", base)
            names = [entry.display_name for entry in entries]
            self.assertEqual(names, ["Antrim", "Aghagallon and Ballinderry"])
            self.assertEqual(entries[0].example_url, "https://www.antrimparish.com")
            self.assertEqual(entries[1].example_url, "https://www.aghagallonandballinderryparish.ie")

    def test_match_parish_handles_common_name_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._write_evidence(
                base,
                "down_and_connor",
                """
# --- Aghagallon and Ballinderry ---
# html_link
https://www.aghagallonandballinderryparish.ie

# --- Saint Malachy's ---
# html_link
https://www.saintmalachysparish.com/
                """.strip(),
            )

            match_1 = _match_parish("Aghagallon & Ballinderry", "down_and_connor", base)
            self.assertEqual(match_1.entry.display_name, "Aghagallon and Ballinderry")

            match_2 = _match_parish("St Malachys", "down_and_connor", base)
            self.assertEqual(match_2.entry.display_name, "Saint Malachy's")

    def test_match_parish_ignores_nested_parenthetical_parts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._write_evidence(
                base,
                "derry_diocese",
                """
# --- Example Parish (Outer (Inner)) ---
# html_link
https://example.org/bulletin
                """.strip(),
            )

            match = _match_parish("Example Parish", "derry_diocese", base)
            self.assertEqual(match.entry.display_name, "Example Parish (Outer (Inner))")

    def test_match_parish_mismatch_error_lists_detected_parishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._write_evidence(
                base,
                "down_and_connor",
                """
# --- Antrim ---
# html_link
https://www.antrimparish.com
                """.strip(),
            )

            with self.assertRaises(ValueError) as ctx:
                _match_parish("NotAParish", "down_and_connor", base)

            msg = str(ctx.exception)
            self.assertIn('No parish matched "NotAParish"', msg)
            self.assertIn("Detected parishes:", msg)
            self.assertIn("Antrim", msg)

    def test_problematic_real_world_parishes_match_from_repository_file(self) -> None:
        repo_root = Path(__file__).resolve().parent
        parishes_dir = repo_root / "parishes"

        for name in ("Aghagallon and Ballinderry", "Antrim"):
            with self.subTest(name=name):
                match = _match_parish(name, None, parishes_dir)
                self.assertEqual(match.entry.display_name, name)

    def test_build_mark_step_validates_http_and_supported_actions(self) -> None:
        self.assertEqual(
            _build_mark_step("image", "https://example.org/bulletin.png"),
            {"action": "image", "url": "https://example.org/bulletin.png"},
        )
        self.assertEqual(
            _build_mark_step("html", "http://example.org/news"),
            {"action": "html", "url": "http://example.org/news"},
        )
        self.assertIsNone(_build_mark_step("image", "javascript:alert(1)"))
        self.assertIsNone(_build_mark_step("download", "https://example.org/file.pdf"))

    def test_click_tracker_script_is_invisible_and_records_clicks(self) -> None:
        self.assertIn("document.addEventListener('click'", _CLICK_TRACKER_JS)
        self.assertIn("window.ph_record_click({", _CLICK_TRACKER_JS)
        self.assertNotIn("createElement('div')", _CLICK_TRACKER_JS)
        self.assertNotIn("attachShadow", _CLICK_TRACKER_JS)

    def test_extension_manifest_and_toolbar_are_present(self) -> None:
        repo_root = Path(__file__).resolve().parent
        extension_dir = repo_root / "extension"
        manifest_path = extension_dir / "manifest.json"
        content_js = (extension_dir / "content.js").read_text(encoding="utf-8")
        background_js = (extension_dir / "background.js").read_text(encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(
            manifest["permissions"],
            ["activeTab", "scripting", "contextMenus"],
        )
        self.assertNotIn("sidePanel", manifest.get("permissions", []))
        self.assertNotIn("side_panel", manifest)
        self.assertEqual(manifest["action"]["default_title"], "Parish Trainer")
        self.assertIn('"world": "MAIN"', manifest_path.read_text(encoding="utf-8"))
        self.assertIn("Mark Page as HTML", content_js)
        self.assertIn("Mark Current URL as File", content_js)
        self.assertIn("Crop Bulletin Image", content_js)
        self.assertIn("toggle_toolbar", content_js)
        self.assertIn("createToolbar", content_js)
        self.assertIn('type === "mark_html"', content_js)
        self.assertIn('type === "mark_file"', content_js)
        self.assertIn('type === "mark_image"', content_js)
        self.assertIn('type === "start_crop"', content_js)
        self.assertIn('window.ph_mark_crop', content_js)
        self.assertIn("chrome.contextMenus.create", background_js)
        self.assertIn('id: "mark-bulletin-image"', background_js)
        self.assertIn("toggle_toolbar", background_js)
        self.assertNotIn("chrome.sidePanel.open", background_js)

    def test_training_uses_persistent_context_with_extension_args(self) -> None:
        train_source = (Path(__file__).resolve().parent / "train.py").read_text(encoding="utf-8")
        self.assertIn("launch_persistent_context", train_source)
        self.assertIn("no_viewport=True", train_source)
        self.assertIn("--disable-extensions-except=", train_source)
        self.assertIn("--load-extension=", train_source)
        self.assertNotIn("--enable-features=SidePanelPinning", train_source)
        self.assertNotIn("--side-panel-options=always-show", train_source)
        self.assertIn("--start-maximized", train_source)
        self.assertIn("--window-size=1400,900", train_source)
        self.assertIn("browser.new_context(", train_source)
        self.assertIn("new_context(accept_downloads=True, no_viewport=True)", train_source)
        self.assertIn("tempfile.mkdtemp(", train_source)

    def test_train_auto_shows_toolbar_via_postmessage(self) -> None:
        train_source = (Path(__file__).resolve().parent / "train.py").read_text(encoding="utf-8")
        # Must post a window message to trigger the floating toolbar
        self.assertIn("window.postMessage", train_source)
        self.assertIn("toggle_toolbar", train_source)
        self.assertIn("from-isolated", train_source)
        # Must NOT try to open a Chrome side-panel (old incorrect approach)
        self.assertNotIn("chrome.sidePanel.open", train_source)
        # Must print a confirmation message
        self.assertIn("Parish Trainer toolbar ready", train_source)

    def test_content_js_auto_shows_toolbar_on_training_bindings(self) -> None:
        repo_root = Path(__file__).resolve().parent
        content_js = (repo_root / "extension" / "content.js").read_text(encoding="utf-8")
        # Auto-show helper must check for the Playwright training bindings
        self.assertIn("ph_mark_html", content_js)
        self.assertIn("ph_mark_download_url", content_js)
        self.assertIn("ph_mark_crop", content_js)
        self.assertIn("_tryAutoShowToolbar", content_js)
        # Must print the confirmation message when toolbar is auto-shown
        self.assertIn("Parish Trainer toolbar ready", content_js)

    def test_background_js_shows_toolbar_on_tab_complete(self) -> None:
        repo_root = Path(__file__).resolve().parent
        background_js = (repo_root / "extension" / "background.js").read_text(encoding="utf-8")
        # Must listen for tab updates to show toolbar after page navigation
        self.assertIn("tabs.onUpdated", background_js)
        self.assertIn("show_toolbar", background_js)

    def test_bulletin_page_limit_constant(self) -> None:
        self.assertEqual(_MAX_BULLETIN_PAGES, 4)

    def test_stitch_mega_pdf_skips_oversized_bulletins(self) -> None:
        """PDFs with more than _MAX_BULLETIN_PAGES pages must be excluded from the mega PDF."""
        try:
            import PyPDF2
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas as rl_canvas
        except ImportError:
            self.skipTest("reportlab or PyPDF2 not available")

        def _make_pdf(n_pages: int) -> bytes:
            buf = io.BytesIO()
            c = rl_canvas.Canvas(buf, pagesize=A4)
            for i in range(n_pages):
                c.drawString(72, 750, f"Page {i + 1} of {n_pages} — parish bulletin content here.")
                c.showPage()
            c.save()
            buf.seek(0)
            return buf.read()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current_dir = root / "current"
            bulletins_dir = root / "bulletins"
            current_dir.mkdir()
            bulletins_dir.mkdir()

            # Write a 2-page PDF (should be included) and a 5-page PDF (should be excluded)
            ok_pdf = current_dir / "ok_parish.pdf"
            ok_pdf.write_bytes(_make_pdf(2))
            big_pdf = current_dir / "big_parish.pdf"
            big_pdf.write_bytes(_make_pdf(5))

            from datetime import date
            from harvester.fetcher import FetchResult

            results = [
                FetchResult(
                    key="ok_parish",
                    display_name="OK Parish",
                    status="ok",
                    url="https://ok.example.org/",
                    file_path=ok_pdf,
                    file_type="pdf",
                ),
                FetchResult(
                    key="big_parish",
                    display_name="Big Parish",
                    status="ok",
                    url="https://big.example.org/",
                    file_path=big_pdf,
                    file_type="pdf",
                ),
            ]

            import contextlib
            import io as _io
            captured = _io.StringIO()
            with contextlib.redirect_stdout(captured):
                stitch_mega_pdf(
                    results,
                    current_dir=current_dir,
                    bulletins_dir=bulletins_dir,
                    target=date(2026, 4, 27),
                )

            output = captured.getvalue()
            # The oversized PDF should have been skipped with a warning
            self.assertIn("big_parish", output)
            self.assertIn("5 pages", output)

            # The mega PDF must exist and contain only pages from the 2-page bulletin
            mega = bulletins_dir / "all_bulletins_2026-04-27.pdf"
            self.assertTrue(mega.exists())
            reader = PyPDF2.PdfReader(str(mega))
            # Mega PDF should have pages from the ok bulletin only (≤ 4 pages)
            # plus possibly a summary page for big_parish which was excluded
            ok_page_count = 2  # both pages have real text
            self.assertLessEqual(len(reader.pages), ok_page_count + 2)


class UrlDateParsingAndScoringTests(unittest.TestCase):
    """Unit tests for URL date extraction and candidate ranking helpers."""

    def test_extract_date_iso_format(self) -> None:
        from harvester.utils import extract_date_from_string
        from datetime import date as _date
        self.assertEqual(extract_date_from_string("2026-04-26"), _date(2026, 4, 26))
        self.assertEqual(extract_date_from_string("2026-05-03"), _date(2026, 5, 3))
        self.assertEqual(extract_date_from_string("2025-12-28"), _date(2025, 12, 28))

    def test_extract_date_iso_nodash(self) -> None:
        from harvester.utils import extract_date_from_string
        from datetime import date as _date
        self.assertEqual(extract_date_from_string("20260426"), _date(2026, 4, 26))
        self.assertEqual(extract_date_from_string("20260503"), _date(2026, 5, 3))

    def test_extract_date_ddmmyyyy(self) -> None:
        from harvester.utils import extract_date_from_string
        from datetime import date as _date
        self.assertEqual(extract_date_from_string("26042026"), _date(2026, 4, 26))

    def test_extract_date_slug_ordinal(self) -> None:
        from harvester.utils import extract_date_from_slug
        from datetime import date as _date
        # Antrim-style: "26th-April-2026" and "3rd-May-2026"
        self.assertEqual(extract_date_from_slug("26th-April-2026"), _date(2026, 4, 26))
        self.assertEqual(extract_date_from_slug("3rd-May-2026"), _date(2026, 5, 3))
        self.assertEqual(extract_date_from_slug("1st-January-2026"), _date(2026, 1, 1))
        self.assertEqual(extract_date_from_slug("22nd-November-2026"), _date(2026, 11, 22))

    def test_extract_date_slug_plain_dash(self) -> None:
        from harvester.utils import extract_date_from_slug
        from datetime import date as _date
        self.assertEqual(extract_date_from_slug("26-april-2026"), _date(2026, 4, 26))
        self.assertEqual(extract_date_from_slug("3-may-2026"), _date(2026, 5, 3))

    def test_extract_date_slug_underscore(self) -> None:
        from harvester.utils import extract_date_from_slug
        from datetime import date as _date
        self.assertEqual(extract_date_from_slug("5_april_2026"), _date(2026, 4, 5))

    def test_extract_candidate_date_combines_parsers(self) -> None:
        """_extract_candidate_date delegates to both extract_date_from_string and slug."""
        from harvester.fetcher import _extract_candidate_date
        from datetime import date as _date
        # ISO in a decoded URL path
        self.assertEqual(
            _extract_candidate_date("https://example.com/uploads/2026-04-26/bulletin.pdf"),
            _date(2026, 4, 26),
        )
        # Ordinal slug in filename
        self.assertEqual(
            _extract_candidate_date("https://antrimparish.com/wp-content/uploads/2026/04/26th-April-2026.pdf"),
            _date(2026, 4, 26),
        )
        # No date → None
        self.assertIsNone(_extract_candidate_date("https://example.com/bulletin.pdf"))

    def test_candidate_score_prefers_target_week_over_older(self) -> None:
        """A URL matching the target date must score higher than an older URL."""
        from harvester.fetcher import _candidate_score
        from datetime import date as _date
        target = _date(2026, 5, 3)
        may3_url = "https://antrimparish.com/wp-content/uploads/2026/05/3rd-May-2026.pdf"
        apr26_url = "https://antrimparish.com/wp-content/uploads/2026/04/26th-April-2026.pdf"
        self.assertGreater(
            _candidate_score(target, may3_url, "", 0),
            _candidate_score(target, apr26_url, "", 1),
        )

    def test_candidate_score_current_week_beats_undated(self) -> None:
        """A URL with a date in the current week outranks a URL with no date."""
        from harvester.fetcher import _candidate_score
        from datetime import date as _date
        target = _date(2026, 4, 26)
        dated_url = "https://example.com/wp-content/uploads/2026/04/26th-April-2026.pdf"
        undated_url = "https://example.com/bulletin.pdf"
        self.assertGreater(
            _candidate_score(target, dated_url, "", 0),
            _candidate_score(target, undated_url, "", 1),
        )

    def test_candidate_score_stale_dates_ranked_below_undated(self) -> None:
        """A URL with a clearly stale date scores lower than an undated URL."""
        from harvester.fetcher import _candidate_score
        from datetime import date as _date
        target = _date(2026, 5, 3)
        stale_url = "https://example.com/wp-content/uploads/2026/01/1st-January-2026.pdf"
        undated_url = "https://example.com/bulletin.pdf"
        # not_known_stale component makes stale rank below undated
        self.assertGreater(
            _candidate_score(target, undated_url, "", 1),
            _candidate_score(target, stale_url, "", 0),
        )

    def test_candidate_score_may3_over_apr26_realistic_urls(self) -> None:
        """Realistic Antrim-style URL: May 3rd ranks above April 26th on 3rd May."""
        from harvester.fetcher import _candidate_score
        from datetime import date as _date
        target = _date(2026, 5, 3)
        urls = [
            "https://www.antrimparish.com/wp-content/uploads/2026/04/26th-April-2026.pdf",
            "https://www.antrimparish.com/wp-content/uploads/2026/05/3rd-May-2026.pdf",
        ]
        scores = [_candidate_score(target, u, "", i) for i, u in enumerate(urls)]
        self.assertGreater(scores[1], scores[0], "May 3rd URL must outscore April 26th URL")


class ToolbarImprovementsTests(unittest.TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parent
        self.content_js = (repo_root / "extension" / "content.js").read_text(encoding="utf-8")
        self.train_py = (repo_root / "train.py").read_text(encoding="utf-8")

    def test_toolbar_max_height_set(self):
        self.assertIn("maxHeight", self.content_js)
        self.assertIn("innerHeight", self.content_js)

    def test_toolbar_scroll_container(self):
        self.assertIn("ph-toolbar-scroll", self.content_js)
        self.assertIn("overflow-y: auto", self.content_js)

    def test_drag_clamp(self):
        # Dragging must clamp position to viewport
        self.assertIn("innerWidth - bw", self.content_js)
        self.assertIn("innerHeight - bh", self.content_js)

    def test_dock_button(self):
        self.assertIn("Snap to top-right corner", self.content_js)

    def test_chrome_interstitial_detection(self):
        self.assertIn("detectChromeInterstitial", self.content_js)
        self.assertIn("security-interstitial-content", self.content_js)
        self.assertIn("Click Advanced", self.content_js)

    def test_no_bulletin_button(self):
        self.assertIn("No bulletin here (skip)", self.content_js)
        self.assertIn("no_bulletin", self.content_js)

    def test_no_bulletin_train_handler(self):
        self.assertIn("no_bulletin", self.train_py)

    def test_pick_newest_recommended_label(self):
        self.assertIn("Recommended (newest)", self.content_js)

    def test_interstitial_result_list_scrollable(self):
        self.assertIn("ph-interstitial-banner", self.content_js)


if __name__ == "__main__":
    unittest.main()
