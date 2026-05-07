from __future__ import annotations

import pathlib
import sys
import unittest
from contextlib import ExitStack
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.golden_eval import GoldenEvalCaseResult
from sciencemonitor.harness import render_harness_check_summary, run_harness_check
from sciencemonitor.harness_audit import HarnessAuditReport
from sciencemonitor.real_case_eval import RealCaseEvalResult, RealCaseFixtureCheckResult
from sciencemonitor.resource_checks import ResourceCheckReport
from sciencemonitor.test_runner import CommandCheckResult


def _resource_report(passed: bool = True) -> ResourceCheckReport:
    return ResourceCheckReport(
        passed=passed,
        min_free_bytes=1,
        test_tmpdir=ROOT / "tmp" / "pytest",
        checks={"project_root": passed, "test_tmpdir": passed},
        issues=[],
    )


def _pytest_result(passed: bool = True) -> CommandCheckResult:
    return CommandCheckResult(
        name="pytest",
        command=("python", "-m", "pytest", "-q"),
        passed=passed,
        exit_code=0 if passed else 1,
        output="ok" if passed else "failed",
    )


def _golden_results() -> list[GoldenEvalCaseResult]:
    return [
        GoldenEvalCaseResult(
            name="article_summary",
            fixture_path=ROOT / "fixture.md",
            actual_path=ROOT / "actual.md",
            passed=True,
            updated=False,
            diff_path=None,
            message="matched fixture",
        )
    ]


class HarnessCheckTest(unittest.TestCase):
    def test_default_profile_skips_output_review_and_runs_pytest(self) -> None:
        with _patched_clean_gates() as patches:
            report = run_harness_check(root=ROOT)
            self.assertTrue(report.passed)
            patches["tag_output"].assert_not_called()
            patches["pytest"].assert_called_once()
            summary = render_harness_check_summary(report)
            self.assertIn("profile=default", summary)
            self.assertIn("pytest=ok", summary)
            self.assertIn("tag_output_review=skipped", summary)

    def test_output_profile_reports_empty_output_review(self) -> None:
        with _patched_clean_gates() as patches:
            patches["tag_output"].return_value = mock.Mock(passed=True, issues=[], scanned_files=0)
            report = run_harness_check(root=ROOT, profile="output")
            self.assertTrue(report.passed)
            patches["pytest"].assert_not_called()
            patches["tag_output"].assert_called_once()
            self.assertIn("tag_output_review=empty", render_harness_check_summary(report))

    def test_ui_profile_passes_changed_paths_to_visual_review(self) -> None:
        with _patched_clean_gates() as patches:
            report = run_harness_check(root=ROOT, profile="ui")
            self.assertTrue(report.passed)
            patches["visual"].assert_called_once_with(ROOT, changed_paths=["src/sciencemonitor/token_monitor.py"])

    def test_include_output_review_enables_output_scan_on_default_profile(self) -> None:
        with _patched_clean_gates() as patches:
            patches["tag_output"].return_value = mock.Mock(passed=True, issues=[], scanned_files=3)
            report = run_harness_check(root=ROOT, include_output_review=True)
            self.assertTrue(report.passed)
            patches["tag_output"].assert_called_once()
            self.assertIn("tag_output_review=ok", render_harness_check_summary(report))

    def test_release_profile_fails_on_missing_real_fixture(self) -> None:
        with _patched_clean_gates() as patches:
            patches["real_eval"].return_value = (
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
            )
            report = run_harness_check(profile="release", include_real_eval=True)
            self.assertFalse(report.passed)
            summary = render_harness_check_summary(report)
            self.assertIn("overall=failed", summary)
            self.assertIn("missing fixture", summary)


class _patched_clean_gates:
    def __enter__(self):
        self.stack = ExitStack()
        patches = {
            "doctor": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_doctor", return_value={"warnings": []})),
            "resource": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_resource_precheck", return_value=_resource_report())),
            "pytest": self.stack.enter_context(mock.patch("sciencemonitor.harness._run_pytest_suite", return_value=_pytest_result())),
            "audit": self.stack.enter_context(
                mock.patch("sciencemonitor.harness.run_harness_audit", return_value=HarnessAuditReport(checks={"docs": True}, findings=[]))
            ),
            "exec_plan": self.stack.enter_context(
                mock.patch(
                    "sciencemonitor.harness.run_exec_plan_check",
                    return_value=mock.Mock(passed=True, template_path=ROOT / "template.md", active_plans=[], completed_plans=[], active_statuses=[], issues=[]),
                )
            ),
            "docs": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_docs_review", return_value=mock.Mock(passed=True, issues=[]))),
            "tag_governance": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_tag_governance_review", return_value=mock.Mock(passed=True, issues=[]))),
            "tag_output": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_tag_output_review", return_value=mock.Mock(passed=True, issues=[], scanned_files=0))),
            "config_ui": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_config_ui_review", return_value=mock.Mock(passed=True, issues=[]))),
            "functional": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_config_ui_functional_review", return_value=mock.Mock(passed=True, issues=[]))),
            "changed": self.stack.enter_context(mock.patch("sciencemonitor.harness._detect_changed_paths", return_value=["src/sciencemonitor/token_monitor.py"])),
            "visual": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_config_ui_visual_review", return_value=mock.Mock(passed=True, issues=[], artifacts=[], reviewed_views=("overview",)))),
            "golden": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_golden_eval", return_value=_golden_results())),
            "real_eval": self.stack.enter_context(mock.patch("sciencemonitor.harness.run_real_case_fixture_eval", return_value=([], []))),
        }
        return patches

    def __exit__(self, exc_type, exc, tb):
        return self.stack.__exit__(exc_type, exc, tb)


if __name__ == "__main__":
    unittest.main()
