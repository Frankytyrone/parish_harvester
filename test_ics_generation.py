from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

# The ICS generation lives in harvester/manifest_builder.py
# We test via the public function _write_ics_calendars (tested below)
# and integration via build_manifest.


# ---------------------------------------------------------------------------
# Import the helper we are testing (it will be added to manifest_builder)
# ---------------------------------------------------------------------------
from harvester.manifest_builder import _write_ics_calendars  # type: ignore[attr-defined]


def _make_events_file(directory: Path, parish_key: str, events: list[dict]) -> None:
    """Write a minimal events JSON file into *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": "2026-06-01T00:00:00Z",
        "parish_key": parish_key,
        "parish_name": f"Parish {parish_key}",
        "diocese": directory.name,
        "source_bulletin_date": "2026-06-01",
        "events": events,
        "ai_provider": "gemini",
        "error": None,
    }
    (directory / f"{parish_key}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


class IcsGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.root = Path(self._tmp)
        self.events_dir = self.root / "Bulletins" / "events"
        self.docs_dir = self.root / "docs"

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_and_read_ics(self, diocese_events: dict[str, list[dict]]) -> dict[str, str]:
        """Write events files, call _write_ics_calendars, return {filename: content}."""
        from datetime import datetime, timezone

        for diocese, parish_data in diocese_events.items():
            diocese_dir = self.events_dir / diocese
            for parish_key, events in parish_data.items():
                _make_events_file(diocese_dir, parish_key, events)

        now = datetime.now(timezone.utc)
        _write_ics_calendars(self.docs_dir, self.events_dir, now)

        result = {}
        cals_dir = self.docs_dir / "calendars"
        if cals_dir.exists():
            for f in cals_dir.iterdir():
                if f.suffix == ".ics":
                    result[f.name] = f.read_text(encoding="utf-8")
        return result

    def test_empty_events_produces_valid_vcalendar(self) -> None:
        files = self._write_and_read_ics({"derry": {"parish_a": []}})
        self.assertIn("derry.ics", files)
        self.assertIn("all.ics", files)
        content = files["derry.ics"]
        self.assertTrue(content.startswith("BEGIN:VCALENDAR"))
        self.assertIn("END:VCALENDAR", content)
        self.assertIn("VERSION:2.0", content)
        self.assertIn("PRODID", content)

    def test_vevent_created_for_valid_event(self) -> None:
        events = [
            {
                "title": "Sunday Mass",
                "date_iso": "2026-06-07",
                "time_24h_or_null": "10:00",
                "location_or_null": "St Mary's",
                "description": "Weekly Sunday Mass",
                "category": "mass",
            }
        ]
        files = self._write_and_read_ics({"derry": {"parish_a": events}})
        content = files["derry.ics"]
        self.assertIn("BEGIN:VEVENT", content)
        self.assertIn("END:VEVENT", content)
        self.assertIn("SUMMARY:Sunday Mass", content)
        self.assertIn("DTSTART", content)

    def test_uid_format(self) -> None:
        events = [
            {
                "title": "Bake Sale",
                "date_iso": "2026-06-14",
                "time_24h_or_null": None,
                "location_or_null": None,
                "description": "Annual bake sale",
                "category": "fundraiser",
            }
        ]
        files = self._write_and_read_ics({"derry": {"st_brigid": events}})
        content = files["derry.ics"]
        self.assertIn("@parish_harvester", content)
        # UID should contain parish_key and date
        self.assertIn("st_brigid", content)
        self.assertIn("2026-06-14", content)

    def test_uids_are_unique(self) -> None:
        events = [
            {
                "title": "Mass A",
                "date_iso": "2026-06-07",
                "time_24h_or_null": None,
                "location_or_null": None,
                "description": "",
                "category": "mass",
            },
            {
                "title": "Mass B",
                "date_iso": "2026-06-14",
                "time_24h_or_null": None,
                "location_or_null": None,
                "description": "",
                "category": "mass",
            },
        ]
        files = self._write_and_read_ics({"derry": {"parish_a": events}})
        content = files["derry.ics"]
        uid_lines = [line for line in content.splitlines() if line.startswith("UID:")]
        self.assertEqual(len(uid_lines), 2)
        self.assertEqual(len(set(uid_lines)), 2, "UIDs must be unique")

    def test_all_ics_aggregates_all_dioceses(self) -> None:
        files = self._write_and_read_ics(
            {
                "derry": {
                    "parish_a": [
                        {
                            "title": "Mass Derry",
                            "date_iso": "2026-06-07",
                            "time_24h_or_null": None,
                            "location_or_null": None,
                            "description": "",
                            "category": "mass",
                        }
                    ]
                },
                "down_and_connor": {
                    "parish_b": [
                        {
                            "title": "Mass D&C",
                            "date_iso": "2026-06-07",
                            "time_24h_or_null": None,
                            "location_or_null": None,
                            "description": "",
                            "category": "mass",
                        }
                    ]
                },
            }
        )
        self.assertIn("all.ics", files)
        all_content = files["all.ics"]
        self.assertIn("Mass Derry", all_content)
        self.assertIn("Mass D&C", all_content)

    def test_comma_and_newline_escaping(self) -> None:
        """RFC 5545 §3.3.11: commas and newlines must be escaped in text values."""
        events = [
            {
                "title": "Meeting, social",
                "date_iso": "2026-06-10",
                "time_24h_or_null": None,
                "location_or_null": "Hall, rear entrance",
                "description": "First line\nSecond line",
                "category": "meeting",
            }
        ]
        files = self._write_and_read_ics({"derry": {"p": events}})
        content = files["derry.ics"]
        # Commas should be escaped as \, in SUMMARY and LOCATION
        self.assertIn(r"SUMMARY:Meeting\, social", content)
        # Newlines in DESCRIPTION should be escaped as \n
        self.assertIn(r"\n", content)

    def test_dtstamp_present(self) -> None:
        events = [
            {
                "title": "Test Event",
                "date_iso": "2026-06-07",
                "time_24h_or_null": None,
                "location_or_null": None,
                "description": "",
                "category": "mass",
            }
        ]
        files = self._write_and_read_ics({"derry": {"p": events}})
        content = files["derry.ics"]
        self.assertIn("DTSTAMP:", content)

    def test_no_ics_written_when_no_events_dir(self) -> None:
        from datetime import datetime, timezone
        _write_ics_calendars(self.docs_dir, self.root / "nonexistent", datetime.now(timezone.utc))
        # Should not raise; calendars dir may or may not exist but no crash
        # all.ics should either not exist or be an empty calendar
        all_path = self.docs_dir / "calendars" / "all.ics"
        if all_path.exists():
            content = all_path.read_text(encoding="utf-8")
            self.assertIn("BEGIN:VCALENDAR", content)


if __name__ == "__main__":
    unittest.main()
