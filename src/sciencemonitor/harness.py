from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .doctor import run_doctor
from .golden_eval import GoldenEvalCaseResult, render_golden_eval_summary, run_golden_eval
from .real_case_eval import (
    RealCaseEvalResult,
    RealCaseFixtureCheckResult,
    render_real_case_fixture_summary,
    run_real_case_fixture_eval,
)


@dataclass(frozen=True)
class HarnessCheckReport:
    doctor_report: dict
    golden_results: list[GoldenEvalCaseResult]
    real_eval_results: list[RealCaseEvalResult]
    real_fixture_results: list[RealCaseFixtureCheckResult]
    include_real_eval: bool

    @property
    def passed(self) -> bool:
        if self.doctor_report.get("warnings"):
            return False
        if any(not item.passed for item in self.golden_results):
            return False
        if not self.include_real_eval:
            return True
        if not self.real_eval_results:
            return False
        if any(not item.passed for item in self.real_eval_results):
            return False
        if any(not item.passed for item in self.real_fixture_results):
            return False
        return True


def run_harness_check(
    root: Path | None = None,
    *,
    include_real_eval: bool = False,
    real_case_ids: set[str] | None = None,
    limit: int = 0,
    include_report: bool = False,
    include_deep_read: bool = False,
    update_golden: bool = False,
    update_real_fixtures: bool = False,
) -> HarnessCheckReport:
    doctor_report = run_doctor(root, strict_runtime=False)
    golden_results = run_golden_eval(root, update=update_golden)
    real_eval_results: list[RealCaseEvalResult] = []
    real_fixture_results: list[RealCaseFixtureCheckResult] = []
    if include_real_eval:
        real_eval_results, real_fixture_results = run_real_case_fixture_eval(
            root=root,
            case_ids=real_case_ids,
            limit=limit,
            include_report=include_report,
            include_deep_read=include_deep_read,
            update=update_real_fixtures,
        )
    return HarnessCheckReport(
        doctor_report=doctor_report,
        golden_results=golden_results,
        real_eval_results=real_eval_results,
        real_fixture_results=real_fixture_results,
        include_real_eval=include_real_eval,
    )


def render_harness_check_summary(report: HarnessCheckReport) -> str:
    lines = [
        "Harness check summary:",
        f"- doctor={'ok' if not report.doctor_report.get('warnings') else 'warning'}",
        f"- golden_passed={sum(1 for item in report.golden_results if item.passed)}/{len(report.golden_results)}",
    ]
    if report.include_real_eval:
        lines.append(
            f"- real_eval_passed={sum(1 for item in report.real_eval_results if item.passed)}/{len(report.real_eval_results)}"
        )
        lines.append(
            f"- real_fixture_passed={sum(1 for item in report.real_fixture_results if item.passed)}/{len(report.real_fixture_results)}"
        )
    lines.append(f"- overall={'ok' if report.passed else 'failed'}")
    lines.append("")
    lines.append("Doctor:")
    if report.doctor_report.get("warnings"):
        for warning in report.doctor_report["warnings"]:
            lines.append(f"- {warning}")
    else:
        lines.append("- no warnings")
    lines.append("")
    lines.append(render_golden_eval_summary(report.golden_results))
    if report.include_real_eval:
        lines.append("")
        lines.append(render_real_case_fixture_summary(report.real_eval_results, report.real_fixture_results))
    return "\n".join(lines)
