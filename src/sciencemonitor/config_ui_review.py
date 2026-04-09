from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from .config import project_root
from .config_ui_page import render_page


@dataclass(frozen=True)
class ConfigUIReviewIssue:
    category: str
    message: str


@dataclass(frozen=True)
class ConfigUIReviewReport:
    passed: bool
    issues: list[ConfigUIReviewIssue]


def _sample_rendered_html(project: Path) -> str:
    return render_page(
        project=project,
        runtime={
            "features": {"weekly_report_enabled": True},
            "cli_defaults": {"daily_days_back": 7, "daily_max_per_source": 20, "report_window_days": 7},
            "deep_read": {"search_full_text_when_pdf_missing": True, "pdf_page_limit": 0},
        },
        analysis={
            "provider": "openrouter_api",
            "article_summaries": {"reasoning_effort": "medium"},
            "report": {"reasoning_effort": "medium"},
            "deep_reads": {"reasoning_effort": "high"},
            "codex_local": {"model": "", "sandbox": "read-only", "timeout_seconds": 180},
            "openai_api": {
                "model": "gpt-5-mini",
                "base_url": "https://api.openai.com/v1/responses",
                "api_key_env": "SCIENCEMONITOR_OPENAI_API_KEY",
                "api_key": "",
                "timeout_seconds": 120,
            },
            "openrouter_api": {
                "model": "openai/gpt-5-mini",
                "base_url": "https://openrouter.ai/api/v1/chat/completions",
                "api_key_env": "SCIENCEMONITOR_OPENROUTER_API_KEY",
                "api_key": "",
                "site_url": "https://example.com",
                "app_name": "ScienceMonitor",
                "timeout_seconds": 120,
            },
        },
        paths={
            "output_root": "out",
            "local_output_root": "/tmp/private-vault",
            "effective_output_root": "/tmp/private-vault",
            "local_paths_config": "/tmp/project/config/local.paths.json",
        },
        doctor={
            "warnings": [],
            "current_python": "/tmp/python",
            "provider_status": {
                "provider": "openrouter_api",
                "chatgpt_web_manual_pending": 1,
                "chatgpt_web_manual_ready": 2,
            },
        },
        status={},
        manual_requests=[
            SimpleNamespace(
                request_id="deep_read_internal_id",
                display_label="【待导入】Li（2026）- JGR.SP - 示例论文",
                status="pending",
                request_kind="deep_read",
                title="示例论文",
                response_filename="sample.json",
            )
        ],
        ui_state={
            "counts": {"article_summaries": 1, "deep_reads": 2, "reports": 3, "manual_files": 4},
            "journal_groups": [{"label": "核心监测", "items": ["JGR.SP", "SW"]}],
            "token_usage": "1234 tokens",
            "maintenance_status": {
                "overall": "ok",
                "doctor": "ok",
                "pytest": "ok",
                "harness": "ok",
                "entropy": "ok",
                "path": str(project / "log" / "maintenance" / "latest.md"),
            },
            "latest_report": str(project / "README.md"),
            "latest_deep_read": str(project / "README.md"),
            "latest_article_summary": str(project / "README.md"),
        },
    )


def _load_ui_css(project: Path) -> str:
    return (project / "src" / "sciencemonitor" / "ui_assets" / "config_ui.css").read_text(encoding="utf-8")


def _load_ui_js(project: Path) -> str:
    return (project / "src" / "sciencemonitor" / "ui_assets" / "config_ui.js").read_text(encoding="utf-8")


def _review_required_fragments(html: str) -> list[ConfigUIReviewIssue]:
    issues: list[ConfigUIReviewIssue] = []
    required_fragments = (
        "总览",
        "周报",
        "深度解读",
        "人工中转",
        "设置",
        "运行统计",
        "运行状态检查",
        "代码维护检查",
        "周报生成参数",
        "深度解读任务面板",
        "请求生成面板",
        "分析后端与服务",
        "OpenRouter API",
        "markdown-render",
        "data-tooltip=",
        "form-stack",
    )
    for fragment in required_fragments:
        if fragment not in html:
            issues.append(ConfigUIReviewIssue("missing_fragment", f"缺少 UI 关键片段：{fragment}"))
    return issues


def _review_forbidden_fragments(html: str) -> list[ConfigUIReviewIssue]:
    issues: list[ConfigUIReviewIssue] = []
    forbidden_fragments = (
        'class="nav-meta"',
        'value="chatgpt_web_manual"',
        "<h4>输出路径</h4>",
        "deep_read_internal_id",
    )
    for fragment in forbidden_fragments:
        if fragment in html:
            issues.append(ConfigUIReviewIssue("forbidden_fragment", f"UI 出现了不应暴露的片段：{fragment}"))
    return issues


def _review_required_css_fragments(css_text: str) -> list[ConfigUIReviewIssue]:
    issues: list[ConfigUIReviewIssue] = []
    required_fragments = (
        ".span-9 { grid-column: span 9; }",
        ".span-3 { grid-column: span 3; }",
        ".form-stack { display: flex; flex-direction: column; gap: 12px; }",
        ".weekly-report-grid",
        ".weekly-report-form-card",
        ".weekly-report-journals-card",
        "@media (max-width: 1100px)",
    )
    for fragment in required_fragments:
        if fragment not in css_text:
            issues.append(ConfigUIReviewIssue("missing_css_fragment", f"缺少 UI 布局关键 CSS：{fragment}"))
    return issues


def _review_required_js_fragments(js_text: str) -> list[ConfigUIReviewIssue]:
    issues: list[ConfigUIReviewIssue] = []
    required_fragments = (
        'const mainEl = document.querySelector(".main");',
        'mainEl.scrollTo({ top: 0, left: 0, behavior: "auto" });',
    )
    for fragment in required_fragments:
        if fragment not in js_text:
            issues.append(ConfigUIReviewIssue("missing_js_fragment", f"缺少 UI 交互关键 JS：{fragment}"))
    return issues


def run_config_ui_review(root: Path | None = None) -> ConfigUIReviewReport:
    project = root or project_root()
    html = _sample_rendered_html(project)
    css_text = _load_ui_css(project)
    js_text = _load_ui_js(project)
    issues = [
        *_review_required_fragments(html),
        *_review_forbidden_fragments(html),
        *_review_required_css_fragments(css_text),
        *_review_required_js_fragments(js_text),
    ]
    return ConfigUIReviewReport(passed=not issues, issues=issues)


def render_config_ui_review_summary(report: ConfigUIReviewReport) -> str:
    lines = [
        "Config UI review summary:",
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
