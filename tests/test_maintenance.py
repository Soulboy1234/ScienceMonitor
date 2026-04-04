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
from sciencemonitor.golden_eval import GoldenEvalCaseResult
from sciencemonitor.harness import HarnessCheckReport
from sciencemonitor.maintenance import SubprocessCheckResult, run_maintenance_cycle


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
                "sciencemonitor.maintenance._run_pytest_suite",
                return_value=SubprocessCheckResult(
                    name="pytest",
                    command=("python", "-m", "pytest", "-q"),
                    passed=True,
                    exit_code=0,
                    output="all passed",
                ),
            ), mock.patch(
                "sciencemonitor.maintenance.run_harness_check",
                return_value=_harness_report(True),
            ), mock.patch(
                "sciencemonitor.maintenance.sync_configs_from_project_markdown",
                return_value=[root / "config" / "runtime.json"],
            ):
                report = run_maintenance_cycle(root=root, auto_repair=True, write_report=False)
                self.assertTrue(report.passed)
                self.assertEqual(len(report.attempts), 1)
                self.assertTrue(any(action.applied for action in report.final_attempt.actions))

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
                "sciencemonitor.maintenance._run_pytest_suite",
                return_value=SubprocessCheckResult(
                    name="pytest",
                    command=("python", "-m", "pytest", "-q"),
                    passed=True,
                    exit_code=0,
                    output="all passed",
                ),
            ), mock.patch(
                "sciencemonitor.maintenance.run_harness_check",
                return_value=_harness_report(True),
            ), mock.patch(
                "sciencemonitor.maintenance.sync_configs_from_project_markdown",
                return_value=[],
            ):
                report = run_maintenance_cycle(root=root, auto_repair=True, write_report=False)
                self.assertFalse(report.passed)
                self.assertEqual(len(report.attempts), 1)
                self.assertTrue(any("manual refactor" in action.detail for action in report.final_attempt.actions))


if __name__ == "__main__":
    unittest.main()
