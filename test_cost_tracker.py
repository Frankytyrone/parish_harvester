from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harvester.cost_tracker import (
    _pct_bar,
    _traffic_light,
    update_dashboard,
)


class TrafficLightTests(unittest.TestCase):
    def test_green_below_60(self) -> None:
        self.assertEqual(_traffic_light(0), "🟢")
        self.assertEqual(_traffic_light(59.9), "🟢")

    def test_amber_between_60_and_85(self) -> None:
        self.assertEqual(_traffic_light(60), "🟡")
        self.assertEqual(_traffic_light(84.9), "🟡")

    def test_red_above_85(self) -> None:
        self.assertEqual(_traffic_light(85), "🔴")
        self.assertEqual(_traffic_light(100), "🔴")


class PctBarTests(unittest.TestCase):
    def test_bar_length(self) -> None:
        bar = _pct_bar(50.0)
        # Should have 20 chars of fill + empty
        inner = bar.split("]")[0].lstrip("[")
        self.assertEqual(len(inner), 20)

    def test_bar_shows_percentage(self) -> None:
        bar = _pct_bar(72.5)
        self.assertIn("72.5%", bar)


class UpdateDashboardTests(unittest.TestCase):
    def test_dashboard_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            update_dashboard(root)
            out = root / "docs" / "COST_DASHBOARD.md"
            self.assertTrue(out.exists(), "COST_DASHBOARD.md should be written")
            content = out.read_text(encoding="utf-8")
            # Must contain all required sections
            self.assertIn("# 💷 Cost Dashboard", content)
            self.assertIn("What's free forever", content)
            self.assertIn("What could start costing money", content)
            self.assertIn("Repository storage", content)
            self.assertIn("What to do if a 🔴 appears", content)

    def test_dashboard_contains_traffic_lights(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            update_dashboard(root)
            content = (root / "docs" / "COST_DASHBOARD.md").read_text(encoding="utf-8")
            # At least one traffic light emoji should appear
            has_light = any(e in content for e in ("🟢", "🟡", "🔴"))
            self.assertTrue(has_light, "Dashboard should contain traffic-light emojis")

    def test_dashboard_degrades_gracefully_without_github_token(self) -> None:
        """Should not raise even when GITHUB_TOKEN is absent."""
        import os
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {}, clear=True):
                # Should not raise
                update_dashboard(root)
            out = root / "docs" / "COST_DASHBOARD.md"
            self.assertTrue(out.exists())

    def test_update_dashboard_never_raises(self) -> None:
        """update_dashboard must catch all exceptions internally."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("harvester.cost_tracker._write_dashboard", side_effect=RuntimeError("boom")):
                update_dashboard(root)  # must not raise

    def test_ai_state_section_present(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create a fake ai_router_state.json
            (root / "Bulletins").mkdir(parents=True)
            (root / "Bulletins" / "ai_router_state.json").write_text(
                json.dumps({"gemini": 5, "groq": 2}), encoding="utf-8"
            )
            update_dashboard(root)
            content = (root / "docs" / "COST_DASHBOARD.md").read_text(encoding="utf-8")
            self.assertIn("AI API calls", content)

    def test_size_section_red_near_cap(self) -> None:
        """When the repo is near the cap, a 🔴 should appear in storage section."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Fill with enough data to exceed 85% of 5 GB? That would be huge.
            # Instead: patch _repo_size_bytes to return a high value.
            from unittest.mock import patch

            from harvester.cost_tracker import GITHUB_REPO_CAP_GB
            large_bytes = int(GITHUB_REPO_CAP_GB * 1024**3 * 0.90)  # 90% of cap = 🔴
            with patch("harvester.cost_tracker._repo_size_bytes", return_value=large_bytes):
                update_dashboard(root)
            content = (root / "docs" / "COST_DASHBOARD.md").read_text(encoding="utf-8")
            self.assertIn("🔴", content)


if __name__ == "__main__":
    unittest.main()
