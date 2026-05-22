"""test_h1_diocesan_split.py — tests for Bundle H1 diocesan file split.

Covers:
  - New per-diocese write paths are used on save.
  - Old flat-path files are still readable (backward-compat shim).
  - _index.json is created / updated atomically per diocese.
  - ocr/generate_bulletin_pages writes summaries and diffs under diocese subfolders.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harvester import learned_recipes


class LearnedRecipesDiocesePathTests(unittest.TestCase):
    """learned_recipes uses per-diocese subfolders on write."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.learned_dir = Path(self.tmp.name) / "recipes" / "learned"
        self._orig_dir = learned_recipes.LEARNED_DIR
        learned_recipes.LEARNED_DIR = self.learned_dir

    def tearDown(self) -> None:
        learned_recipes.LEARNED_DIR = self._orig_dir
        self.tmp.cleanup()

    def _base_payload(self, diocese: str = "derry") -> dict:
        return {
            "parish_key": "testparish",
            "diocese": diocese,
            "fingerprint": {
                "host": "example.com",
                "path_hint": "/bulletin",
                "dom_markers": [],
            },
            "last_success_date": "2026-05-22",
            "success_count": 1,
            "failure_count": 0,
            "success_rate": 1.0,
            "playbook": [{"action": "goto", "url": "https://example.com/bulletin"}],
            "last_strategy": "recipe",
        }

    # ── new paths ───────────────────────────────────────────────────────────

    def test_save_writes_to_per_diocese_subfolder(self) -> None:
        payload = self._base_payload("derry")
        learned_recipes.save("testparish", payload)
        expected = self.learned_dir / "derry" / "testparish.json"
        self.assertTrue(expected.exists(), f"Expected {expected} to exist")

    def test_save_with_unknown_diocese_writes_to_unknown_subfolder(self) -> None:
        payload = self._base_payload("")
        learned_recipes.save("testparish", payload)
        expected = self.learned_dir / "unknown" / "testparish.json"
        self.assertTrue(expected.exists(), f"Expected {expected} to exist")

    def test_load_reads_from_per_diocese_subfolder(self) -> None:
        payload = self._base_payload("derry")
        learned_recipes.save("testparish", payload)
        loaded = learned_recipes.load("testparish", diocese="derry")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual("testparish", loaded["parish_key"])
        self.assertEqual("derry", loaded["diocese"])

    # ── backward-compat shim ────────────────────────────────────────────────

    def test_load_falls_back_to_flat_path_when_new_path_missing(self) -> None:
        # Write a legacy flat file directly — no diocese subfolder.
        self.learned_dir.mkdir(parents=True, exist_ok=True)
        flat_path = self.learned_dir / "legacyparish.json"
        flat_path.write_text(
            json.dumps(
                {
                    "parish_key": "legacyparish",
                    "fingerprint": {"host": "legacy.com", "path_hint": "/", "dom_markers": []},
                    "last_success_date": "2026-01-01",
                    "success_count": 5,
                    "failure_count": 1,
                    "success_rate": 0.83,
                    "playbook": [],
                    "last_strategy": "old",
                }
            ),
            encoding="utf-8",
        )
        # No diocese sub-folder exists — should fall back to flat path.
        loaded = learned_recipes.load("legacyparish")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual("legacyparish", loaded["parish_key"])
        self.assertEqual(5, loaded["success_count"])

    def test_load_prefers_new_path_over_flat_path(self) -> None:
        # Write BOTH a flat legacy file and a new per-diocese file.
        self.learned_dir.mkdir(parents=True, exist_ok=True)
        flat_path = self.learned_dir / "ambiguous.json"
        flat_path.write_text(
            json.dumps(
                {
                    "parish_key": "ambiguous",
                    "diocese": "",
                    "fingerprint": {"host": "old.com", "path_hint": "/", "dom_markers": []},
                    "last_success_date": "2025-01-01",
                    "success_count": 1,
                    "failure_count": 0,
                    "success_rate": 1.0,
                    "playbook": [],
                    "last_strategy": "old",
                }
            ),
            encoding="utf-8",
        )
        # Also write the new path with different success_count.
        (self.learned_dir / "derry").mkdir(parents=True, exist_ok=True)
        new_path = self.learned_dir / "derry" / "ambiguous.json"
        new_path.write_text(
            json.dumps(
                {
                    "parish_key": "ambiguous",
                    "diocese": "derry",
                    "fingerprint": {"host": "new.com", "path_hint": "/", "dom_markers": []},
                    "last_success_date": "2026-05-22",
                    "success_count": 10,
                    "failure_count": 0,
                    "success_rate": 1.0,
                    "playbook": [],
                    "last_strategy": "new",
                }
            ),
            encoding="utf-8",
        )
        loaded = learned_recipes.load("ambiguous", diocese="derry")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(10, loaded["success_count"])  # from new path

    # ── _index.json ─────────────────────────────────────────────────────────

    def test_save_creates_index_json(self) -> None:
        payload = self._base_payload("derry")
        learned_recipes.save("testparish", payload)
        index_path = self.learned_dir / "derry" / "_index.json"
        self.assertTrue(index_path.exists(), "_index.json should be created")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual("derry", index["diocese"])
        self.assertIn("testparish", index["entries"])

    def test_save_updates_index_json_on_second_parish(self) -> None:
        learned_recipes.save("parish_a", {**self._base_payload("derry"), "parish_key": "parish_a"})
        learned_recipes.save("parish_b", {**self._base_payload("derry"), "parish_key": "parish_b"})
        index = json.loads(
            (self.learned_dir / "derry" / "_index.json").read_text(encoding="utf-8")
        )
        self.assertIn("parish_a", index["entries"])
        self.assertIn("parish_b", index["entries"])

    def test_index_json_is_not_loaded_as_parish(self) -> None:
        """_index.json must not be loaded as a learned recipe."""
        payload = self._base_payload("derry")
        learned_recipes.save("testparish", payload)
        # _index.json should not be loadable as a parish.
        result = learned_recipes.load("_index", diocese="derry")
        self.assertIsNone(result)

    # ── record_success/failure propagate diocese ─────────────────────────────

    def test_record_success_saves_to_diocese_subfolder(self) -> None:
        learned_recipes.record_success(
            "freshparish",
            "recipe",
            [{"action": "goto", "url": "https://example.com/bulletin"}],
            diocese="down_and_connor",
        )
        expected = self.learned_dir / "down_and_connor" / "freshparish.json"
        self.assertTrue(expected.exists())
        data = json.loads(expected.read_text(encoding="utf-8"))
        self.assertEqual("down_and_connor", data["diocese"])

    def test_record_failure_saves_to_diocese_subfolder(self) -> None:
        # First create a record via record_success so there's an existing entry.
        learned_recipes.record_success(
            "failparish", "recipe",
            [{"action": "goto", "url": "https://fail.com"}],
            diocese="derry",
        )
        learned_recipes.record_failure("failparish", diocese="derry")
        expected = self.learned_dir / "derry" / "failparish.json"
        self.assertTrue(expected.exists())
        data = json.loads(expected.read_text(encoding="utf-8"))
        self.assertEqual(1, data["failure_count"])


class BulletinsPathTests(unittest.TestCase):
    """generate_bulletin_pages writes per-diocese summaries and diffs."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self.tmp.name)

        # Patch SUMMARIES_DIR and DIFFS_DIR used by generate_bulletin_pages.
        import ocr.generate_bulletin_pages as gbp

        self._orig_summaries = gbp.SUMMARIES_DIR
        self._orig_diffs = gbp.DIFFS_DIR
        self._orig_bulletins_dir = gbp.BULLETINS_DIR

        gbp.SUMMARIES_DIR = self.tmp_root / "summaries"
        gbp.DIFFS_DIR = self.tmp_root / "diffs"
        # BULLETINS_DIR used by _find_previous_viewer_path — point at empty dir.
        gbp.BULLETINS_DIR = self.tmp_root / "bulletins"

        self.gbp = gbp

    def tearDown(self) -> None:
        self.gbp.SUMMARIES_DIR = self._orig_summaries
        self.gbp.DIFFS_DIR = self._orig_diffs
        self.gbp.BULLETINS_DIR = self._orig_bulletins_dir
        self.tmp.cleanup()

    def test_summaries_written_under_diocese_subfolder(self) -> None:
        os.environ["PARISH_AI_SUMMARIES_DISABLE"] = "1"
        try:
            self.gbp._write_parish_reader_outputs(
                diocese="derry",
                bulletin_date="2026-05-22",
                ocr_text="Some bulletin text.",
                parish_links=[("Blessed Sacrament", "https://example.com")],
            )
        finally:
            del os.environ["PARISH_AI_SUMMARIES_DISABLE"]

        summaries_dir = self.tmp_root / "summaries" / "derry"
        json_files = [f for f in summaries_dir.iterdir() if f.suffix == ".json" and f.name != "_index.json"]
        self.assertGreater(len(json_files), 0, "At least one summary JSON should be written")

    def test_diffs_written_under_diocese_subfolder(self) -> None:
        os.environ["PARISH_AI_SUMMARIES_DISABLE"] = "1"
        try:
            self.gbp._write_parish_reader_outputs(
                diocese="down_and_connor",
                bulletin_date="2026-05-22",
                ocr_text="Some bulletin text.",
                parish_links=[("St Mary's", "https://example.com")],
            )
        finally:
            del os.environ["PARISH_AI_SUMMARIES_DISABLE"]

        diffs_dir = self.tmp_root / "diffs" / "down_and_connor"
        json_files = [f for f in diffs_dir.iterdir() if f.suffix == ".json" and f.name != "_index.json"]
        self.assertGreater(len(json_files), 0, "At least one diff JSON should be written")

    def test_index_json_created_for_summaries(self) -> None:
        os.environ["PARISH_AI_SUMMARIES_DISABLE"] = "1"
        try:
            self.gbp._write_parish_reader_outputs(
                diocese="derry",
                bulletin_date="2026-05-22",
                ocr_text="Some bulletin text.",
                parish_links=[("Blessed Sacrament", "https://example.com")],
            )
        finally:
            del os.environ["PARISH_AI_SUMMARIES_DISABLE"]

        index_path = self.tmp_root / "summaries" / "derry" / "_index.json"
        self.assertTrue(index_path.exists(), "_index.json should be created for summaries")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual("derry", index["diocese"])
        self.assertIsInstance(index["entries"], dict)
        self.assertGreater(len(index["entries"]), 0)

    def test_index_json_created_for_diffs(self) -> None:
        os.environ["PARISH_AI_SUMMARIES_DISABLE"] = "1"
        try:
            self.gbp._write_parish_reader_outputs(
                diocese="derry",
                bulletin_date="2026-05-22",
                ocr_text="Some bulletin text.",
                parish_links=[("Blessed Sacrament", "https://example.com")],
            )
        finally:
            del os.environ["PARISH_AI_SUMMARIES_DISABLE"]

        index_path = self.tmp_root / "diffs" / "derry" / "_index.json"
        self.assertTrue(index_path.exists(), "_index.json should be created for diffs")


if __name__ == "__main__":
    unittest.main()
