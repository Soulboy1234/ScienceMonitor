from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import logs_root, project_root, sync_configs_from_project_markdown
from .doctor import run_doctor
from .entropy import EntropyCheckReport, render_entropy_check_summary, run_entropy_check
from .harness import HarnessCheckReport, render_harness_check_summary, run_harness_check


@dataclass(frozen=True)
class MaintenanceAction:
    name: str
    applied: bool
    detail: str


@dataclass(frozen=True)
class SubprocessCheckResult:
    name: str
    command: tuple[str, ...]
    passed: bool
    exit_code: int
    output: str


@dataclass(frozen=True)
class MaintenanceAttempt:
    pass_index: int
    initial_doctor: dict
    initial_entropy: EntropyCheckReport
    actions: list[MaintenanceAction]
    pytest_result: SubprocessCheckResult
    harness_report: HarnessCheckReport
    final_doctor: dict
    final_entropy: EntropyCheckReport

    @property
    def passed(self) -> bool:
        return (
            not self.final_doctor.get("warnings")
            and self.pytest_result.passed
            and self.harness_report.passed
            and self.final_entropy.passed
        )


@dataclass(frozen=True)
class MaintenanceCycleReport:
    attempts: list[MaintenanceAttempt]
    report_path: Path | None

    @property
    def passed(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].passed

    @property
    def final_attempt(self) -> MaintenanceAttempt:
        return self.attempts[-1]


def maintenance_log_root(root: Path | None = None) -> Path:
    return logs_root(root) / "maintenance"


def run_maintenance_cycle(
    root: Path | None = None,
    *,
    auto_repair: bool = False,
    max_passes: int = 2,
    include_real_eval: bool = False,
    real_case_ids: set[str] | None = None,
    limit: int = 0,
    include_report: bool = False,
    include_deep_read: bool = False,
    write_report: bool = True,
) -> MaintenanceCycleReport:
    project = root or project_root()
    attempts: list[MaintenanceAttempt] = []

    for pass_index in range(1, max(1, max_passes) + 1):
        initial_doctor = run_doctor(project, strict_runtime=False)
        initial_entropy = run_entropy_check(project)
        actions = _apply_safe_maintenance_repairs(project, initial_doctor, initial_entropy) if auto_repair else []
        pytest_result = _run_pytest_suite(project)
        harness_report = run_harness_check(
            project,
            include_real_eval=include_real_eval,
            real_case_ids=real_case_ids,
            limit=limit,
            include_report=include_report,
            include_deep_read=include_deep_read,
        )
        final_doctor = run_doctor(project, strict_runtime=False)
        final_entropy = run_entropy_check(project)
        attempt = MaintenanceAttempt(
            pass_index=pass_index,
            initial_doctor=initial_doctor,
            initial_entropy=initial_entropy,
            actions=actions,
            pytest_result=pytest_result,
            harness_report=harness_report,
            final_doctor=final_doctor,
            final_entropy=final_entropy,
        )
        attempts.append(attempt)
        if attempt.passed:
            break
        if not auto_repair or not any(action.applied for action in actions):
            break

    report_path: Path | None = None
    if write_report:
        report_path = write_maintenance_report(project, MaintenanceCycleReport(attempts=attempts, report_path=None))
    return MaintenanceCycleReport(attempts=attempts, report_path=report_path)


def render_maintenance_summary(report: MaintenanceCycleReport) -> str:
    final_attempt = report.final_attempt
    lines = [
        "Maintenance check summary:",
        f"- passes={len(report.attempts)}",
        f"- overall={'ok' if report.passed else 'failed'}",
        f"- report={report.report_path or 'not written'}",
        "",
        "Reliability Reviewer:",
        f"- doctor={'ok' if not final_attempt.final_doctor.get('warnings') else 'warning'}",
        f"- pytest={'ok' if final_attempt.pytest_result.passed else 'failed'}",
        f"- harness={'ok' if final_attempt.harness_report.passed else 'failed'}",
        "",
        "Entropy Steward:",
        f"- entropy={'ok' if final_attempt.final_entropy.passed else 'failed'}",
    ]
    if final_attempt.actions:
        lines.append("")
        lines.append("Applied actions:")
        for action in final_attempt.actions:
            status = "applied" if action.applied else "skipped"
            lines.append(f"- {action.name}: {status} ({action.detail})")
    return "\n".join(lines)


def write_maintenance_report(root: Path | None, report: MaintenanceCycleReport) -> Path:
    project = root or project_root()
    log_root = maintenance_log_root(project)
    log_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = log_root / f"{timestamp}_maintenance_report.md"
    latest_path = log_root / "latest.md"
    content = _render_maintenance_markdown(report)
    path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    return path


def _render_maintenance_markdown(report: MaintenanceCycleReport) -> str:
    lines = [
        "# Maintenance Report",
        "",
        render_maintenance_summary(report),
    ]
    for attempt in report.attempts:
        lines.extend(
            [
                "",
                f"## Pass {attempt.pass_index}",
                "",
                "### Reliability Reviewer",
                "",
                f"- 初始 doctor 告警数：{len(attempt.initial_doctor.get('warnings', []))}",
                f"- pytest：{'通过' if attempt.pytest_result.passed else '失败'}",
                f"- harness-check：{'通过' if attempt.harness_report.passed else '失败'}",
                "",
                "### Entropy Steward",
                "",
                f"- 初始熵检查：{'通过' if attempt.initial_entropy.passed else '失败'}",
                f"- 最终熵检查：{'通过' if attempt.final_entropy.passed else '失败'}",
            ]
        )
        if attempt.actions:
            lines.extend(["", "### Applied Actions", ""])
            for action in attempt.actions:
                status = "applied" if action.applied else "skipped"
                lines.append(f"- {action.name}: {status} ({action.detail})")
        lines.extend(
            [
                "",
                "### Pytest Output",
                "",
                "```text",
                attempt.pytest_result.output.strip(),
                "```",
                "",
                "### Harness Output",
                "",
                "```text",
                render_harness_check_summary(attempt.harness_report).strip(),
                "```",
                "",
                "### Final Entropy Output",
                "",
                "```text",
                render_entropy_check_summary(attempt.final_entropy).strip(),
                "```",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _apply_safe_maintenance_repairs(
    root: Path,
    doctor_report: dict,
    entropy_report: EntropyCheckReport,
) -> list[MaintenanceAction]:
    actions: list[MaintenanceAction] = []
    sync_issues = [
        warning
        for warning in doctor_report.get("warnings", [])
        if "同步段" in warning or "research_preferences.json 与 PROJECT_CONFIG.md" in warning or "PROJECT_CONFIG" in warning
    ]
    updated_paths = sync_configs_from_project_markdown(root)
    actions.append(
        MaintenanceAction(
            name="sync_project_config",
            applied=bool(updated_paths),
            detail=", ".join(str(path.relative_to(root)) for path in updated_paths) if updated_paths else "no config drift to sync",
        )
    )
    if sync_issues and not updated_paths:
        actions.append(
            MaintenanceAction(
                name="sync_project_config_followup",
                applied=False,
                detail="doctor reported config drift but no files changed; requires manual inspection",
            )
        )
    if not entropy_report.passed:
        actions.append(
            MaintenanceAction(
                name="entropy_budget_guard",
                applied=False,
                detail="entropy violations require manual refactor; no safe automatic code rewrite available",
            )
        )
    return actions


def _run_pytest_suite(root: Path) -> SubprocessCheckResult:
    local_python = root / ".venv" / "bin" / "python"
    python_bin = str(local_python if local_python.exists() else Path(sys.executable))
    command = (python_bin, "-m", "pytest", "-q")
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (completed.stdout or "") + ((completed.stderr or "") if completed.stderr else "")
    return SubprocessCheckResult(
        name="pytest",
        command=command,
        passed=completed.returncode == 0,
        exit_code=completed.returncode,
        output=output.strip() or "(no output)",
    )
