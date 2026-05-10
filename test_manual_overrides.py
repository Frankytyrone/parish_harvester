from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from harvester.fetcher import ParishEntry, _fetch_entry, load_manual_overrides


class ManualOverrideTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_manual_overrides_filters_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parishes_dir = Path(tmp)
            (parishes_dir / "manual_overrides.json").write_text(
                json.dumps(
                    {
                        "good": {"url": "https://example.org/bulletin.pdf", "type": "download"},
                        "bad_url": {"url": "javascript:alert(1)", "type": "download"},
                        "bad_payload": "nope",
                        "unknown_type": {"url": "https://example.org/listing", "type": "mystery"},
                    }
                ),
                encoding="utf-8",
            )

            overrides = load_manual_overrides(parishes_dir)

            self.assertEqual(
                overrides,
                {
                    "good": {"url": "https://example.org/bulletin.pdf", "type": "download"},
                    "unknown_type": {"url": "https://example.org/listing", "type": "html"},
                },
            )

    async def test_fetch_entry_prefers_manual_pdf_override_before_other_paths(self) -> None:
        entry = ParishEntry(
            key="manualtest",
            display_name="Manual Test Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.org/old.pdf",
        )
        overrides = {
            "manualtest": {"url": "https://example.org/new.pdf", "type": "download"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            fake_download = AsyncMock(return_value=None)
            with (
                patch("harvester.fetcher._download_pdf", fake_download),
                patch("harvester.fetcher._is_real_pdf", return_value=True),
            ):
                result = await _fetch_entry(
                    entry,
                    out_dir,
                    date(2026, 5, 10),
                    browser=object(),  # download helper is mocked
                    manual_overrides=overrides,
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.url, "https://example.org/new.pdf")
        self.assertEqual(result.file_type, "pdf")
        fake_download.assert_awaited_once()

    async def test_fetch_entry_supports_manual_html_override(self) -> None:
        entry = ParishEntry(
            key="manualhtml",
            display_name="Manual HTML Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.org/old.pdf",
        )
        overrides = {
            "manualhtml": {"url": "https://example.org/bulletins", "type": "html"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            result = await _fetch_entry(
                entry,
                out_dir,
                date(2026, 5, 10),
                browser=object(),
                manual_overrides=overrides,
            )

        self.assertEqual(result.status, "html_link")
        self.assertEqual(result.url, "https://example.org/bulletins")
        self.assertEqual(result.file_type, "html_link")


if __name__ == "__main__":
    unittest.main()
