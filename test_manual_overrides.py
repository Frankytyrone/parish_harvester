from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from harvester.fetcher import (
    FetchResult,
    ParishEntry,
    _build_auto_healed_steps,
    _fetch_entry,
    _write_auto_healed_recipe,
    load_manual_overrides,
)
from harvester.replay import RecipeReplayError


class ManualOverrideTests(unittest.IsolatedAsyncioTestCase):
    def test_build_auto_healed_steps_uses_image_action_for_image_urls(self) -> None:
        self.assertEqual(
            _build_auto_healed_steps("https://example.org/bulletin.jpg"),
            [{"action": "image", "url": "https://example.org/bulletin.jpg"}],
        )
        self.assertEqual(
            _build_auto_healed_steps("https://example.org/bulletin.pdf"),
            [
                {"action": "goto", "url": "https://example.org/bulletin.pdf"},
                {"action": "download"},
            ],
        )

    def test_write_auto_healed_recipe_updates_steps_and_metadata(self) -> None:
        entry = ParishEntry(
            key="healedparish",
            display_name="Healed Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.org/old.pdf",
            bulletin_page="https://example.org/bulletins",
        )

        with tempfile.TemporaryDirectory() as tmp:
            recipe_path = Path(tmp) / "recipes" / "healedparish.json"
            recipe_path.parent.mkdir(parents=True, exist_ok=True)
            recipe_path.write_text(
                json.dumps(
                    {
                        "parish_key": "healedparish",
                        "display_name": "Old Name",
                        "start_url": "https://example.org/original-start",
                        "custom": "keep-me",
                        "steps": [{"action": "goto", "url": "https://example.org/old.pdf"}],
                    }
                ),
                encoding="utf-8",
            )

            _write_auto_healed_recipe(
                entry,
                recipe_path,
                "https://example.org/new.pdf",
                date(2026, 5, 10),
            )

            saved = json.loads(recipe_path.read_text(encoding="utf-8"))

        self.assertEqual(saved["parish_key"], "healedparish")
        self.assertEqual(saved["display_name"], "Healed Parish")
        self.assertEqual(saved["recorded_date"], "2026-05-10")
        self.assertEqual(saved["start_url"], "https://example.org/original-start")
        self.assertEqual(saved["custom"], "keep-me")
        self.assertEqual(
            saved["steps"],
            [
                {"action": "goto", "url": "https://example.org/new.pdf"},
                {"action": "download"},
            ],
        )

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
                        "unknown_pdf": {"url": "https://example.org/current.pdf", "type": "mystery"},
                        "unknown_pdf_query": {"url": "https://example.org/current.pdf?download=1", "type": "mystery"},
                        "unknown_docx": {"url": "https://example.org/current.docx", "type": "mystery"},
                        "unknown_image": {"url": "https://example.org/current.jpg", "type": "mystery"},
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
                    "unknown_pdf": {"url": "https://example.org/current.pdf", "type": "download"},
                    "unknown_pdf_query": {"url": "https://example.org/current.pdf?download=1", "type": "download"},
                    "unknown_docx": {"url": "https://example.org/current.docx", "type": "docx"},
                    "unknown_image": {"url": "https://example.org/current.jpg", "type": "image"},
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

    async def test_fetch_entry_uses_mistral_fallback_after_recipe_failure(self) -> None:
        entry = ParishEntry(
            key="mistralrecipe",
            display_name="Mistral Recipe Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.org/old.pdf",
            bulletin_page="https://example.org/bulletins",
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            recipe_path = out_dir / "recipes" / "mistralrecipe.json"
            recipe_path.parent.mkdir(parents=True, exist_ok=True)
            recipe_path.write_text(json.dumps({"steps": [{"action": "goto", "url": "https://example.org"}]}), encoding="utf-8")

            healed = FetchResult(
                key=entry.key,
                display_name=entry.display_name,
                status="ok",
                url="https://example.org/new.pdf",
                file_path=out_dir / "mistralrecipe.pdf",
                file_type="pdf",
                is_fallback=True,
            )
            fallback = AsyncMock(return_value=healed)
            with (
                patch("harvester.fetcher.recipe_path_for", return_value=recipe_path),
                patch("harvester.fetcher.replay_recipe", AsyncMock(side_effect=RecipeReplayError("boom"))),
                patch("harvester.fetcher._try_mistral_auto_heal", fallback),
            ):
                result = await _fetch_entry(
                    entry,
                    out_dir,
                    date(2026, 5, 10),
                    browser=object(),
                    manual_overrides={},
                )

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.is_fallback)
        fallback.assert_awaited_once()

    async def test_fetch_entry_uses_mistral_fallback_after_prediction_failure(self) -> None:
        entry = ParishEntry(
            key="mistralpredict",
            display_name="Mistral Predict Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.org/current.pdf",
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            recipe_path = out_dir / "recipes" / "mistralpredict.json"
            healed = FetchResult(
                key=entry.key,
                display_name=entry.display_name,
                status="ok",
                url="https://example.org/fixed.pdf",
                file_path=out_dir / "mistralpredict.pdf",
                file_type="pdf",
                is_fallback=True,
            )
            fallback = AsyncMock(return_value=healed)
            with (
                patch("harvester.fetcher.recipe_path_for", return_value=recipe_path),
                patch("harvester.fetcher._download_pdf", AsyncMock(side_effect=RuntimeError("HTTP 404 for test"))),
                patch("harvester.fetcher.detect_pattern", AsyncMock(return_value=None)),
                patch("harvester.fetcher._scrape_seed_urls", return_value=[]),
                patch("harvester.fetcher._try_mistral_auto_heal", fallback),
            ):
                result = await _fetch_entry(
                    entry,
                    out_dir,
                    date(2026, 5, 10),
                    browser=object(),
                    manual_overrides={},
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.url, "https://example.org/fixed.pdf")
        self.assertTrue(result.is_fallback)
        fallback.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
