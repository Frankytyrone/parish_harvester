from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
CONTENT_JS = REPO_ROOT / "extension" / "content.js"
SIDEPANEL_JS = REPO_ROOT / "extension" / "sidepanel.js"


class ExtensionMessagingTests(unittest.TestCase):
    def test_mark_image_returns_explicit_failure_reasons(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        self.assertIn('if (!imageUrl)', content)
        self.assertIn('reason: "No image URL was provided."', content)
        self.assertIn('unavailableReason: "Image mark handler is unavailable on this page."', content)

    def test_recipe_steps_are_single_source_of_truth(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        self.assertIn("let recipeSteps = [];", content)
        self.assertIn("const _standaloneRecipeSteps = () =>", content)
        self.assertIn("if (_standaloneRecipeSteps().length === 0)", content)
        self.assertNotIn("let sessionSteps = []", content)
        self.assertNotIn("const standaloneSteps = []", content)

    def test_sidepanel_uses_reason_for_error_status(self) -> None:
        sidepanel = SIDEPANEL_JS.read_text(encoding="utf-8")
        self.assertIn('setStatus(`❌ ${result?.reason || _dispatchErrorText(result)}`, "err")', sidepanel)
        self.assertIn("statusEl.dataset.status", sidepanel)

    def test_mark_image_standalone_path_uses_single_recipe_step_append(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        marker = 'standaloneAddStep(\n              { action: "image", url: absUrl },'
        self.assertIn(marker, content)
        block_start = content.index(marker)
        block_end = content.index("showStatus(`✅ Image noted", block_start)
        self.assertNotIn("addSessionStep(\"mark_image\"", content[block_start:block_end])

    def test_toolbar_core_controls_and_advanced_fold_exist(self) -> None:
        content = CONTENT_JS.read_text(encoding="utf-8")
        for label in (
            "📄 Get a PDF (recommended)",
            "🔗 I need to click something first",
            "🖼️ Get an image (newsletter screenshot)",
            "📐 It's in a frame / viewer",
            "🔍 Help me identify this page",
            "📋 Recipe Preview",
            "⬆ Push Recipe to GitHub",
        ):
            self.assertIn(label, content)
        self.assertIn('document.createElement("details")', content)
        self.assertIn('advancedSummary.textContent = "▾ Advanced";', content)


if __name__ == "__main__":
    unittest.main()
