from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harvester.fetcher import parse_evidence_file
from train import _PANEL_JS, _build_mark_step, _match_parish


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

    def test_panel_script_uses_shadow_dom_and_recreates_host(self) -> None:
        self.assertIn("document.getElementById('ph-training-host')", _PANEL_JS)
        self.assertIn("_existingHost.remove()", _PANEL_JS)
        self.assertNotIn("window.__phTrainingPanelInjected", _PANEL_JS)
        self.assertIn("attachShadow({ mode: 'open' })", _PANEL_JS)
        self.assertIn("top:12px!important", _PANEL_JS)
        self.assertIn("width:auto!important", _PANEL_JS)
        self.assertIn("height:auto!important", _PANEL_JS)
        self.assertIn("pointer-events:none!important", _PANEL_JS)
        self.assertIn("position: relative;", _PANEL_JS)
        self.assertIn("right: auto;", _PANEL_JS)
        self.assertIn("top: auto;", _PANEL_JS)
        self.assertIn("pointer-events: auto;", _PANEL_JS)
        self.assertNotIn("bottom:12px!important", _PANEL_JS)
        self.assertNotIn("bottom: 12px;", _PANEL_JS)
        self.assertIn("id=\"html-btn\"", _PANEL_JS)
        self.assertIn("id=\"file-btn\"", _PANEL_JS)


if __name__ == "__main__":
    unittest.main()
