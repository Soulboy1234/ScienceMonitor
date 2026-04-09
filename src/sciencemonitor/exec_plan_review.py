from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import project_root


REQUIRED_SECTION_TITLES = [
    "## 目的 / 大图景",
    "## 背景与定位",
    "## 工作范围",
    "## 非目标",
    "## 进度",
    "## 计划中的工作",
    "## 具体步骤",
    "## 发现与意外",
    "## 决策记录",
    "## 结果与复盘",
    "## 验证",
]

SECTION_ALIASES = {
    "## 目的 / 大图景": {"## Purpose / Big Picture"},
    "## 背景与定位": {"## Context and Orientation"},
    "## 进度": {"## Progress"},
    "## 计划中的工作": {"## Plan of Work"},
    "## 具体步骤": {"## Concrete Steps"},
    "## 发现与意外": {"## Surprises & Discoveries"},
    "## 决策记录": {"## Decision Log"},
    "## 结果与复盘": {"## Outcomes & Retrospective"},
}


@dataclass(frozen=True)
class ExecPlanIssue:
    category: str
    plan_path: Path
    message: str


@dataclass(frozen=True)
class ActiveExecPlanStatus:
    plan_path: Path
    checked_steps: list[str]
    pending_steps: list[str]


@dataclass(frozen=True)
class ExecPlanCheckReport:
    passed: bool
    template_path: Path
    active_plans: list[Path]
    completed_plans: list[Path]
    active_statuses: list[ActiveExecPlanStatus]
    issues: list[ExecPlanIssue]


def exec_plan_template_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "templates" / "exec_plan_template.md"


def run_exec_plan_check(root: Path | None = None) -> ExecPlanCheckReport:
    project = root or project_root()
    plans_root = project / "docs" / "exec_plans"
    active_root = plans_root / "active"
    completed_root = plans_root / "completed"
    template_path = exec_plan_template_path(project)
    active_plans = sorted(active_root.glob("*.md"))
    completed_plans = sorted(completed_root.glob("*.md"))
    active_statuses = [_collect_active_plan_status(path) for path in active_plans]
    issues: list[ExecPlanIssue] = []

    issues.extend(_check_template(template_path))
    for path in active_plans:
        issues.extend(_check_plan(path, require_checked_progress=False))

    return ExecPlanCheckReport(
        passed=not issues,
        template_path=template_path,
        active_plans=active_plans,
        completed_plans=completed_plans,
        active_statuses=active_statuses,
        issues=issues,
    )


def render_exec_plan_check_summary(report: ExecPlanCheckReport) -> str:
    lines = [
        "Exec plan check summary:",
        f"- template_source_of_truth={report.template_path}",
        f"- active_plans={len(report.active_plans)}",
        f"- completed_plans={len(report.completed_plans)}",
        "- completed_policy=archive_only",
        f"- issues={len(report.issues)}",
        f"- overall={'ok' if report.passed else 'failed'}",
    ]
    if report.active_statuses:
        lines.append("- active_plan_status:")
        for item in report.active_statuses:
            lines.append(
                f"  - {item.plan_path.name}: done={len(item.checked_steps)} pending={len(item.pending_steps)}"
            )
            if item.pending_steps:
                lines.append(f"    next={'; '.join(item.pending_steps[:3])}")
    if report.issues:
        lines.append("- violations:")
        for issue in report.issues:
            lines.append(f"  - {issue.plan_path.name}: {issue.message}")
    else:
        lines.append("- violations: none")
    return "\n".join(lines)


def _check_template(path: Path) -> list[ExecPlanIssue]:
    if not path.exists():
        return [ExecPlanIssue(category="missing_template", plan_path=path, message="缺少 ExecPlan 模板文件 exec_plan_template.md。")]
    return _check_required_sections(path, require_checked_progress=False)


def _check_plan(path: Path, *, require_checked_progress: bool) -> list[ExecPlanIssue]:
    issues = _check_required_sections(path, require_checked_progress=require_checked_progress)
    if not path.exists():
        return issues
    text = path.read_text(encoding="utf-8")
    progress_lines = _progress_lines(text)
    if not progress_lines:
        issues.append(ExecPlanIssue(category="missing_progress_items", plan_path=path, message="`进度` 段必须包含 `- [ ]` 或 `- [x]` 勾选项。"))
    if require_checked_progress:
        unchecked = [line for line in progress_lines if line.startswith("- [ ]")]
        if unchecked:
            issues.append(ExecPlanIssue(category="unchecked_progress", plan_path=path, message="`completed/` 中的计划不能保留未完成勾选项。"))
    return issues


def _check_required_sections(path: Path, *, require_checked_progress: bool) -> list[ExecPlanIssue]:
    if not path.exists():
        return [ExecPlanIssue(category="missing_plan", plan_path=path, message="计划文件不存在。")]
    text = path.read_text(encoding="utf-8")
    headings = [line.strip() for line in text.splitlines() if line.startswith("## ")]
    canonical_positions: list[int] = []
    issues: list[ExecPlanIssue] = []
    for title in REQUIRED_SECTION_TITLES:
        aliases = {title, *SECTION_ALIASES.get(title, set())}
        index = next((i for i, heading in enumerate(headings) if heading in aliases), -1)
        if index < 0:
            issues.append(ExecPlanIssue(category="missing_section", plan_path=path, message=f"缺少必需标题：`{title}`。"))
            continue
        canonical_positions.append(index)
    if canonical_positions and canonical_positions != sorted(canonical_positions):
        issues.append(ExecPlanIssue(category="section_order", plan_path=path, message="必需标题顺序不稳定，请按模板顺序排列。"))
    if require_checked_progress and "## 进度" not in headings and "## Progress" not in headings:
        issues.append(ExecPlanIssue(category="missing_progress_section", plan_path=path, message="缺少 `## 进度` 段。"))
    return issues


def _progress_lines(text: str) -> list[str]:
    lines = text.splitlines()
    in_progress = False
    progress: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line in {"## 进度", "## Progress"}:
            in_progress = True
            continue
        if in_progress and line.startswith("## "):
            break
        if in_progress and (line.startswith("- [ ]") or line.startswith("- [x]")):
            progress.append(line)
    return progress


def _collect_active_plan_status(path: Path) -> ActiveExecPlanStatus:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    checked: list[str] = []
    pending: list[str] = []
    for line in _progress_lines(text):
        body = line[5:].strip()
        if line.startswith("- [x]"):
            checked.append(body)
        elif line.startswith("- [ ]"):
            pending.append(body)
    return ActiveExecPlanStatus(
        plan_path=path,
        checked_steps=checked,
        pending_steps=pending,
    )
