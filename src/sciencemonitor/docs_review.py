from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import project_root


USER_GUIDE_FILES = {
    "agent_skill_usage.md",
    "chatgpt_web_manual_workflow.md",
    "deep_reading_comparison_and_fusion.md",
    "eval_governance_runbook.md",
    "literature_codex_quick_guide.md",
    "literature_directory_integration_guide.md",
    "llm_analysis_readme.md",
    "maintenance_governance_runbook.md",
    "python_module_map.md",
    "release_checklist.md",
}

WORKFLOW_SPEC_FILES = {
    "README.md",
    "article_summary_template_guide.md",
    "daily_report_template_guide.md",
    "deep_reading_template_guide.md",
    "hierarchical_tag_reference.md",
    "literature_note_style_guide.md",
    "llm_prompt_contracts.md",
    "report_review_rules.md",
    "rules.md",
    "source_of_truth_matrix.md",
}


@dataclass(frozen=True)
class DocsReviewIssue:
    category: str
    path: Path
    message: str


@dataclass(frozen=True)
class DocsReviewReport:
    passed: bool
    issues: list[DocsReviewIssue]


def run_docs_review(root: Path | None = None) -> DocsReviewReport:
    project = root or project_root()
    docs_root = project / "docs"
    issues: list[DocsReviewIssue] = []

    issues.extend(_check_expected_locations(docs_root / "user_guides", USER_GUIDE_FILES, "user_guides"))
    issues.extend(_check_expected_locations(docs_root / "workflow_specs", WORKFLOW_SPEC_FILES, "workflow_specs"))
    issues.extend(_check_misplaced_known_docs(docs_root))

    legacy_template = docs_root / "exec_plans" / "TEMPLATE.md"
    if legacy_template.exists():
        issues.append(
            DocsReviewIssue(
                category="legacy_template",
                path=legacy_template,
                message="`docs/exec_plans/TEMPLATE.md` 不应继续保留；ExecPlan 模板 source of truth 已迁到 config/templates。",
            )
        )
    legacy_tag_reference = docs_root / "workflow_specs" / "常用分级标签参考.md"
    if legacy_tag_reference.exists():
        issues.append(
            DocsReviewIssue(
                category="legacy_doc_name",
                path=legacy_tag_reference,
                message="旧的中文文件名 `常用分级标签参考.md` 不应继续保留；应统一为 `hierarchical_tag_reference.md`。",
            )
        )

    return DocsReviewReport(passed=not issues, issues=issues)


def render_docs_review_summary(report: DocsReviewReport) -> str:
    lines = [
        "Docs review summary:",
        f"- issues={len(report.issues)}",
        f"- overall={'ok' if report.passed else 'failed'}",
    ]
    if report.issues:
        lines.append("- violations:")
        for issue in report.issues:
            lines.append(f"  - {issue.path.name}: {issue.message}")
    else:
        lines.append("- violations: none")
    return "\n".join(lines)


def _check_expected_locations(directory: Path, filenames: set[str], label: str) -> list[DocsReviewIssue]:
    issues: list[DocsReviewIssue] = []
    for filename in sorted(filenames):
        path = directory / filename
        if not path.exists():
            issues.append(
                DocsReviewIssue(
                    category="missing_doc",
                    path=path,
                    message=f"缺少应放在 `{label}/` 下的说明文件：`{filename}`。",
                )
            )
    return issues


def _check_misplaced_known_docs(docs_root: Path) -> list[DocsReviewIssue]:
    issues: list[DocsReviewIssue] = []
    for filename in sorted(USER_GUIDE_FILES):
        misplaced = docs_root / "workflow_specs" / filename
        if misplaced.exists():
            issues.append(
                DocsReviewIssue(
                    category="misplaced_doc",
                    path=misplaced,
                    message=f"`{filename}` 主要供用户阅读，应放在 `user_guides/`，不应留在 `workflow_specs/`。",
                )
            )
    for filename in sorted(WORKFLOW_SPEC_FILES):
        misplaced = docs_root / "user_guides" / filename
        if misplaced.exists():
            issues.append(
                DocsReviewIssue(
                    category="misplaced_doc",
                    path=misplaced,
                    message=f"`{filename}` 属于 workflow spec，不应放在 `user_guides/`。",
                )
            )
    return issues
