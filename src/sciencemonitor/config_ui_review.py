from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
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
        analysis=_sample_analysis_config(),
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
        ui_state=_sample_ui_state(project),
    )


def _sample_analysis_config() -> dict:
    return {
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
    }


def _sample_ui_state(project: Path) -> dict:
    start_day = date(2026, 3, 14)
    chart_days = []
    for offset in range(30):
        current = start_day + timedelta(days=offset)
        token_count = 0
        if current.isoformat() == "2026-04-09":
            token_count = 463894
        elif current.isoformat() == "2026-04-10":
            token_count = 438700
        chart_days.append(
            {
                "date": current.isoformat(),
                "label": f"{current.month}月{current.day}日",
                "short_label": f"{current.month}/{current.day}",
                "show_label": offset in {0, 29},
                "total_tokens": token_count,
                "runs": 1 if token_count else 0,
                "providers": {"codex_local": {"tokens": token_count, "label": "Codex 本地", "color": "#d9482b"}},
            }
        )
    return {
        "counts": {"article_summaries": 1, "deep_reads": 2, "reports": 3, "manual_files": 4},
        "journal_groups": [{"label": "核心监测", "items": ["JGR.SP", "SW"]}],
        "token_usage": "今天 0（0次） / 本周 902,594（2次） / 本月 902,594（2次）",
        "token_usage_periods": {
            "today": {"label": "今天", "tokens": 0, "runs": 0},
            "week": {"label": "本周", "tokens": 902594, "runs": 2},
            "month": {"label": "本月", "tokens": 902594, "runs": 2},
        },
        "token_usage_chart": {
            "max_tokens": 463894,
            "providers": [{"key": "codex_local", "label": "Codex 本地", "color": "#d9482b"}],
            "days": chart_days,
        },
        "report_job": {
            "status": "running",
            "step": "抓取与筛选文章",
            "message": "正在抓取最新论文。",
            "elapsed_seconds": 15.0,
            "estimated_total_seconds": 42.0,
            "fetched_count": 8,
            "kept_count": 3,
            "source_index": 2,
            "source_total": 6,
            "current_source": "jgr_space_physics",
        },
        "active_task": {
            "kind": "weekly_report",
            "label": "周报任务",
            "step": "抓取与筛选文章",
            "message": "正在抓取最新论文。",
            "status": "running",
        },
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
        "latest_manual_result": str(project / "README.md"),
    }


def _load_ui_css(project: Path) -> str:
    return (project / "src" / "sciencemonitor" / "ui_assets" / "config_ui.css").read_text(encoding="utf-8")


def _load_ui_js(project: Path) -> str:
    return (project / "src" / "sciencemonitor" / "ui_assets" / "config_ui.js").read_text(encoding="utf-8")


def _review_required_fragments(html: str) -> list[ConfigUIReviewIssue]:
    issues: list[ConfigUIReviewIssue] = []
    required_fragments = (
        'data-view="overview"',
        'data-view="weekly-report"',
        'data-view="deep-read"',
        'data-view="manual-llm"',
        'data-view="settings"',
        'data-nav-target="overview"',
        'data-nav-target="weekly-report"',
        'data-nav-target="deep-read"',
        'data-nav-target="manual-llm"',
        'data-nav-target="settings"',
        'data-provider-select',
        'data-provider-only="codex_local"',
        'data-provider-only="openai_api"',
        'data-provider-only="openrouter_api"',
        'data-provider-only="ollama_api"',
        'data-token-usage-root',
        'data-token-chart-frame',
        'data-token-chart-tooltip',
        'data-weekly-report-status-root',
        'data-task-trigger="weekly-report"',
        'data-task-trigger="deep-read"',
        'data-task-trigger="deep-read-folder"',
        'data-task-trigger="manual-create"',
        'data-task-trigger="manual-import"',
        'action="/run-deep-read-folder',
        'action="/manual-llm-import-upload',
        'data-tag-governance-link="formal"',
        'data-tag-governance-link="pending"',
        'data-tag-action="promote-pending"',
        'data-ui-panel="provider-settings"',
        'data-ui-panel="path-settings"',
        'data-ui-panel="tag-management"',
        'data-ui-panel="deep-read-single"',
        'data-ui-panel="deep-read-folder"',
        'data-ui-panel="manual-create"',
        'data-ui-panel="manual-import"',
        "markdown-render",
        "data-tooltip=",
        "form-stack",
        "token-chart-column",
        "token-chart-axis-y-ticks",
        "token-chart-axis-y",
        "token-chart-axis-x",
        "token-chart-axis-labels",
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
        "周报模式",
    )
    for fragment in forbidden_fragments:
        if fragment in html:
            issues.append(ConfigUIReviewIssue("forbidden_fragment", f"UI 出现了不应暴露的片段：{fragment}"))
    return issues


def _review_required_css_fragments(css_text: str) -> list[ConfigUIReviewIssue]:
    issues: list[ConfigUIReviewIssue] = []
    required_fragments = (
        ".span-9",
        ".span-3",
        ".form-stack",
        ".weekly-report-grid",
        ".weekly-report-form-card",
        ".weekly-report-journals-card",
        ".status-check-row",
        ".token-chart-days",
        ".token-chart-axis-y",
        ".token-chart-grid",
        ".token-chart-tooltip",
        ".token-provider-codex_local",
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
        'const weeklyReportStatusRoot = document.querySelector("[data-weekly-report-status-root]");',
        'const activeTaskTextRoot = document.querySelector("[data-active-task-text]");',
        'const activeTaskDetailRoot = document.querySelector("[data-active-task-detail]");',
        'const tokenUsageRoot = document.querySelector("[data-token-usage-root]");',
        'const uiToken = (document.querySelector(\'meta[name="sciencemonitor-ui-token"]\') || {}).content || "";',
        'button.disabled = hasRunningTask;',
        'window.fetch(withToken("/ui-status"), { cache: "no-store" })',
        'window.fetch(withToken(`/latest-result?kind=${encodeURIComponent(kind)}`), { cache: "no-store" })',
        'tokenUsageRoot.innerHTML = payload.token_usage_html;',
        "function handleTokenChartPointer(event) {",
        "tokenUsageRoot.addEventListener(\"pointermove\", handleTokenChartPointer);",
        "refreshChangedResults(payload.latest_results || {});",
    )
    for fragment in required_fragments:
        if fragment not in js_text:
            issues.append(ConfigUIReviewIssue("missing_js_fragment", f"缺少 UI 交互关键 JS：{fragment}"))
    forbidden_fragments = (
        "window.location.reload()",
    )
    for fragment in forbidden_fragments:
        if fragment in js_text:
            issues.append(ConfigUIReviewIssue("forbidden_js_fragment", f"不应存在会导致自动刷新的 JS：{fragment}"))
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
