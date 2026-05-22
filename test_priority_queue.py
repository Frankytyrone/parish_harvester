from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from harvester.priority_queue import prioritise
from main import _prioritise_entries


class _Entry:
    def __init__(self, key: str) -> None:
        self.key = key


class PriorityQueueTests(unittest.TestCase):
    def test_prioritise_orders_highest_failures_then_alphabetical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            failures_path = Path(tmp) / "consecutive_failures.json"
            failures_path.write_text(
                json.dumps({"alpha": 2, "bravo": 2, "charlie": 5}),
                encoding="utf-8",
            )
            ordered = prioritise(
                ["zulu", "bravo", "charlie", "alpha", "yankee"],
                failures_path=failures_path,
            )
            self.assertEqual(["charlie", "alpha", "bravo", "zulu", "yankee"], ordered)

    def test_prioritise_keeps_unseen_parishes_in_original_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            failures_path = Path(tmp) / "consecutive_failures.json"
            failures_path.write_text(json.dumps({"known": 1}), encoding="utf-8")
            ordered = prioritise(["x", "known", "y", "z"], failures_path=failures_path)
            self.assertEqual(["known", "x", "y", "z"], ordered)

    def test_escape_hatch_env_var_disables_priority_reordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            failures_path = Path(tmp) / "consecutive_failures.json"
            failures_path.write_text(json.dumps({"alpha": 10, "bravo": 0}), encoding="utf-8")
            entries = [_Entry("bravo"), _Entry("alpha")]

            original = list(entries)
            os.environ["PARISH_HARVEST_NO_PRIORITY"] = "1"
            try:
                reordered = _prioritise_entries(entries, failures_path=failures_path)
            finally:
                os.environ.pop("PARISH_HARVEST_NO_PRIORITY", None)
            self.assertEqual(original, reordered)


if __name__ == "__main__":
    unittest.main()
