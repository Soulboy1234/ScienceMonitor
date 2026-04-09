from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.config_ui_review import render_config_ui_review_summary, run_config_ui_review


class ConfigUIReviewTest(unittest.TestCase):
    def test_config_ui_review_passes(self) -> None:
        report = run_config_ui_review(ROOT)
        self.assertTrue(report.passed)
        summary = render_config_ui_review_summary(report)
        self.assertIn("overall=ok", summary)
        self.assertIn("violations: none", summary)

    def test_ui_css_contains_narrow_viewport_guards(self) -> None:
        css_text = (ROOT / "src" / "sciencemonitor" / "ui_assets" / "config_ui.css").read_text(encoding="utf-8")
        self.assertIn(".span-9 { grid-column: span 9; }", css_text)
        self.assertIn(".span-3 { grid-column: span 3; }", css_text)
        self.assertIn(".form-stack { display: flex; flex-direction: column; gap: 12px; }", css_text)
        self.assertIn(".weekly-report-grid", css_text)
        self.assertIn(".weekly-report-form-card", css_text)
        self.assertIn(".weekly-report-journals-card", css_text)
        self.assertIn("@media (max-width: 1100px)", css_text)

    def test_ui_js_scrolls_main_to_top_on_view_switch(self) -> None:
        js_text = (ROOT / "src" / "sciencemonitor" / "ui_assets" / "config_ui.js").read_text(encoding="utf-8")
        self.assertIn('const mainEl = document.querySelector(".main");', js_text)
        self.assertIn('mainEl.scrollTo({ top: 0, left: 0, behavior: "auto" });', js_text)


if __name__ == "__main__":
    unittest.main()
