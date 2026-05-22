from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harvester.manifest_builder import build_manifest


class ManifestBuilderTests(unittest.TestCase):
    def test_build_manifest_includes_only_existing_mega_pdf_and_omits_missing_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Bulletins").mkdir(parents=True, exist_ok=True)
            (root / "mega_pdf").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "bulletins").mkdir(parents=True, exist_ok=True)
            (root / "parishes").mkdir(parents=True, exist_ok=True)

            report_path = root / "Bulletins" / "report.json"
            output_path = root / "docs" / "manifest.json"
            (root / "mega_pdf" / "derry_mega_bulletin.pdf").write_bytes(b"%PDF-1.4")

            report_path.write_text(
                json.dumps(
                    {
                        "target_date": "2026-05-22",
                        "downloaded": [
                            {"parish": "derry_a"},
                            {"parish": "derry_b"},
                            {"parish": "dac_a"},
                        ],
                        "html_links": [{"parish": "derry_a"}],
                        "failed": [{"parish": "derry_c"}, {"parish": "dac_b"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "parishes" / "derry_diocese_contacts.json").write_text(
                json.dumps({"derry_a": {}, "derry_b": {}, "derry_c": {}}),
                encoding="utf-8",
            )
            (root / "parishes" / "down_and_connor_contacts.json").write_text(
                json.dumps({"dac_a": {}, "dac_b": {}}),
                encoding="utf-8",
            )

            build_manifest(
                report_path=report_path,
                dioceses_in_run=["derry_diocese", "down_and_connor"],
                output_path=output_path,
            )

            manifest = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("2026-05-22", manifest["target_date"])
            self.assertIn("generated_at", manifest)
            self.assertIn("derry_diocese", manifest["dioceses"])
            self.assertNotIn("down_and_connor", manifest["dioceses"])

            derry = manifest["dioceses"]["derry_diocese"]
            self.assertEqual("Derry Diocese", derry["display_name"])
            self.assertEqual(2, derry["downloaded"])
            self.assertEqual(1, derry["html_links"])
            self.assertEqual(1, derry["failed"])
            self.assertEqual("66.7%", derry["success_rate"])
            self.assertNotIn("ocr_viewer", derry)


if __name__ == "__main__":
    unittest.main()
