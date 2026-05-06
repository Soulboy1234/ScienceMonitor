from __future__ import annotations

import re
from pathlib import Path


REPORT_TEMPLATE_VAR_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
REQUIRED_REPORT_HEADINGS = [
    "## 周报信息",
    "## 今日概览",
    "### 本周重点方向分布",
    "### 整体观察",
    "### 与当前工作相关的重点",
    "## 文章推荐",
    "### 推荐论文",
    "### 建议重点关注的事件或物理过程",
    "### 对当前工作的可能启发",
    "## 主题推荐",
    "## 各期刊主题汇总",
    "## 其他",
    "### 未完成或未获取摘要/全文的文献",
    "### 附注",
]
REPORT_TEMPLATE_REQUIRED_MARKERS = [
    "----",
    "标题：Space Physics Daily Report -",
    "统计窗口：近",
    "监控期刊：",
    *REQUIRED_REPORT_HEADINGS,
    "- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。",
    "- 生成时间：",
]
REPORT_TEMPLATE_REQUIRED_VARS = {
    "report_date",
    "window_days",
    "journals",
    "report_info_block",
    "overview_table_block",
    "objective_overview_block",
    "preference_overview_block",
    "recommended_papers_block",
    "recommended_processes_block",
    "work_implications_block",
    "theme_recommendations_block",
    "journal_roundup_block",
    "missing_sources_block",
    "generated_at",
}
REPORT_REVIEW_MAX_PASSES = 3


def load_report_template(template_path: Path) -> str:
    template_text = template_path.read_text(encoding="utf-8")
    validate_report_template(template_text, template_path)
    return template_text


def validate_report_template(template_text: str, template_path: Path) -> None:
    missing_markers = [marker for marker in REPORT_TEMPLATE_REQUIRED_MARKERS if marker not in template_text]
    if missing_markers:
        joined = "、".join(missing_markers)
        raise ValueError(f"Daily report template missing required markers in {template_path}: {joined}")

    found_vars = set(REPORT_TEMPLATE_VAR_RE.findall(template_text))
    missing_vars = sorted(REPORT_TEMPLATE_REQUIRED_VARS - found_vars)
    if missing_vars:
        joined = ", ".join(missing_vars)
        raise ValueError(f"Daily report template missing required placeholders in {template_path}: {joined}")


def render_report_template(template_text: str, context: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise ValueError(f"Daily report template placeholder has no context value: {key}")
        return str(context[key])

    rendered = REPORT_TEMPLATE_VAR_RE.sub(replace, template_text)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def join_report_lines(lines: list[str]) -> str:
    return "\n".join(lines)


def validate_report_markdown(markdown: str) -> list[str]:
    issues: list[str] = []
    for marker in [
        "标题：Space Physics Daily Report -",
        "统计窗口：近",
        "监控期刊：",
        *REQUIRED_REPORT_HEADINGS,
        "- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。",
        "- 生成时间：",
    ]:
        if marker not in markdown:
            issues.append(f"缺少报告模板要求的区块：{marker}")
    if "{{" in markdown or "}}" in markdown:
        issues.append("报告正文仍包含未替换的模板占位符")
    return issues


def run_report_review_loop(markdown: str) -> tuple[str, list[str]]:
    reviewed = markdown
    for _ in range(REPORT_REVIEW_MAX_PASSES):
        fixed = autofix_report_markdown(reviewed)
        issues = audit_report_markdown(fixed)
        if not issues:
            return fixed, []
        if fixed == reviewed:
            return fixed, issues
        reviewed = fixed
    return reviewed, audit_report_markdown(reviewed)


def autofix_report_markdown(markdown: str) -> str:
    fixed = markdown.replace("\r\n", "\n").replace("\r", "\n")
    fixed = re.sub(r"[ \t]+\n", "\n", fixed)
    fixed = re.sub(r"\n{3,}", "\n\n", fixed)
    fixed = re.sub(r"(?m)^(### .+)\n\n+(?=(?:\||- |\s+\d+\.\s))", r"\1\n", fixed)
    fixed = re.sub(r"(?m)^(#### .+)\n\n+(?=   - )", r"\1\n", fixed)
    fixed = re.sub(r"(?m)^(### .+)\n{3,}", r"\1\n\n", fixed)
    return fixed.strip() + "\n"


def audit_report_markdown(markdown: str) -> list[str]:
    issues: list[str] = []
    for heading in REQUIRED_REPORT_HEADINGS:
        pattern = re.compile(rf"(?m)^{re.escape(heading)}\n\n\n+")
        if pattern.search(markdown):
            issues.append(f"报告区块 {heading} 后存在多余空行")
    if re.search(r"(?m)^### .+\n\n(?=(?:\\||- |\\d+\\. ))", markdown):
        issues.append("周报三级标题与后续表格或列表之间存在多余空行")
    if "| 期刊 | 新增文章数 |" not in markdown:
        issues.append("周报信息缺少期刊统计表")
    if "| 重点方向 | 文章数 | 重点期刊 |" not in markdown:
        issues.append("今日概览缺少重点方向统计表")
    return issues
