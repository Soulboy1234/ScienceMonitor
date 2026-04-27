from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.config_ui_visual_review import infer_visual_review_targets, render_config_ui_visual_review_summary


class ConfigUIVisualReviewSummaryTest(unittest.TestCase):
    def test_summary_renders_ok_state(self) -> None:
        from sciencemonitor.config_ui_visual_review import ConfigUIVisualReviewReport

        report = ConfigUIVisualReviewReport(
            passed=True,
            issues=[],
            artifacts=[
                ROOT / "log" / "ui_visual_review" / "overview.png",
                ROOT / "log" / "ui_visual_review" / "weekly.png",
            ],
            reviewed_views=("overview", "weekly-report"),
        )
        summary = render_config_ui_visual_review_summary(report)
        self.assertIn("overall=ok", summary)
        self.assertIn("screenshots=2", summary)
        self.assertIn("reviewed_views=overview, weekly-report", summary)
        self.assertIn("violations: none", summary)

    def test_infer_targets_from_changed_paths(self) -> None:
        self.assertEqual(
            infer_visual_review_targets(["src/sciencemonitor/token_monitor.py"]),
            ("overview",),
        )
        self.assertEqual(
            infer_visual_review_targets(["src/sciencemonitor/config_ui_result_cards.py"]),
            ("weekly-report", "deep-read", "manual-llm"),
        )
        self.assertEqual(
            infer_visual_review_targets(["src/sciencemonitor/ui_assets/config_ui.css"]),
            ("overview", "weekly-report", "deep-read", "manual-llm", "settings"),
        )


if __name__ == "__main__":
    unittest.main()
