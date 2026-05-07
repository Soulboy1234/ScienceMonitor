from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.entropy import EntropyCheckReport
from sciencemonitor.config_ui_functional_review import ConfigUIFunctionalReviewReport
from sciencemonitor.config_ui_review import ConfigUIReviewReport
from sciencemonitor.config_ui_visual_review import ConfigUIVisualReviewReport
from sciencemonitor.docs_review import DocsReviewReport
from sciencemonitor.exec_plan_review import ExecPlanCheckReport
from sciencemonitor.golden_eval import GoldenEvalCaseResult
from sciencemonitor.harness_audit import HarnessAuditReport
from sciencemonitor.harness import HarnessCheckReport
from sciencemonitor.maintenance import SubprocessCheckResult, run_maintenance_cycle
from sciencemonitor.resource_checks import ResourceCheckReport
from sciencemonitor.tag_governance_review import TagGovernanceReviewReport
from sciencemonitor.tag_review import TagReviewAuditReport


def _entropy_report(passed: bool) -> EntropyCheckReport:
    return EntropyCheckReport(
        passed=passed,
        module_line_counts={"a.py": 1},
        function_lengths={"a.py::f": 1},
        import_cycles=[],
        unused_imports={},
        issues=[] if passed else [],
        budget_path=ROOT / "config" / "maintenance_budget.json",
    )


def _harness_report(passed: bool) -> HarnessCheckReport:
    return HarnessCheckReport(
        doctor_report={"warnings": []},
        harness_audit_report=HarnessAuditReport(checks={"docs": True}, findings=[]),
        exec_plan_report=ExecPlanCheckReport(
            passed=True,
            template_path=ROOT / "config" / "templates" / "exec_plan_template.md",
            active_plans=[],
            completed_plans=[],
            active_statuses=[],
            issues=[],
        ),
        docs_review_report=DocsReviewReport(passed=True, issues=[]),
        tag_governance_report=TagGovernanceReviewReport(passed=True, issues=[]),
        tag_output_review_report=TagReviewAuditReport(passed=True, scanned_files=0, issues=[]),
        config_ui_review_report=ConfigUIReviewReport(passed=True, issues=[]),
        config_ui_functional_review_report=ConfigUIFunctionalReviewReport(passed=True, issues=[]),
        config_ui_visual_review_report=ConfigUIVisualReviewReport(passed=True, issues=[], artifacts=[]),
        golden_results=[
            GoldenEvalCaseResult(
                name="article_summary",
                fixture_path=ROOT / "fixture.md",
                actual_path=ROOT / "actual.md",
                passed=passed,
                updated=False,
                diff_path=None,
                message="ok",
            )
        ],
        real_eval_results=[],
        real_fixture_results=[],
        include_real_eval=False,
        include_pytest=False,
    )


def _resource_report(passed: bool) -> ResourceCheckReport:
    return ResourceCheckReport(
        passed=passed,
        min_free_bytes=1,
        test_tmpdir=ROOT / "tmp" / "pytest",
        checks={"project_root": passed, "test_tmpdir": passed},
        issues=[],
    )


class MaintenanceCycleTest(unittest.TestCase):
    def test_maintenance_cycle_applies_safe_repairs_and_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            with mock.patch(
                "sciencemonitor.maintenance.run_doctor",
                side_effect=[{"warnings": ["PROJECT_CONFIG drift"]}, {"warnings": []}],
            ), mock.patch(
                "sciencemonitor.maintenance.run_entropy_check",
                side_effect=[_entropy_report(True), _entropy_report(True)],
            ), mock.patch(
                "sciencemonitor.maintenance.run_resource_precheck",
                return_value=_resource_report(True),
            ), mock.patch(
                "sciencemonitor.maintenance._run_pytest_suite",
                return_value=SubprocessCheckResult(
                    name="pytest",
                    command=("python", "-m", "pytest", "-q"),
                    passed=True,
                    exit_code=0,
                    output="all passed",
                ),
            ) as pytest_mock, mock.patch(
                "sciencemonitor.maintenance.run_harness_check",
                return_value=_harness_report(True),
            ) as harness_mock, mock.patch(
                "sciencemonitor.maintenance.sync_configs_from_project_markdown",
                return_value=[root / "config" / "runtime.json"],
            ):
                report = run_maintenance_cycle(root=root, auto_repair=True, write_report=False)
                self.assertTrue(report.passed)
                self.assertEqual(len(report.attempts), 1)
                self.assertTrue(any(action.applied for action in report.final_attempt.actions))
                pytest_mock.assert_called_once()
                harness_mock.assert_called_once()

    def test_maintenance_cycle_stops_without_safe_repair_when_failures_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            failing_entropy = EntropyCheckReport(
                passed=False,
                module_line_counts={"a.py": 100},
                function_lengths={"a.py::f": 90},
                import_cycles=[],
                unused_imports={},
                issues=[],
                budget_path=ROOT / "config" / "maintenance_budget.json",
            )
            with mock.patch(
                "sciencemonitor.maintenance.run_doctor",
                side_effect=[{"warnings": []}, {"warnings": []}],
            ), mock.patch(
                "sciencemonitor.maintenance.run_entropy_check",
                side_effect=[failing_entropy, failing_entropy],
            ), mock.patch(
                "sciencemonitor.maintenance.run_resource_precheck",
                return_value=_resource_report(True),
            ), mock.patch(
                "sciencemonitor.maintenance._run_pytest_suite",
                return_value=SubprocessCheckResult(
                    name="pytest",
                    command=("python", "-m", "pytest", "-q"),
                    passed=True,
                    exit_code=0,
                    output="all passed",
                ),
            ) as pytest_mock, mock.patch(
                "sciencemonitor.maintenance.run_harness_check",
                return_value=_harness_report(True),
            ) as harness_mock, mock.patch(
                "sciencemonitor.maintenance.sync_configs_from_project_markdown",
                return_value=[],
            ):
                report = run_maintenance_cycle(root=root, auto_repair=True, write_report=False)
                self.assertFalse(report.passed)
                self.assertEqual(len(report.attempts), 1)
                self.assertTrue(any("manual refactor" in action.detail for action in report.final_attempt.actions))
                self.assertTrue(report.final_attempt.pytest_result.skipped)
                self.assertIsNone(report.final_attempt.harness_report)
                pytest_mock.assert_not_called()
                harness_mock.assert_not_called()

    def test_maintenance_cycle_skips_tests_when_resource_precheck_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            with mock.patch(
                "sciencemonitor.maintenance.run_doctor",
                side_effect=[{"warnings": []}, {"warnings": []}],
            ), mock.patch(
                "sciencemonitor.maintenance.run_entropy_check",
                side_effect=[_entropy_report(True), _entropy_report(True)],
            ), mock.patch(
                "sciencemonitor.maintenance.run_resource_precheck",
                return_value=_resource_report(False),
            ), mock.patch("sciencemonitor.maintenance._run_pytest_suite") as pytest_mock, mock.patch(
                "sciencemonitor.maintenance.run_harness_check"
            ) as harness_mock:
                report = run_maintenance_cycle(root=root, auto_repair=False, write_report=False)
                self.assertFalse(report.passed)
                self.assertTrue(report.final_attempt.pytest_result.skipped)
                self.assertEqual(report.final_attempt.skipped_checks, ("pytest", "harness"))
                pytest_mock.assert_not_called()
                harness_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
