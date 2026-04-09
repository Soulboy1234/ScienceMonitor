from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.config_ui_functional_review import (
    ConfigUIFunctionalReviewReport,
    render_config_ui_functional_review_summary,
)


class ConfigUIFunctionalReviewSummaryTest(unittest.TestCase):
    def test_summary_renders_ok_state(self) -> None:
        report = ConfigUIFunctionalReviewReport(passed=True, issues=[])
        summary = render_config_ui_functional_review_summary(report)
        self.assertIn("overall=ok", summary)
        self.assertIn("violations: none", summary)


if __name__ == "__main__":
    unittest.main()
