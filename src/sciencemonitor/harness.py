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
from .tag_governance_review import (
    TagGovernanceReviewReport,
    render_tag_governance_review_summary,
    run_tag_governance_review,
)
from .tag_review import TagReviewAuditReport, render_tag_output_review_summary, run_tag_output_review


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
    include_real_eval: bool

    @property
    def passed(self) -> bool:
        if self.doctor_report.get("warnings"):
            return False
        if not self.harness_audit_report.passed:
            return False
        if not self.exec_plan_report.passed:
            return False
        if not self.docs_review_report.passed:
            return False
        if not self.tag_governance_report.passed:
            return False
        if not self.tag_output_review_report.passed:
            return False
        if not self.config_ui_review_report.passed:
            return False
        if not self.config_ui_functional_review_report.passed:
            return False
        if not self.config_ui_visual_review_report.passed:
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
    resolved_root = root or project_root()
    doctor_report = run_doctor(root, strict_runtime=False)
    harness_audit_report = run_harness_audit(root, write_report=False)
    exec_plan_report = run_exec_plan_check(root)
    docs_review_report = run_docs_review(root)
    tag_governance_report = run_tag_governance_review(root)
    tag_output_review_report = run_tag_output_review(root)
    config_ui_review_report = run_config_ui_review(root)
    config_ui_functional_review_report = run_config_ui_functional_review(root)
    config_ui_visual_review_report = run_config_ui_visual_review(root, changed_paths=_detect_changed_paths(resolved_root))
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
        harness_audit_report=harness_audit_report,
        exec_plan_report=exec_plan_report,
        docs_review_report=docs_review_report,
        tag_governance_report=tag_governance_report,
        tag_output_review_report=tag_output_review_report,
        config_ui_review_report=config_ui_review_report,
        config_ui_functional_review_report=config_ui_functional_review_report,
        config_ui_visual_review_report=config_ui_visual_review_report,
        golden_results=golden_results,
        real_eval_results=real_eval_results,
        real_fixture_results=real_fixture_results,
        include_real_eval=include_real_eval,
    )


def render_harness_check_summary(report: HarnessCheckReport) -> str:
    lines = [
        "Harness check summary:",
        f"- doctor={'ok' if not report.doctor_report.get('warnings') else 'warning'}",
        f"- harness_audit={'ok' if report.harness_audit_report.passed else 'failed'}",
        f"- exec_plan={'ok' if report.exec_plan_report.passed else 'failed'}",
        f"- docs={'ok' if report.docs_review_report.passed else 'failed'}",
        f"- tag_governance={'ok' if report.tag_governance_report.passed else 'failed'}",
        f"- tag_output_review={'ok' if report.tag_output_review_report.passed else 'failed'}",
        f"- config_ui={'ok' if report.config_ui_review_report.passed else 'failed'}",
        f"- config_ui_functional={'ok' if report.config_ui_functional_review_report.passed else 'failed'}",
        f"- config_ui_visual={'ok' if report.config_ui_visual_review_report.passed else 'failed'}",
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
    lines.append(render_harness_audit_summary(report.harness_audit_report))
    lines.append("")
    lines.append(render_exec_plan_check_summary(report.exec_plan_report))
    lines.append("")
    lines.append(render_docs_review_summary(report.docs_review_report))
    lines.append("")
    lines.append(render_tag_governance_review_summary(report.tag_governance_report))
    lines.append("")
    lines.append(render_tag_output_review_summary(report.tag_output_review_report))
    lines.append("")
    lines.append(render_config_ui_review_summary(report.config_ui_review_report))
    lines.append("")
    lines.append(render_config_ui_functional_review_summary(report.config_ui_functional_review_report))
    lines.append("")
    lines.append(render_config_ui_visual_review_summary(report.config_ui_visual_review_report))
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
