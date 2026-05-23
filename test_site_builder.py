from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import harvester.site_builder as site_builder


class SiteBuilderTests(unittest.TestCase):
    def test_run_writes_live_and_placeholder_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs = root / "docs"
            recipes = root / "parishes" / "recipes"
            bulletins = docs / "bulletins"
            report = root / "Bulletins" / "report.json"
            parishes_dir = root / "parishes"

            (recipes / "derry").mkdir(parents=True, exist_ok=True)
            (recipes / "derry" / "ardmoreparish.json").write_text(
                json.dumps(
                    {
                        "parish_key": "ardmoreparish",
                        "parish_name": "Ardmore",
                        "start_url": "https://example.com/ardmore",
                    }
                ),
                encoding="utf-8",
            )
            parishes_dir.mkdir(parents=True, exist_ok=True)
            (parishes_dir / "raphoe_diocese_bulletin_urls.txt").write_text(
                "\n".join(
                    [
                        "# --- Raphoe town ---",
                        "# key: drive-raphoe-town",
                        "# page: https://drive.google.com/file/d/abc/view",
                        "https://drive.usercontent.google.com/download?id=abc&export=download",
                    ]
                ),
                encoding="utf-8",
            )
            bulletins.mkdir(parents=True, exist_ok=True)
            (bulletins / "derry-2026-05-22.html").write_text(
                '<div id="ocr-panel">Line one</div><div class="note-box">note</div>',
                encoding="utf-8",
            )
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps({"downloaded": [{"parish": "ardmoreparish"}]}),
                encoding="utf-8",
            )

            old = (site_builder.RECIPES_DIR, site_builder.BULLETINS_DIR, site_builder.RELIABILITY_PATH, site_builder.REPO_ROOT)
            site_builder.RECIPES_DIR = recipes
            site_builder.BULLETINS_DIR = bulletins
            site_builder.RELIABILITY_PATH = docs / "reliability.json"
            site_builder.REPO_ROOT = root
            try:
                site_builder.run(report_path=report, docs_dir=docs)
            finally:
                site_builder.RECIPES_DIR, site_builder.BULLETINS_DIR, site_builder.RELIABILITY_PATH, site_builder.REPO_ROOT = old

            derry_page = (docs / "dioceses" / "derry" / "index.html").read_text(encoding="utf-8")
            raphoe_page = (docs / "dioceses" / "raphoe" / "index.html").read_text(encoding="utf-8")
            armagh_page = (docs / "dioceses" / "armagh" / "index.html").read_text(encoding="utf-8")

            self.assertIn("Download PDF", derry_page)
            self.assertIn("Line one", derry_page)
            self.assertIn("Raphoe town", raphoe_page)
            self.assertIn("We're still collecting bulletins for this diocese", armagh_page)


if __name__ == "__main__":
    unittest.main()
