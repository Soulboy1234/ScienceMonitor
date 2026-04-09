from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.config_ui_visual_review import render_config_ui_visual_review_summary


class ConfigUIVisualReviewSummaryTest(unittest.TestCase):
    def test_summary_renders_ok_state(self) -> None:
        from sciencemonitor.config_ui_visual_review import ConfigUIVisualReviewReport

        report = ConfigUIVisualReviewReport(passed=True, issues=[], artifacts=[ROOT / "log" / "ui_visual_review" / "weekly.png"])
        summary = render_config_ui_visual_review_summary(report)
        self.assertIn("overall=ok", summary)
        self.assertIn("screenshots=1", summary)
        self.assertIn("violations: none", summary)


if __name__ == "__main__":
    unittest.main()
