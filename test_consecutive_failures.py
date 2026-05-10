from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harvester.fetcher import FetchResult
from harvester.harvest_log import update_consecutive_failures


class ConsecutiveFailuresTests(unittest.TestCase):
    def test_updates_counts_for_success_and_failure_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            failures_path = Path(tmp) / "consecutive_failures.json"
            failures_path.write_text(
                json.dumps({"keep_failing": 1, "will_reset": 3, "untouched": 5}),
                encoding="utf-8",
            )

            results = [
                FetchResult(key="keep_failing", display_name="A", status="error"),
                FetchResult(key="will_reset", display_name="B", status="ok"),
                FetchResult(key="new_html_success", display_name="C", status="html_link"),
                FetchResult(key="new_failure", display_name="D", status="error"),
            ]

            counts = update_consecutive_failures(results, failures_path=failures_path)

            self.assertEqual(counts["keep_failing"], 2)
            self.assertEqual(counts["will_reset"], 0)
            self.assertEqual(counts["new_html_success"], 0)
            self.assertEqual(counts["new_failure"], 1)
            self.assertEqual(counts["untouched"], 5)

            on_disk = json.loads(failures_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk, counts)

    def test_missing_or_invalid_file_is_treated_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            failures_path = Path(tmp) / "consecutive_failures.json"

            counts = update_consecutive_failures(
                [FetchResult(key="first_failure", display_name="X", status="error")],
                failures_path=failures_path,
            )
            self.assertEqual(counts, {"first_failure": 1})

            failures_path.write_text("{not json", encoding="utf-8")
            counts = update_consecutive_failures(
                [FetchResult(key="first_failure", display_name="X", status="error")],
                failures_path=failures_path,
            )
            self.assertEqual(counts, {"first_failure": 1})


if __name__ == "__main__":
    unittest.main()
