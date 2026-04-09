from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import logs_root, project_root


@dataclass(frozen=True)
class HarnessAuditFinding:
    severity: str
    area: str
    message: str
    recommendation: str


@dataclass(frozen=True)
class HarnessAuditReport:
    checks: dict[str, bool]
    findings: list[HarnessAuditFinding]
    report_path: Path | None = None

    @property
    def passed(self) -> bool:
        return not any(item.severity == "warning" for item in self.findings)

    @property
    def needs_optimization(self) -> bool:
        return bool(self.findings)


@dataclass(frozen=True)
class _HarnessAuditContext:
    readme_text: str
    agents_text: str
    overview_text: str
    release_text: str
    cli_text: str
    harness_text: str
    ci_text: str
    module_map_text: str


def harness_audit_log_root(root: Path | None = None) -> Path:
    return logs_root(root) / "harness_audit"


def run_harness_audit(root: Path | None = None, *, write_report: bool = False) -> HarnessAuditReport:
    project = root or project_root()
    checks: dict[str, bool] = {}
    findings: list[HarnessAuditFinding] = []
    context = _build_audit_context(project, checks, findings)
    _audit_public_entrypoints(context, checks, findings)
    _audit_overview_doc(context, checks, findings)
    _audit_execution_chain(context, checks, findings)
    _audit_release_and_code_map(context, checks, findings)

    report = HarnessAuditReport(checks=checks, findings=findings, report_path=None)
    if not write_report:
        return report
    report_path = write_harness_audit_report(project, report)
    return HarnessAuditReport(checks=checks, findings=findings, report_path=report_path)


def render_harness_audit_summary(report: HarnessAuditReport) -> str:
    lines = [
        "Harness audit summary:",
        f"- checks={sum(1 for ok in report.checks.values() if ok)}/{len(report.checks)}",
        f"- warnings={sum(1 for item in report.findings if item.severity == 'warning')}",
        f"- recommendations={sum(1 for item in report.findings if item.severity == 'recommendation')}",
        f"- needs_optimization={'yes' if report.needs_optimization else 'no'}",
        f"- overall={'ok' if report.passed else 'failed'}",
    ]
    if report.findings:
        lines.append("- findings:")
        for finding in report.findings:
            lines.append(
                f"  - [{finding.severity}] {finding.area}: {finding.message} 建议：{finding.recommendation}"
            )
    else:
        lines.append("- findings: none")
    if report.report_path:
        lines.append(f"- report={report.report_path}")
    return "\n".join(lines)


def write_harness_audit_report(root: Path | None, report: HarnessAuditReport) -> Path:
    project = root or project_root()
    log_root = harness_audit_log_root(project)
    log_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_root / f"{timestamp}_harness_audit.md"
    latest_path = log_root / "latest.md"
    content = _render_harness_audit_markdown(report)
    path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    return path


def _render_harness_audit_markdown(report: HarnessAuditReport) -> str:
    lines = [
        "# Harness Audit Report",
        "",
        render_harness_audit_summary(report),
        "",
        "## 检查项",
        "",
    ]
    for name, passed in sorted(report.checks.items()):
        lines.append(f"- {name}: {'ok' if passed else 'missing'}")
    if report.findings:
        lines.extend(["", "## Findings", ""])
        for finding in report.findings:
            lines.append(f"- [{finding.severity}] **{finding.area}**：{finding.message}")
            lines.append(f"  - 建议：{finding.recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def _build_audit_context(
    project: Path,
    checks: dict[str, bool],
    findings: list[HarnessAuditFinding],
) -> _HarnessAuditContext:
    overview_path = project / "docs" / "user_guides" / "harness_governance_overview.md"
    checks["overview_doc_exists"] = overview_path.exists()
    if not checks["overview_doc_exists"]:
        findings.append(
            HarnessAuditFinding(
                severity="warning",
                area="文档入口",
                message="缺少 harness 总览说明文档。",
                recommendation="恢复 docs/user_guides/harness_governance_overview.md，并把它作为公开入口。",
            )
        )
    return _HarnessAuditContext(
        readme_text=_read_text(project / "README.md"),
        agents_text=_read_text(project / "AGENTS.md"),
        overview_text=_read_text(overview_path),
        release_text=_read_text(project / "docs" / "user_guides" / "release_checklist.md"),
        cli_text=_read_text(project / "src" / "sciencemonitor" / "cli_support.py"),
        harness_text=_read_text(project / "src" / "sciencemonitor" / "harness.py"),
        ci_text=_read_text(project / ".github" / "workflows" / "ci.yml"),
        module_map_text=_read_text(project / "docs" / "user_guides" / "python_module_map.md"),
    )


def _audit_public_entrypoints(
    context: _HarnessAuditContext,
    checks: dict[str, bool],
    findings: list[HarnessAuditFinding],
) -> None:
    _record_check(
        checks,
        findings,
        name="readme_has_harness_commands",
        passed=all(
            item in context.readme_text
            for item in (
                "./scripts/run_science_monitor.sh harness-check",
                "./scripts/run_science_monitor.sh maintenance-check",
                "./scripts/run_science_monitor.sh harness-audit",
                "./scripts/run_science_monitor.sh harness-optimize",
            )
        ),
        severity="warning",
        area="README",
        message="README 没有完整暴露 harness 审计与优化命令。",
        recommendation="在 README 的常用命令和 harness 说明中补充 harness-audit 与 harness-optimize。",
    )
    _record_check(
        checks,
        findings,
        name="agents_has_harness_commands",
        passed=all(
            item in context.agents_text
            for item in (
                "./scripts/run_science_monitor.sh harness-check",
                "./scripts/run_science_monitor.sh maintenance-check",
                "./scripts/run_science_monitor.sh harness-audit",
                "./scripts/run_science_monitor.sh harness-optimize",
                "docs/user_guides/harness_governance_overview.md",
            )
        ),
        severity="warning",
        area="AGENTS",
        message="AGENTS 没有把 harness 审计与优化入口同步给 agent。",
        recommendation="在标准命令和导航中补充 harness-audit、harness-optimize 以及总览文档入口。",
    )


def _audit_overview_doc(
    context: _HarnessAuditContext,
    checks: dict[str, bool],
    findings: list[HarnessAuditFinding],
) -> None:
    _record_check(
        checks,
        findings,
        name="overview_mentions_audit_and_optimize",
        passed=all(item in context.overview_text for item in ("`harness-audit`", "`harness-optimize`")),
        severity="warning",
        area="Harness 总览",
        message="harness 总览没有解释 harness 自监督与优化闭环。",
        recommendation="在总览文档中增加 harness-audit 和 harness-optimize 的职责与使用方式。",
    )
    _record_check(
        checks,
        findings,
        name="overview_structure_stable",
        passed=_overview_structure_stable(context.overview_text),
        severity="warning",
        area="Harness 总览",
        message="harness 总览存在重复段落或旧编号，治理说明没有保持幂等。",
        recommendation="清理旧版 7/8 号小节和重复的治理关系行，并要求优化模块对总览文档保持幂等。",
    )


def _audit_execution_chain(
    context: _HarnessAuditContext,
    checks: dict[str, bool],
    findings: list[HarnessAuditFinding],
) -> None:
    _record_check(
        checks,
        findings,
        name="cli_exposes_audit_and_optimize",
        passed=all(
            item in context.cli_text
            for item in ('add_parser("harness-audit"', 'add_parser("harness-optimize"')
        ),
        severity="warning",
        area="命令入口",
        message="CLI 没有暴露 harness 自监督与优化命令。",
        recommendation="在 cli_support.py 中添加 harness-audit 和 harness-optimize 子命令。",
    )
    _record_check(
        checks,
        findings,
        name="harness_includes_audit",
        passed="run_harness_audit" in context.harness_text and "harness_audit" in context.harness_text,
        severity="warning",
        area="Harness Gate",
        message="harness-check 尚未纳入 harness 自监督结果。",
        recommendation="把 harness_audit 接入 harness-check，使治理链路也被自身审计覆盖。",
    )
    _record_check(
        checks,
        findings,
        name="ci_runs_harness_check",
        passed="./scripts/run_science_monitor.sh harness-check" in context.ci_text,
        severity="warning",
        area="CI",
        message="CI 没有运行 harness-check。",
        recommendation="保持 CI 至少执行 harness-check，避免治理链路与仓库主线脱节。",
    )


def _audit_release_and_code_map(
    context: _HarnessAuditContext,
    checks: dict[str, bool],
    findings: list[HarnessAuditFinding],
) -> None:
    _record_check(
        checks,
        findings,
        name="release_mentions_audit",
        passed="./scripts/run_science_monitor.sh harness-audit" in context.release_text,
        severity="recommendation",
        area="发版流程",
        message="发版清单尚未把 harness 自监督作为显式步骤。",
        recommendation="在 release_checklist 中加入 harness-audit，用于发版前检查治理链路自身是否有盲区。",
    )
    _record_check(
        checks,
        findings,
        name="module_map_mentions_audit_and_optimize",
        passed=all(item in context.module_map_text for item in ("harness_audit.py", "harness_optimize.py")),
        severity="recommendation",
        area="代码地图",
        message="Python 模块地图尚未纳入新的 harness 模块。",
        recommendation="在 python_module_map.md 中补充 harness_audit.py 和 harness_optimize.py 的职责说明。",
    )


def _overview_structure_stable(text: str) -> bool:
    return (
        text.count("### 2.5 `harness-audit`") == 1
        and text.count("### 2.6 `harness-optimize`") == 1
        and "### 7. `harness-audit`" not in text
        and "### 8. `harness-optimize`" not in text
        and text.count("- `harness-audit`：治理链路自身是否还有盲区") <= 1
        and text.count("- `harness-optimize`：按审计建议做低风险治理修补，再重新审计") <= 1
    )


def _record_check(
    checks: dict[str, bool],
    findings: list[HarnessAuditFinding],
    *,
    name: str,
    passed: bool,
    severity: str,
    area: str,
    message: str,
    recommendation: str,
) -> None:
    checks[name] = passed
    if passed:
        return
    findings.append(
        HarnessAuditFinding(
            severity=severity,
            area=area,
            message=message,
            recommendation=recommendation,
        )
    )


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
