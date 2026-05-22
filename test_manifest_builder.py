from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

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

    def test_build_manifest_writes_reliability_tiers_and_rss_feed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Bulletins").mkdir(parents=True, exist_ok=True)
            (root / "mega_pdf").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "bulletins").mkdir(parents=True, exist_ok=True)
            (root / "parishes").mkdir(parents=True, exist_ok=True)
            (root / "recipes" / "learned").mkdir(parents=True, exist_ok=True)

            report_path = root / "Bulletins" / "report.json"
            output_path = root / "docs" / "manifest.json"
            (root / "mega_pdf" / "derry_mega_bulletin.pdf").write_bytes(b"%PDF-1.4")

            report_path.write_text(
                json.dumps(
                    {
                        "target_date": "2026-05-22",
                        "downloaded": [{"parish": "parish_green"}],
                        "html_links": [],
                        "failed": [{"parish": "parish_red"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "parishes" / "derry_diocese_contacts.json").write_text(
                json.dumps(
                    {
                        "parish_green": {},
                        "parish_amber": {},
                        "parish_red": {},
                        "parish_fallback": {},
                        "parish_grey": {},
                    }
                ),
                encoding="utf-8",
            )
            (root / "recipes" / "learned" / "parish_green.json").write_text(
                json.dumps({"success_rate": 0.8, "last_success": "2026-05-22T09:30:00Z"}),
                encoding="utf-8",
            )
            (root / "recipes" / "learned" / "parish_amber.json").write_text(
                json.dumps({"success_rate": 0.5}),
                encoding="utf-8",
            )
            (root / "recipes" / "learned" / "parish_red.json").write_text(
                json.dumps({"success_rate": 0.49}),
                encoding="utf-8",
            )
            (root / "parishes" / "consecutive_failures.json").write_text(
                json.dumps({"parish_fallback": 2}),
                encoding="utf-8",
            )

            build_manifest(
                report_path=report_path,
                dioceses_in_run=["derry_diocese"],
                output_path=output_path,
            )

            reliability = json.loads((root / "docs" / "reliability.json").read_text(encoding="utf-8"))
            parishes = reliability["parishes"]
            self.assertEqual("green", parishes["parish_green"]["tier"])
            self.assertEqual("2026-05-22", parishes["parish_green"]["last_success"])
            self.assertEqual("amber", parishes["parish_amber"]["tier"])
            self.assertEqual("red", parishes["parish_red"]["tier"])
            self.assertEqual("amber", parishes["parish_fallback"]["tier"])
            self.assertEqual("grey", parishes["parish_grey"]["tier"])
            self.assertIsNone(parishes["parish_grey"]["success_rate"])

            feed_path = root / "docs" / "feeds" / "derry_diocese.xml"
            xml_root = ET.fromstring(feed_path.read_text(encoding="utf-8"))
            self.assertEqual("rss", xml_root.tag)
            self.assertEqual("2.0", xml_root.attrib.get("version"))
            channel = xml_root.find("channel")
            self.assertIsNotNone(channel)
            if channel is None:
                self.fail("channel missing")
            self.assertEqual("Derry Diocese Bulletins", channel.findtext("title"))
            item = channel.find("item")
            self.assertIsNotNone(item)
            if item is None:
                self.fail("item missing")
            self.assertEqual(
                "Derry Diocese bulletin for 2026-05-22",
                item.findtext("title"),
            )
            self.assertEqual(
                "https://frankytyrone.github.io/parish_harvester/mega_pdf/derry_mega_bulletin.pdf",
                item.findtext("link"),
            )


if __name__ == "__main__":
    unittest.main()
