from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from reportlab.pdfgen import canvas

from harvester.fetcher import ParishEntry, _fetch_entry


class _FakePage:
    def __init__(self) -> None:
        self.url = "https://example.org/bulletins"

    async def goto(self, url: str, timeout: int = 0, wait_until: str = "domcontentloaded") -> None:
        self.url = url

    async def wait_for_load_state(self, _state: str, timeout: int = 0) -> None:
        return None

    async def wait_for_timeout(self, _delay_ms: int) -> None:
        return None

    async def eval_on_selector_all(self, _selector: str, _script: str):
        return []

    async def query_selector_all(self, _selector: str):
        return []


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()
        self.closed = False

    async def new_page(self) -> _FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self) -> None:
        self.context = _FakeContext()

    async def new_context(self):
        return self.context


def _write_large_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path))
    for page_num in range(1, 4):
        pdf.setFont("Helvetica", 12)
        for line in range(120):
            pdf.drawString(40, 800 - (line * 6), f"Rendered fallback page {page_num} line {line}")
        pdf.showPage()
    pdf.save()


class HtmlRenderFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_entry_uses_html_render_fallback_when_scrape_finds_no_pdf(self) -> None:
        entry = ParishEntry(
            key="htmlrender",
            display_name="HTML Render Parish",
            pattern="html_link",
            content_type="html_link",
            example_url="https://example.org/bulletins",
        )

        async def _fake_render(_page, dest_path: str) -> bool:
            _write_large_pdf(Path(dest_path))
            return True

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            missing_recipe = out_dir / "recipes" / "htmlrender.json"
            render_mock = AsyncMock(side_effect=_fake_render)
            with (
                patch("harvester.fetcher.recipe_path_for", return_value=missing_recipe),
                patch("harvester.fetcher._render_page_to_pdf", render_mock),
                patch("harvester.fetcher._scrape_seed_urls", return_value=["https://example.org/bulletins"]),
            ):
                result = await _fetch_entry(
                    entry,
                    out_dir,
                    date(2026, 5, 22),
                    browser=_FakeBrowser(),
                    manual_overrides={},
                )

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.file_type, "html_render")
            self.assertEqual(result.url, "https://example.org/bulletins")
            self.assertIsNotNone(result.file_path)
            self.assertTrue(result.file_path.exists())
            render_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
