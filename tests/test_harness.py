from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.golden_eval import GoldenEvalCaseResult
from sciencemonitor.harness import render_harness_check_summary, run_harness_check
from sciencemonitor.real_case_eval import RealCaseEvalResult, RealCaseFixtureCheckResult


class HarnessCheckTest(unittest.TestCase):
    def test_harness_check_passes_when_all_gates_are_clean(self) -> None:
        with mock.patch(
            "sciencemonitor.harness.run_doctor",
            return_value={"warnings": []},
        ), mock.patch(
            "sciencemonitor.harness.run_golden_eval",
            return_value=[
                GoldenEvalCaseResult(
                    name="article_summary",
                    fixture_path=ROOT / "fixture.md",
                    actual_path=ROOT / "actual.md",
                    passed=True,
                    updated=False,
                    diff_path=None,
                    message="matched fixture",
                )
            ],
        ), mock.patch(
            "sciencemonitor.harness.run_real_case_fixture_eval",
            return_value=(
                [
                    RealCaseEvalResult(
                        case_id="case",
                        title="Example",
                        passed=True,
                        source_kind="local_pdf_full_text",
                        abstract_only=False,
                        summary_path=None,
                        report_path=None,
                        deep_read_path=None,
                        deep_read_pdf_path=None,
                        metadata_path=None,
                        message="ok",
                    )
                ],
                [
                    RealCaseFixtureCheckResult(
                        case_id="case",
                        artifact_name="summary",
                        fixture_path=ROOT / "fixture.md",
                        actual_path=ROOT / "actual.md",
                        passed=True,
                        updated=False,
                        diff_path=None,
                        message="matched fixture",
                    )
                ],
            ),
        ):
            report = run_harness_check(include_real_eval=True)
            self.assertTrue(report.passed)
            summary = render_harness_check_summary(report)
            self.assertIn("overall=ok", summary)
            self.assertIn("real_fixture_passed=1/1", summary)

    def test_harness_check_fails_on_missing_real_fixture(self) -> None:
        with mock.patch(
            "sciencemonitor.harness.run_doctor",
            return_value={"warnings": []},
        ), mock.patch(
            "sciencemonitor.harness.run_golden_eval",
            return_value=[
                GoldenEvalCaseResult(
                    name="article_summary",
                    fixture_path=ROOT / "fixture.md",
                    actual_path=ROOT / "actual.md",
                    passed=True,
                    updated=False,
                    diff_path=None,
                    message="matched fixture",
                )
            ],
        ), mock.patch(
            "sciencemonitor.harness.run_real_case_fixture_eval",
            return_value=(
                [
                    RealCaseEvalResult(
                        case_id="case",
                        title="Example",
                        passed=True,
                        source_kind="crossref_abstract",
                        abstract_only=True,
                        summary_path=None,
                        report_path=None,
                        deep_read_path=None,
                        deep_read_pdf_path=None,
                        metadata_path=None,
                        message="ok",
                    )
                ],
                [
                    RealCaseFixtureCheckResult(
                        case_id="case",
                        artifact_name="summary",
                        fixture_path=ROOT / "fixture.md",
                        actual_path=ROOT / "actual.md",
                        passed=False,
                        updated=False,
                        diff_path=None,
                        message="missing fixture",
                    )
                ],
            ),
        ):
            report = run_harness_check(include_real_eval=True)
            self.assertFalse(report.passed)
            summary = render_harness_check_summary(report)
            self.assertIn("overall=failed", summary)
            self.assertIn("missing fixture", summary)


if __name__ == "__main__":
    unittest.main()
