from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from harvester.fetcher import FetchResult
from harvester.harvest_log import update_consecutive_failures, update_stale_bulletins


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
                FetchResult(key="new_skipped_success", display_name="E", status="skipped"),
                FetchResult(key="new_failure", display_name="D", status="error"),
            ]

            counts = update_consecutive_failures(results, failures_path=failures_path)

            self.assertEqual(counts["keep_failing"], 2)
            self.assertEqual(counts["will_reset"], 0)
            self.assertEqual(counts["new_html_success"], 0)
            self.assertEqual(counts["new_skipped_success"], 0)
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

    def test_update_stale_bulletins_flags_stale_and_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stale_path = Path(tmp) / "stale_bulletins.json"
            old_date = (date.today() - timedelta(days=10)).strftime("%d%m%y")
            fresh_date = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
            results = [
                FetchResult(
                    key="staleparish",
                    display_name="Stale Parish",
                    status="ok",
                    url=f"https://example.com/bulletin_{old_date}.pdf",
                ),
                FetchResult(
                    key="freshparish",
                    display_name="Fresh Parish",
                    status="ok",
                    url=f"https://example.com/bulletin-{fresh_date}.pdf",
                ),
                FetchResult(
                    key="unknownparish",
                    display_name="Unknown Parish",
                    status="ok",
                    url="https://example.com/latest.pdf",
                ),
                FetchResult(
                    key="errorparish",
                    display_name="Error Parish",
                    status="error",
                    url=f"https://example.com/bulletin_{old_date}.pdf",
                ),
            ]

            payload = update_stale_bulletins(results, bulletins_path=stale_path)

            self.assertEqual(len(payload["stale"]), 1)
            self.assertEqual(payload["stale"][0]["key"], "staleparish")
            self.assertEqual(payload["stale"][0]["reason"], "date_in_url")
            self.assertGreater(payload["stale"][0]["days_old"], 8)
            self.assertEqual(len(payload["unknown_date"]), 1)
            self.assertEqual(payload["unknown_date"][0]["key"], "unknownparish")
            self.assertEqual(payload["unknown_date"][0]["reason"], "no_date_in_url")

            on_disk = json.loads(stale_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk, payload)

    def test_update_stale_bulletins_supports_dd_mm_yyyy_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stale_path = Path(tmp) / "stale_bulletins.json"
            old_date = (date.today() - timedelta(days=11)).strftime("%d-%m-%Y")
            payload = update_stale_bulletins(
                [
                    FetchResult(
                        key="dashparish",
                        display_name="Dash Parish",
                        status="ok",
                        url=f"https://example.com/bulletin-{old_date}.pdf",
                    )
                ],
                bulletins_path=stale_path,
            )
            self.assertEqual(payload["stale"][0]["key"], "dashparish")
            self.assertEqual(payload["stale"][0]["reason"], "date_in_url")

    def test_update_stale_bulletins_uses_strictly_more_than_8_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stale_path = Path(tmp) / "stale_bulletins.json"
            boundary_date = (date.today() - timedelta(days=8)).strftime("%Y-%m-%d")
            payload = update_stale_bulletins(
                [
                    FetchResult(
                        key="boundaryparish",
                        display_name="Boundary Parish",
                        status="ok",
                        url=f"https://example.com/bulletin-{boundary_date}.pdf",
                    )
                ],
                bulletins_path=stale_path,
            )
            self.assertEqual(payload["stale"], [])
            self.assertEqual(payload["unknown_date"], [])


if __name__ == "__main__":
    unittest.main()
