from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
CONTENT_JS = REPO_ROOT / "extension" / "content.js"
SIDEPANEL_JS = REPO_ROOT / "extension" / "sidepanel.js"
POPUP_HTML = REPO_ROOT / "extension" / "popup.html"
POPUP_JS = REPO_ROOT / "extension" / "popup.js"
SIDEPANEL_HTML = REPO_ROOT / "extension" / "sidepanel.html"
AI_HELP_JS = REPO_ROOT / "extension" / "ai_help.js"
MANIFEST_JSON = REPO_ROOT / "extension" / "manifest.json"


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

    def test_gemini_settings_and_ai_help_hooks_exist(self) -> None:
        popup_html = POPUP_HTML.read_text(encoding="utf-8")
        popup_js = POPUP_JS.read_text(encoding="utf-8")
        sidepanel_html = SIDEPANEL_HTML.read_text(encoding="utf-8")
        sidepanel_js = SIDEPANEL_JS.read_text(encoding="utf-8")
        content_js = CONTENT_JS.read_text(encoding="utf-8")
        ai_help_js = AI_HELP_JS.read_text(encoding="utf-8")
        manifest_json = MANIFEST_JSON.read_text(encoding="utf-8")

        self.assertIn('id="gemini-api-key"', popup_html)
        self.assertIn("gemini_api_key", popup_js)
        self.assertIn('id="tab-ai"', sidepanel_html)
        self.assertIn("askGemini", sidepanel_js)
        self.assertIn("gatherPageContext", sidepanel_js)
        self.assertIn("<script src=\"ai_help.js\"></script>", sidepanel_html)
        self.assertIn("globalThis.PhAiHelp", ai_help_js)
        self.assertIn("gatherPageContextFromCurrentPage", ai_help_js)
        self.assertIn("saveHostMemory", ai_help_js)
        self.assertIn('ai_help.js",', manifest_json)
        self.assertIn("const _aiShared = () => globalThis.PhAiHelp || null;", content_js)
        self.assertIn("🤖 AI Help", content_js)
        self.assertIn("chrome.runtime.getManifest().version", content_js)

    def test_popup_retries_page_bridge_once_before_error(self) -> None:
        popup_js = POPUP_JS.read_text(encoding="utf-8")
        self.assertIn("setTimeout(resolve, 500)", popup_js)
        self.assertIn('result.reason === "receiver_unavailable"', popup_js)
        self.assertIn("click the toolbar icon again", popup_js)

    def test_content_js_avoids_literal_innerhtml_assignments(self) -> None:
        content_js = CONTENT_JS.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\.innerHTML\s*=", content_js))

    def test_ai_help_get_best_tab_skips_internal_urls_and_uses_normal_window_fallback(self) -> None:
        ai_help_js = AI_HELP_JS.read_text(encoding="utf-8")
        self.assertIn("async function getBestTab()", ai_help_js)
        self.assertIn('"chrome-extension://"', ai_help_js)
        self.assertIn("last_focused_normal_window", ai_help_js)
        self.assertIn('throw new Error("no_target_tab")', ai_help_js)

    def test_popup_diagnostics_dump_includes_extended_debug_lines(self) -> None:
        popup_html = POPUP_HTML.read_text(encoding="utf-8")
        popup_js = POPUP_JS.read_text(encoding="utf-8")
        self.assertIn("📋 Copy diagnostic info (paste to AI)", popup_html)
        self.assertIn("Browser user-agent:", popup_js)
        self.assertIn("Active tab URL:", popup_js)
        self.assertIn("Active tab is real http(s) page:", popup_js)
        self.assertIn("GitHub PAT present:", popup_js)
        self.assertIn("GitHub repo configured:", popup_js)
        self.assertIn("Mistral key present:", popup_js)
        self.assertIn("Gemini key present:", popup_js)
        self.assertIn("Last 10 ph_ai_memory_* keys:", popup_js)
        self.assertIn("Recent AI Help log entries (last 5):", popup_js)
        self.assertIn("Paste this whole block to your AI assistant.", popup_js)

    def test_content_scripts_use_isolated_world_only(self) -> None:
        import json
        manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
        content_scripts = manifest.get("content_scripts", [])
        # No entry must have "world": "MAIN"
        for entry in content_scripts:
            self.assertNotEqual(
                entry.get("world", "ISOLATED"),
                "MAIN",
                "A content_scripts entry still has world: MAIN",
            )
        # Exactly one entry must cover <all_urls>
        all_urls_entries = [e for e in content_scripts if "<all_urls>" in e.get("matches", [])]
        self.assertEqual(
            len(all_urls_entries),
            1,
            f"Expected exactly 1 content_scripts entry for <all_urls>, found {len(all_urls_entries)}",
        )

    def test_ph_ai_help_log_key_referenced_in_ai_help_and_popup(self) -> None:
        ai_help_js = AI_HELP_JS.read_text(encoding="utf-8")
        popup_js = POPUP_JS.read_text(encoding="utf-8")
        self.assertIn("ph_ai_help_log", ai_help_js)
        self.assertIn("ph_ai_help_log", popup_js)


if __name__ == "__main__":
    unittest.main()
