from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


class RaphoeAssetsTests(unittest.TestCase):
    def test_renamed_raphoe_evidence_file_is_structured(self) -> None:
        evidence_path = REPO_ROOT / "parishes" / "raphoe_diocese_bulletin_urls.txt"
        old_path = REPO_ROOT / "parishes" / "raphoe diocese urls.txt"

        text = evidence_path.read_text(encoding="utf-8")
        self.assertTrue(evidence_path.exists())
        self.assertFalse(old_path.exists())
        self.assertIn("# --- Ardara ---", text)
        self.assertIn("# --- Raphoe town ---", text)
        self.assertIn("drive.usercontent.google.com/download?id=1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa&export=download", text)
        self.assertEqual(text.count("milfordrathmullanparishes.ie/bulletins/"), 2)  # page + URL

    def test_raphoe_contacts_file_contains_placeholder_entries(self) -> None:
        contacts_path = REPO_ROOT / "parishes" / "raphoe_diocese_contacts.json"
        payload = json.loads(contacts_path.read_text(encoding="utf-8"))

        self.assertIn("ardara", payload)
        self.assertIn("drive-1jmslbrliw", payload)
        self.assertEqual(payload["dungloe"]["facebook"], "https://www.facebook.com/donalquinn1959")
        self.assertEqual(payload["steunanscathedral"]["display_name"], "St Eunan's Cathedral Letterkenny")


if __name__ == "__main__":
    unittest.main()
