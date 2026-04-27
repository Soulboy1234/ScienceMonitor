from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import focus_tags_config_path, formal_tags_markdown_path, pending_tags_json_path, pending_tags_markdown_path, project_root
from .tag_governance import (
    PENDING_FAMILY_BY_ID,
    collect_pending_tag_usage,
    ensure_tag_governance_files,
    govern_pending_candidate_tag,
    parse_pending_tag_review_decisions,
    parse_formal_tags_markdown,
    sync_formal_tags_to_focus_tags_json_if_markdown_newer,
)


@dataclass(frozen=True)
class TagGovernanceReviewIssue:
    category: str
    message: str


@dataclass(frozen=True)
class TagGovernanceReviewReport:
    passed: bool
    issues: list[TagGovernanceReviewIssue]


def run_tag_governance_review(root: Path | None = None) -> TagGovernanceReviewReport:
    project = root or project_root()
    ensure_tag_governance_files(project, refresh_pending=False)
    sync_formal_tags_to_focus_tags_json_if_markdown_newer(project)
    issues: list[TagGovernanceReviewIssue] = []

    focus_path = focus_tags_config_path(project)
    formal_path = formal_tags_markdown_path(project)
    pending_json_path = pending_tags_json_path(project)
    pending_md_path = pending_tags_markdown_path(project)

    for path, label in (
        (focus_path, "focus_tags.json"),
        (formal_path, "formal_tags.md"),
        (pending_json_path, "pending_tags.json"),
        (pending_md_path, "pending_tags.md"),
    ):
        if not path.exists():
            issues.append(TagGovernanceReviewIssue("missing_file", f"缺少标签治理文件：{label}"))

    if issues:
        return TagGovernanceReviewReport(passed=False, issues=issues)

    focus_payload = json.loads(focus_path.read_text(encoding="utf-8"))
    pending_payload = json.loads(pending_json_path.read_text(encoding="utf-8"))
    formal_by_category = parse_formal_tags_markdown(formal_path.read_text(encoding="utf-8"), focus_payload)

    json_formal_labels = {
        str(item.get("label", "")).strip()
        for item in focus_payload.get("tags", [])
        if isinstance(item, dict) and str(item.get("label", "")).strip()
    }
    markdown_formal_labels = {
        label.strip()
        for labels in formal_by_category.values()
        for label in labels
        if str(label).strip()
    }
    if markdown_formal_labels != json_formal_labels:
        issues.append(
            TagGovernanceReviewIssue(
                "formal_drift",
                "formal_tags.md 与 focus_tags.json 的正式标签集合不一致。",
            )
        )

    tag_rules = focus_payload.get("tag_rules", {}) if isinstance(focus_payload, dict) else {}
    if str((tag_rules or {}).get("pending_tags_path", "") or "") != "config/pending_tags.json":
        issues.append(
            TagGovernanceReviewIssue(
                "pending_path",
                "focus_tags.json 的 tag_rules.pending_tags_path 必须指向 config/pending_tags.json。",
            )
        )

    pending_tags = pending_payload.get("tags", {}) if isinstance(pending_payload, dict) else {}
    if not isinstance(pending_tags, dict):
        issues.append(TagGovernanceReviewIssue("pending_structure", "pending_tags.json 的 tags 必须是对象。"))
        return TagGovernanceReviewReport(passed=False, issues=issues)

    overlap = sorted(tag for tag in pending_tags if tag in json_formal_labels)
    if overlap:
        issues.append(
            TagGovernanceReviewIssue(
                "pending_overlap",
                f"这些 tag 已经进入正式体系，却仍保留在预选中：{', '.join(overlap[:10])}",
            )
        )

    try:
        parse_pending_tag_review_decisions(project)
    except Exception as exc:
        issues.append(TagGovernanceReviewIssue("pending_markdown_structure", f"预选 Markdown 结构与 JSON 不一致：{exc}"))

    usage_counts = collect_pending_tag_usage(project)
    for tag, entry in pending_tags.items():
        if not isinstance(entry, dict):
            issues.append(TagGovernanceReviewIssue("pending_entry_type", f"预选 tag 记录格式异常：{tag}"))
            continue
        family_id = str(entry.get("family", "") or "").strip()
        if family_id not in PENDING_FAMILY_BY_ID:
            issues.append(TagGovernanceReviewIssue("pending_family_missing", f"预选 tag 缺少有效家族：{tag}"))
            break
        decision = govern_pending_candidate_tag(tag, formal_labels=json_formal_labels, focus_payload=focus_payload)
        if decision.status != "pending":
            issues.append(
                TagGovernanceReviewIssue(
                    "pending_should_not_exist",
                    f"预选 tag 已可被清洗掉或并入正式体系，不应继续停留在 pending：{tag}",
                )
            )
            break
        if decision.tag != tag:
            issues.append(
                TagGovernanceReviewIssue(
                    "pending_not_normalized",
                    f"预选 tag 还没有落到规范化后的待审名称：{tag} -> {decision.tag}",
                )
            )
            break
        expected = usage_counts.get(tag, {"count": 0, "by_kind": {"article_summaries": 0, "deep_reads": 0}})
        actual_count = int(entry.get("usage_count", 0) or 0)
        actual_by_kind = entry.get("usage_by_kind", {}) if isinstance(entry.get("usage_by_kind"), dict) else {}
        if actual_count != int(expected.get("count", 0) or 0):
            issues.append(
                TagGovernanceReviewIssue(
                    "usage_count_drift",
                    f"预选 tag 使用次数与真实输出库不一致：{tag}",
                )
            )
            break
        expected_by_kind = expected.get("by_kind", {}) if isinstance(expected.get("by_kind"), dict) else {}
        if (
            int(actual_by_kind.get("article_summaries", 0) or 0) != int(expected_by_kind.get("article_summaries", 0) or 0)
            or int(actual_by_kind.get("deep_reads", 0) or 0) != int(expected_by_kind.get("deep_reads", 0) or 0)
        ):
            issues.append(
                TagGovernanceReviewIssue(
                    "usage_kind_drift",
                    f"预选 tag 分类型使用次数与真实输出库不一致：{tag}",
                )
            )
            break

    return TagGovernanceReviewReport(passed=not issues, issues=issues)


def render_tag_governance_review_summary(report: TagGovernanceReviewReport) -> str:
    lines = [
        "Tag governance review summary:",
        f"- issues={len(report.issues)}",
        f"- overall={'ok' if report.passed else 'failed'}",
    ]
    if report.issues:
        lines.append("- violations:")
        for item in report.issues:
            lines.append(f"  - {item.category}: {item.message}")
    else:
        lines.append("- violations: none")
    return "\n".join(lines)
