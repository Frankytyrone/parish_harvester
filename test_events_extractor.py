from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from harvester.events_extractor import (
    _parse_events_json,
    _validate_event,
    extract_events,
    write_events_json,
)


class ValidateEventTests(unittest.TestCase):
    def test_valid_event_passes(self) -> None:
        item = {
            "title": "Sunday Mass",
            "date_iso": "2026-06-01",
            "time_24h_or_null": "10:00",
            "location_or_null": "Main Church",
            "description": "Parish Mass",
            "category": "mass",
        }
        result = _validate_event(item)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["title"], "Sunday Mass")
        self.assertEqual(result["date_iso"], "2026-06-01")
        self.assertEqual(result["category"], "mass")

    def test_invalid_date_rejected(self) -> None:
        item = {
            "title": "Meeting",
            "date_iso": "not-a-date",
            "description": "",
            "category": "meeting",
        }
        self.assertIsNone(_validate_event(item))

    def test_missing_date_rejected(self) -> None:
        item = {"title": "Fundraiser", "description": "", "category": "fundraiser"}
        self.assertIsNone(_validate_event(item))

    def test_empty_title_rejected(self) -> None:
        item = {"title": "", "date_iso": "2026-06-01", "description": "", "category": "mass"}
        self.assertIsNone(_validate_event(item))

    def test_unknown_category_coerced_to_other(self) -> None:
        item = {
            "title": "Bake Sale",
            "date_iso": "2026-06-15",
            "description": "Bake sale after mass",
            "category": "bazaar",
        }
        result = _validate_event(item)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["category"], "other")

    def test_null_optional_fields_preserved(self) -> None:
        item = {
            "title": "Prayer Group",
            "date_iso": "2026-07-04",
            "time_24h_or_null": None,
            "location_or_null": None,
            "description": "",
            "category": "meeting",
        }
        result = _validate_event(item)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsNone(result["time_24h_or_null"])
        self.assertIsNone(result["location_or_null"])


class ParseEventsJsonTests(unittest.TestCase):
    def test_clean_json_array(self) -> None:
        raw = '[{"title":"Mass","date_iso":"2026-06-01","description":"","category":"mass"}]'
        result = _parse_events_json(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Mass")

    def test_markdown_fenced(self) -> None:
        raw = "```json\n[{\"title\":\"Meeting\",\"date_iso\":\"2026-06-02\",\"description\":\"\",\"category\":\"meeting\"}]\n```"
        result = _parse_events_json(raw)
        self.assertEqual(len(result), 1)

    def test_empty_array(self) -> None:
        self.assertEqual(_parse_events_json("[]"), [])

    def test_no_json(self) -> None:
        self.assertEqual(_parse_events_json("Sorry, no events found."), [])

    def test_invalid_json(self) -> None:
        self.assertEqual(_parse_events_json("[{invalid}]"), [])


class ExtractEventsTests(unittest.TestCase):
    def _make_router(self, response: str | None, provider: str | None = "gemini") -> MagicMock:
        mock = MagicMock()
        mock.call_ai.return_value = (response, provider)
        return mock

    def test_ai_failure_returns_empty_list(self) -> None:
        router = self._make_router(None, None)
        result = extract_events("Some text", "Test Parish", "test_key", "derry", ai_router=router)
        self.assertEqual(result, [])

    def test_ai_returns_empty_array_json(self) -> None:
        router = self._make_router("[]")
        result = extract_events("No events", "Test Parish", "test_key", "derry", ai_router=router)
        self.assertEqual(result, [])

    def test_valid_events_returned(self) -> None:
        events_json = json.dumps([
            {
                "title": "Sunday Mass",
                "date_iso": "2026-06-01",
                "time_24h_or_null": "10:00",
                "location_or_null": "Church",
                "description": "Weekly mass",
                "category": "mass",
            }
        ])
        router = self._make_router(events_json)
        result = extract_events("bulletin text", "Parish A", "parish_a", "derry", ai_router=router)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Sunday Mass")
        self.assertEqual(result[0]["date_iso"], "2026-06-01")

    def test_invalid_dates_dropped(self) -> None:
        events_json = json.dumps([
            {"title": "Good Event", "date_iso": "2026-06-01", "description": "", "category": "mass"},
            {"title": "Bad Event", "date_iso": "tomorrow", "description": "", "category": "other"},
            {"title": "No Date", "description": "", "category": "meeting"},
        ])
        router = self._make_router(events_json)
        result = extract_events("text", "Parish", "parish_x", "derry", ai_router=router)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Good Event")

    def test_ai_exception_returns_empty_list(self) -> None:
        mock = MagicMock()
        mock.call_ai.side_effect = RuntimeError("Network error")
        result = extract_events("text", "Parish", "p", "derry", ai_router=mock)
        self.assertEqual(result, [])

    def test_disable_env_returns_empty(self) -> None:
        import os
        with patch.dict(os.environ, {"PARISH_EVENTS_DISABLE": "1"}):
            mock = MagicMock()
            result = extract_events("text", "Parish", "p", "derry", ai_router=mock)
        self.assertEqual(result, [])
        mock.call_ai.assert_not_called()

    def test_text_truncated_to_max_chars(self) -> None:
        from harvester.events_extractor import MAX_INPUT_CHARS

        captured = []
        def fake_call_ai(prompt: str):
            captured.append(prompt)
            return ("[]", "gemini")

        mock = MagicMock()
        mock.call_ai.side_effect = fake_call_ai
        long_text = "x" * (MAX_INPUT_CHARS + 5000)
        extract_events(long_text, "Parish", "p", "derry", ai_router=mock)
        self.assertTrue(len(captured[0]) <= MAX_INPUT_CHARS + 500)  # 500 = safe upper bound for prompt template overhead


class WriteEventsJsonTests(unittest.TestCase):
    def test_writes_correct_structure(self) -> None:
        import tempfile

        events = [
            {
                "title": "Mass",
                "date_iso": "2026-06-01",
                "time_24h_or_null": None,
                "location_or_null": None,
                "description": "Sunday mass",
                "category": "mass",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_events_json(
                events=events,
                parish_key="test_parish",
                parish_name="Test Parish",
                diocese="derry",
                bulletin_date="2026-06-01",
                ai_provider="gemini",
                error=None,
                repo_root=root,
            )
            out = root / "Bulletins" / "events" / "derry" / "test_parish.json"
            self.assertTrue(out.exists())
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["parish_key"], "test_parish")
            self.assertEqual(data["diocese"], "derry")
            self.assertEqual(len(data["events"]), 1)
            self.assertIsNone(data["error"])
            self.assertEqual(data["ai_provider"], "gemini")
            self.assertIn("generated_at", data)


if __name__ == "__main__":
    unittest.main()
