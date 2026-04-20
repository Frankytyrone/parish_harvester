from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from harvester.replay import replay_recipe


class _FakePage:
    def __init__(self) -> None:
        self.url = "https://example.org/start"

    def on(self, _event: str, _callback) -> None:
        return None


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
        _ = accept_downloads
        return self.context


class ReplayRecipeStepTests(unittest.IsolatedAsyncioTestCase):
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
            self.assertTrue(context.closed)

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
            fake_download.assert_awaited_once()
            self.assertTrue(context.closed)


if __name__ == "__main__":
    unittest.main()
