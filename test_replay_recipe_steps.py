from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from harvester.replay import _find_pdfemb_url, replay_recipe


class _FakePage:
    def __init__(self) -> None:
        self.url = "https://example.org/start"
        self._screenshot = None
        self.last_goto_timeout = None

    def on(self, _event: str, _callback) -> None:
        return None

    def locator(self, _selector: str):
        class _FakeLocator:
            @property
            def first(self):
                return self

            async def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
                return None

        return _FakeLocator()

    async def goto(self, url: str, timeout: int = 0, wait_until: str = "domcontentloaded") -> None:
        self.url = url
        self.last_goto_timeout = timeout

    async def wait_for_load_state(self, _state: str, timeout: int = 0) -> None:
        return None

    async def screenshot(self, full_page: bool = False) -> bytes:
        if self._screenshot is None:
            img = Image.new("RGB", (120, 120), color=(255, 255, 255))
            buf = BytesIO()
            img.save(buf, format="PNG")
            self._screenshot = buf.getvalue()
        return self._screenshot


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()
        self.closed = False

    async def new_page(self) -> _FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, context: _FakeContext) -> None:
        self.context = context

    async def new_context(self, accept_downloads: bool = True) -> _FakeContext:
        self.context.accept_downloads = accept_downloads
        return self.context


class ReplayRecipeStepTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_pdfemb_url_prefers_pdf_embedder_links(self) -> None:
        class _Page:
            url = "https://example.org/news/"

            async def eval_on_selector_all(self, selector: str, _script: str):
                self.selector = selector
                return ["/wp-content/uploads/2026/04/bulletin.pdf", "/other.html"]

        page = _Page()
        found = await _find_pdfemb_url(page)
        self.assertEqual(page.selector, "a.pdfemb-viewer[href]")
        self.assertEqual(found, "https://example.org/wp-content/uploads/2026/04/bulletin.pdf")

    async def test_replay_recipe_supports_html_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps({"steps": [{"action": "html", "url": "https://example.org/bulletin"}]}),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            out_path, file_type, source_url = await replay_recipe(recipe_path, dest, browser)

            self.assertEqual(out_path, dest)
            self.assertEqual(file_type, "html_link")
            self.assertEqual(source_url, "https://example.org/bulletin")
            self.assertTrue(context.accept_downloads)
            self.assertTrue(context.closed)

    async def test_replay_recipe_uses_recipe_timeout_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps(
                    {
                        "timeout": 30000,
                        "steps": [
                            {"action": "goto", "url": "https://example.org/news"},
                            {"action": "html", "url": "https://example.org/news"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            _out_path, _file_type, _source_url = await replay_recipe(recipe_path, dest, browser)

            self.assertEqual(context.page.last_goto_timeout, 30000)

    async def test_replay_recipe_supports_image_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps({"steps": [{"action": "image", "url": "https://example.org/bulletin.jpg"}]}),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            fake_download = AsyncMock(return_value=("https://example.org/bulletin.jpg", "image_to_pdf"))
            with patch("harvester.replay._download_image_url_as_pdf", fake_download):
                out_path, file_type, source_url = await replay_recipe(recipe_path, dest, browser)

            self.assertEqual(out_path, dest)
            self.assertEqual(file_type, "image_to_pdf")
            self.assertEqual(source_url, "https://example.org/bulletin.jpg")
            self.assertTrue(context.accept_downloads)
            fake_download.assert_awaited_once()
            self.assertTrue(context.closed)

    async def test_replay_recipe_supports_crop_screenshot_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_path = root / "recipe.json"
            recipe_path.write_text(
                json.dumps(
                    {
                        "steps": [
                            {
                                "action": "crop_screenshot",
                                "x": 10,
                                "y": 10,
                                "width": 50,
                                "height": 40,
                                "page_x": 10,
                                "page_y": 10,
                                "element_selector": "img",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dest = root / "bulletin.pdf"
            context = _FakeContext()
            browser = _FakeBrowser(context)

            out_path, file_type, source_url = await replay_recipe(recipe_path, dest, browser)

            self.assertEqual(out_path, dest)
            self.assertEqual(file_type, "crop_screenshot_to_pdf")
            self.assertEqual(source_url, "https://example.org/start")
            self.assertTrue(dest.exists())
            self.assertGreater(dest.stat().st_size, 0)
            self.assertTrue(context.closed)


if __name__ == "__main__":
    unittest.main()
