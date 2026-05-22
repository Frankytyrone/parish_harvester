from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harvester import learned_recipes


class LearnedRecipesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.learned_dir = Path(self.tmp.name) / "recipes" / "learned"
        self._orig_dir = learned_recipes.LEARNED_DIR
        learned_recipes.LEARNED_DIR = self.learned_dir

    def tearDown(self) -> None:
        learned_recipes.LEARNED_DIR = self._orig_dir
        self.tmp.cleanup()

    def test_load_missing_returns_none(self) -> None:
        self.assertIsNone(learned_recipes.load("missing"))

    def test_save_and_load_roundtrip(self) -> None:
        payload = {
            "parish_key": "testparish",
            "fingerprint": {
                "host": "example.com",
                "path_hint": "/bulletin",
                "dom_markers": [".pdfemb-viewer", "iframe[src*='pdf']"],
            },
            "last_success_date": "2026-05-22",
            "success_count": 14,
            "failure_count": 4,
            "success_rate": 0.78,
            "playbook": [
                {"action": "goto", "url": "https://example.com/bulletin"},
                {"action": "click", "selector": ".next"},
            ],
            "last_strategy": "iframe_unwrap",
        }
        learned_recipes.save("testparish", payload)

        loaded = learned_recipes.load("testparish")
        self.assertIsNotNone(loaded)
        self.assertEqual("testparish", loaded["parish_key"])
        self.assertEqual("example.com", loaded["fingerprint"]["host"])
        self.assertEqual(14, loaded["success_count"])
        self.assertEqual(4, loaded["failure_count"])
        self.assertEqual(0.78, loaded["success_rate"])

    def test_record_success_updates_counts_rate_and_timestamp(self) -> None:
        learned_recipes.record_success(
            "freshparish",
            "iframe_unwrap",
            [
                {"action": "goto", "url": "https://example.com/bulletin"},
                {"action": "click", "selector": ".pdfemb-viewer"},
                {"action": "download", "url_pattern": "*.pdf"},
            ],
        )
        data = learned_recipes.load("freshparish")
        self.assertIsNotNone(data)
        self.assertEqual(1, data["success_count"])
        self.assertEqual(0, data["failure_count"])
        self.assertEqual(1.0, data["success_rate"])
        self.assertTrue(data["last_success_date"])
        self.assertEqual("iframe_unwrap", data["last_strategy"])
        self.assertEqual("example.com", data["fingerprint"]["host"])

    def test_record_failure_updates_failure_count_and_rate_only(self) -> None:
        learned_recipes.record_success(
            "failingparish",
            "recipe",
            [{"action": "goto", "url": "https://example.com/bulletin"}],
        )
        before = learned_recipes.load("failingparish")
        learned_recipes.record_failure("failingparish")
        after = learned_recipes.load("failingparish")
        self.assertIsNotNone(before)
        self.assertIsNotNone(after)
        self.assertEqual(before["success_count"], after["success_count"])
        self.assertEqual(before["last_success_date"], after["last_success_date"])
        self.assertEqual(before["last_strategy"], after["last_strategy"])
        self.assertEqual(before["playbook"], after["playbook"])
        self.assertEqual(before["failure_count"] + 1, after["failure_count"])
        self.assertEqual(0.5, after["success_rate"])

    def test_save_is_atomic_replace(self) -> None:
        payload = {
            "parish_key": "atomic",
            "diocese": "",
            "fingerprint": {"host": "", "path_hint": "", "dom_markers": []},
            "last_success_date": "",
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0.0,
            "playbook": [],
            "last_strategy": "",
        }
        learned_recipes.save("atomic", payload)
        # H1: no diocese → written to unknown/ subfolder.
        stored = self.learned_dir / "unknown" / "atomic.json"
        self.assertTrue(stored.exists())
        parsed = json.loads(stored.read_text(encoding="utf-8"))
        self.assertEqual("atomic", parsed["parish_key"])


if __name__ == "__main__":
    unittest.main()
