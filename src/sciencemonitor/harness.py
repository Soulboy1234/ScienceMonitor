from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import project_root
from .config_ui_functional_review import (
    ConfigUIFunctionalReviewReport,
    render_config_ui_functional_review_summary,
    run_config_ui_functional_review,
)
from .config_ui_review import ConfigUIReviewReport, render_config_ui_review_summary, run_config_ui_review
from .config_ui_visual_review import (
    ConfigUIVisualReviewReport,
    render_config_ui_visual_review_summary,
    run_config_ui_visual_review,
)
from .docs_review import DocsReviewReport, render_docs_review_summary, run_docs_review
from .doctor import run_doctor
from .exec_plan_review import ExecPlanCheckReport, render_exec_plan_check_summary, run_exec_plan_check
from .golden_eval import GoldenEvalCaseResult, render_golden_eval_summary, run_golden_eval
from .harness_audit import HarnessAuditReport, render_harness_audit_summary, run_harness_audit
from .real_case_outputs import render_real_case_fixture_summary
from .real_case_eval import (
    RealCaseEvalResult,
    RealCaseFixtureCheckResult,
    run_real_case_fixture_eval,
)
from .resource_checks import ResourceCheckReport, render_resource_check_summary, run_resource_precheck
from .tag_governance_review import (
    TagGovernanceReviewReport,
    render_tag_governance_review_summary,
    run_tag_governance_review,
)
from .tag_review import TagReviewAuditReport, render_tag_output_review_summary, run_tag_output_review
from .test_runner import CommandCheckResult, run_pytest_suite, skipped_command_result


VALID_HARNESS_PROFILES = ("smoke", "default", "output", "ui", "release")


@dataclass(frozen=True)
class HarnessProfileOptions:
    include_harness_audit: bool
    include_exec_plan: bool
    include_docs_review: bool
    include_tag_governance: bool
    include_tag_output_review: bool
    include_config_ui: bool
    include_golden: bool
    include_pytest: bool
    pytest_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class HarnessStaticReports:
    harness_audit: HarnessAuditReport
    exec_plan: ExecPlanCheckReport
    docs_review: DocsReviewReport
    tag_governance: TagGovernanceReviewReport
    tag_output: TagReviewAuditReport
    config_ui: ConfigUIReviewReport
    config_ui_functional: ConfigUIFunctionalReviewReport
    config_ui_visual: ConfigUIVisualReviewReport
    golden: list[GoldenEvalCaseResult]


@dataclass(frozen=True)
class HarnessCheckReport:
    doctor_report: dict
    harness_audit_report: HarnessAuditReport
    exec_plan_report: ExecPlanCheckReport
    docs_review_report: DocsReviewReport
    tag_governance_report: TagGovernanceReviewReport
    tag_output_review_report: TagReviewAuditReport
    config_ui_review_report: ConfigUIReviewReport
    config_ui_functional_review_report: ConfigUIFunctionalReviewReport
    config_ui_visual_review_report: ConfigUIVisualReviewReport
    golden_results: list[GoldenEvalCaseResult]
    real_eval_results: list[RealCaseEvalResult]
    real_fixture_results: list[RealCaseFixtureCheckResult]
    include_real_eval: bool = False
    profile: str = "default"
    resource_report: ResourceCheckReport | None = None
    pytest_result: CommandCheckResult | None = None
    include_harness_audit: bool = True
    include_exec_plan: bool = True
    include_docs_review: bool = True
    include_tag_governance: bool = True
    include_tag_output_review: bool = False
    include_config_ui: bool = False
    include_golden: bool = True
    include_pytest: bool = True

    @property
    def passed(self) -> bool:
        if self.doctor_report.get("warnings"):
            return False
        if self.resource_report is not None and not self.resource_report.passed:
            return False
        if self.include_pytest and (self.pytest_result is None or not self.pytest_result.passed):
            return False
        if self.include_harness_audit and not self.harness_audit_report.passed:
            return False
        if self.include_exec_plan and not self.exec_plan_report.passed:
            return False
        if self.include_docs_review and not self.docs_review_report.passed:
            return False
        if self.include_tag_governance and not self.tag_governance_report.passed:
            return False
        if self.include_tag_output_review and not self.tag_output_review_report.passed:
            return False
        if self.include_config_ui and not self.config_ui_review_report.passed:
            return False
        if self.include_config_ui and not self.config_ui_functional_review_report.passed:
            return False
        if self.include_config_ui and not self.config_ui_visual_review_report.passed:
            return False
        if self.include_golden and any(not item.passed for item in self.golden_results):
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
    profile: str = "default",
    include_real_eval: bool = False,
    real_case_ids: set[str] | None = None,
    limit: int = 0,
    include_report: bool = False,
    include_deep_read: bool = False,
    include_output_review: bool = False,
    include_pytest: bool | None = None,
    update_golden: bool = False,
    update_real_fixtures: bool = False,
) -> HarnessCheckReport:
    resolved_root = root or project_root()
    normalized_profile = _normalize_profile(profile)
    options = _resolve_profile_options(
        normalized_profile,
        include_output_review=include_output_review,
        include_pytest=include_pytest,
    )
    doctor_report = run_doctor(root, strict_runtime=False)
    resource_report, pytest_result = _run_pytest_for_profile(resolved_root, options)
    static_reports = _run_static_reports(root, resolved_root, options, update_golden=update_golden)
    real_eval_results, real_fixture_results = _run_real_fixture_checks(
        root=root,
        enabled=include_real_eval,
        real_case_ids=real_case_ids,
        limit=limit,
        include_report=include_report,
        include_deep_read=include_deep_read,
        update_real_fixtures=update_real_fixtures,
    )
    return HarnessCheckReport(
        doctor_report=doctor_report,
        harness_audit_report=static_reports.harness_audit,
        exec_plan_report=static_reports.exec_plan,
        docs_review_report=static_reports.docs_review,
        tag_governance_report=static_reports.tag_governance,
        tag_output_review_report=static_reports.tag_output,
        config_ui_review_report=static_reports.config_ui,
        config_ui_functional_review_report=static_reports.config_ui_functional,
        config_ui_visual_review_report=static_reports.config_ui_visual,
        golden_results=static_reports.golden,
        real_eval_results=real_eval_results,
        real_fixture_results=real_fixture_results,
        include_real_eval=include_real_eval,
        profile=normalized_profile,
        resource_report=resource_report,
        pytest_result=pytest_result,
        include_harness_audit=options.include_harness_audit,
        include_exec_plan=options.include_exec_plan,
        include_docs_review=options.include_docs_review,
        include_tag_governance=options.include_tag_governance,
        include_tag_output_review=options.include_tag_output_review,
        include_config_ui=options.include_config_ui,
        include_golden=options.include_golden,
        include_pytest=options.include_pytest,
    )


def render_harness_check_summary(report: HarnessCheckReport) -> str:
    lines = [
        "Harness check summary:",
        f"- profile={report.profile}",
        f"- doctor={'ok' if not report.doctor_report.get('warnings') else 'warning'}",
        f"- resources={_resource_status(report)}",
        f"- pytest={_command_status(report.pytest_result, report.include_pytest)}",
        f"- harness_audit={_gate_status(report.include_harness_audit, report.harness_audit_report.passed)}",
        f"- exec_plan={_gate_status(report.include_exec_plan, report.exec_plan_report.passed)}",
        f"- docs={_gate_status(report.include_docs_review, report.docs_review_report.passed)}",
        f"- tag_governance={_gate_status(report.include_tag_governance, report.tag_governance_report.passed)}",
        f"- tag_output_review={_tag_output_status(report)}",
        f"- config_ui={_gate_status(report.include_config_ui, report.config_ui_review_report.passed)}",
        f"- config_ui_functional={_gate_status(report.include_config_ui, report.config_ui_functional_review_report.passed)}",
        f"- config_ui_visual={_gate_status(report.include_config_ui, report.config_ui_visual_review_report.passed)}",
        f"- golden_passed={_golden_status(report)}",
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
    if report.resource_report is not None:
        lines.append("")
        lines.append(render_resource_check_summary(report.resource_report))
    if report.pytest_result is not None:
        lines.append("")
        lines.append(_render_pytest_summary(report.pytest_result))
    if report.include_harness_audit:
        lines.append("")
        lines.append(render_harness_audit_summary(report.harness_audit_report))
    if report.include_exec_plan:
        lines.append("")
        lines.append(render_exec_plan_check_summary(report.exec_plan_report))
    if report.include_docs_review:
        lines.append("")
        lines.append(render_docs_review_summary(report.docs_review_report))
    if report.include_tag_governance:
        lines.append("")
        lines.append(render_tag_governance_review_summary(report.tag_governance_report))
    if report.include_tag_output_review:
        lines.append("")
        lines.append(render_tag_output_review_summary(report.tag_output_review_report))
    if report.include_config_ui:
        lines.append("")
        lines.append(render_config_ui_review_summary(report.config_ui_review_report))
        lines.append("")
        lines.append(render_config_ui_functional_review_summary(report.config_ui_functional_review_report))
        lines.append("")
        lines.append(render_config_ui_visual_review_summary(report.config_ui_visual_review_report))
    if report.include_golden:
        lines.append("")
        lines.append(render_golden_eval_summary(report.golden_results))
    if report.include_real_eval:
        lines.append("")
        lines.append(render_real_case_fixture_summary(report.real_eval_results, report.real_fixture_results))
    return "\n".join(lines)


def _detect_changed_paths(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    paths: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        path_text = line[3:]
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        path_text = path_text.strip().strip('"')
        if path_text and path_text not in paths:
            paths.append(path_text)
    return paths


def _normalize_profile(profile: str) -> str:
    normalized = str(profile or "default").strip().lower()
    if normalized not in VALID_HARNESS_PROFILES:
        allowed = ", ".join(VALID_HARNESS_PROFILES)
        raise ValueError(f"未知 harness profile：{profile}。可选值：{allowed}")
    return normalized


def _resolve_profile_options(
    profile: str,
    *,
    include_output_review: bool,
    include_pytest: bool | None,
) -> HarnessProfileOptions:
    options = _profile_options(profile)
    if include_output_review:
        options = HarnessProfileOptions(
            include_harness_audit=options.include_harness_audit,
            include_exec_plan=options.include_exec_plan,
            include_docs_review=options.include_docs_review,
            include_tag_governance=True,
            include_tag_output_review=True,
            include_config_ui=options.include_config_ui,
            include_golden=options.include_golden,
            include_pytest=options.include_pytest,
            pytest_args=options.pytest_args,
        )
    if include_pytest is None:
        return options
    return HarnessProfileOptions(
        include_harness_audit=options.include_harness_audit,
        include_exec_plan=options.include_exec_plan,
        include_docs_review=options.include_docs_review,
        include_tag_governance=options.include_tag_governance,
        include_tag_output_review=options.include_tag_output_review,
        include_config_ui=options.include_config_ui,
        include_golden=options.include_golden,
        include_pytest=bool(include_pytest),
        pytest_args=options.pytest_args,
    )


def _run_pytest_for_profile(
    root: Path,
    options: HarnessProfileOptions,
) -> tuple[ResourceCheckReport | None, CommandCheckResult | None]:
    if not options.include_pytest:
        return None, None
    resource_report = run_resource_precheck(root)
    if resource_report.passed:
        return resource_report, _run_pytest_suite(root, options.pytest_args)
    return resource_report, skipped_command_result(
        "pytest",
        _pytest_command_preview(root, options.pytest_args),
        "resource precheck failed; pytest skipped to avoid low-signal cascade failures",
    )


def _run_static_reports(
    root: Path | None,
    resolved_root: Path,
    options: HarnessProfileOptions,
    *,
    update_golden: bool,
) -> HarnessStaticReports:
    return HarnessStaticReports(
        harness_audit=run_harness_audit(root, write_report=False)
        if options.include_harness_audit
        else _empty_harness_audit_report(),
        exec_plan=run_exec_plan_check(root) if options.include_exec_plan else _empty_exec_plan_report(resolved_root),
        docs_review=run_docs_review(root) if options.include_docs_review else DocsReviewReport(passed=True, issues=[]),
        tag_governance=run_tag_governance_review(root)
        if options.include_tag_governance
        else TagGovernanceReviewReport(passed=True, issues=[]),
        tag_output=run_tag_output_review(root)
        if options.include_tag_output_review
        else TagReviewAuditReport(passed=True, scanned_files=0, issues=[]),
        config_ui=run_config_ui_review(root) if options.include_config_ui else ConfigUIReviewReport(passed=True, issues=[]),
        config_ui_functional=run_config_ui_functional_review(root)
        if options.include_config_ui
        else ConfigUIFunctionalReviewReport(passed=True, issues=[]),
        config_ui_visual=run_config_ui_visual_review(root, changed_paths=_detect_changed_paths(resolved_root))
        if options.include_config_ui
        else ConfigUIVisualReviewReport(passed=True, issues=[], artifacts=[], reviewed_views=()),
        golden=run_golden_eval(root, update=update_golden) if options.include_golden else [],
    )


def _run_real_fixture_checks(
    *,
    root: Path | None,
    enabled: bool,
    real_case_ids: set[str] | None,
    limit: int,
    include_report: bool,
    include_deep_read: bool,
    update_real_fixtures: bool,
) -> tuple[list[RealCaseEvalResult], list[RealCaseFixtureCheckResult]]:
    if not enabled:
        return [], []
    return run_real_case_fixture_eval(
        root=root,
        case_ids=real_case_ids,
        limit=limit,
        include_report=include_report,
        include_deep_read=include_deep_read,
        update=update_real_fixtures,
    )


def _profile_options(profile: str) -> HarnessProfileOptions:
    if profile == "smoke":
        return HarnessProfileOptions(
            include_harness_audit=False,
            include_exec_plan=True,
            include_docs_review=True,
            include_tag_governance=False,
            include_tag_output_review=False,
            include_config_ui=False,
            include_golden=False,
            include_pytest=True,
            pytest_args=("tests/test_config.py", "tests/test_doctor.py", "tests/test_harness.py"),
        )
    if profile == "output":
        return HarnessProfileOptions(
            include_harness_audit=False,
            include_exec_plan=True,
            include_docs_review=True,
            include_tag_governance=True,
            include_tag_output_review=True,
            include_config_ui=False,
            include_golden=False,
            include_pytest=False,
        )
    if profile == "ui":
        return HarnessProfileOptions(
            include_harness_audit=False,
            include_exec_plan=True,
            include_docs_review=True,
            include_tag_governance=False,
            include_tag_output_review=False,
            include_config_ui=True,
            include_golden=False,
            include_pytest=True,
            pytest_args=(
                "tests/test_config_ui.py",
                "tests/test_config_ui_review.py",
                "tests/test_config_ui_functional_review.py",
                "tests/test_config_ui_visual_review.py",
            ),
        )
    if profile == "release":
        return HarnessProfileOptions(
            include_harness_audit=True,
            include_exec_plan=True,
            include_docs_review=True,
            include_tag_governance=True,
            include_tag_output_review=True,
            include_config_ui=True,
            include_golden=True,
            include_pytest=True,
        )
    return HarnessProfileOptions(
        include_harness_audit=True,
        include_exec_plan=True,
        include_docs_review=True,
        include_tag_governance=False,
        include_tag_output_review=False,
        include_config_ui=False,
        include_golden=True,
        include_pytest=True,
    )


def _empty_harness_audit_report() -> HarnessAuditReport:
    return HarnessAuditReport(checks={}, findings=[])


def _empty_exec_plan_report(root: Path) -> ExecPlanCheckReport:
    return ExecPlanCheckReport(
        passed=True,
        template_path=root / "config" / "templates" / "exec_plan_template.md",
        active_plans=[],
        completed_plans=[],
        active_statuses=[],
        issues=[],
    )


def _run_pytest_suite(root: Path, test_args: tuple[str, ...] = ()) -> CommandCheckResult:
    return run_pytest_suite(root, test_args)


def _pytest_command_preview(root: Path, test_args: tuple[str, ...] = ()) -> tuple[str, ...]:
    local_python = root / ".venv" / "bin" / "python"
    python_bin = str(local_python if local_python.exists() else "python")
    return (python_bin, "-m", "pytest", "-q", *test_args)


def _gate_status(included: bool, passed: bool) -> str:
    if not included:
        return "skipped"
    return "ok" if passed else "failed"


def _command_status(result: CommandCheckResult | None, included: bool) -> str:
    if not included:
        return "skipped"
    if result is None:
        return "missing"
    if result.skipped:
        return "skipped"
    return "ok" if result.passed else "failed"


def _resource_status(report: HarnessCheckReport) -> str:
    if report.resource_report is None:
        return "skipped"
    return "ok" if report.resource_report.passed else "failed"


def _tag_output_status(report: HarnessCheckReport) -> str:
    if not report.include_tag_output_review:
        return "skipped"
    if not report.tag_output_review_report.passed:
        return "failed"
    if report.tag_output_review_report.scanned_files == 0:
        return "empty"
    return "ok"


def _golden_status(report: HarnessCheckReport) -> str:
    if not report.include_golden:
        return "skipped"
    return f"{sum(1 for item in report.golden_results if item.passed)}/{len(report.golden_results)}"


def _render_pytest_summary(result: CommandCheckResult) -> str:
    status = "skipped" if result.skipped else ("ok" if result.passed else "failed")
    lines = [
        "Pytest summary:",
        f"- status={status}",
        f"- exit_code={result.exit_code}",
        f"- command={' '.join(result.command)}",
        "- output:",
    ]
    lines.append(result.output.strip() or "(no output)")
    return "\n".join(lines)
