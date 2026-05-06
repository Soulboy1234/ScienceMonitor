from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import urlencode

from .config import output_root
from .config_ui_markdown import render_obsidian_markdown_file


def render_latest_result_card(project: Path, title: str, path_value: str, empty_text: str, *, result_key: str = "") -> str:
    content = render_latest_result_content(project, path_value, empty_text)
    result_attrs = ""
    if result_key:
        result_attrs = (
            f' data-latest-result-body="{html.escape(result_key)}"'
            f' data-latest-result-path="{html.escape(str(path_value or ""))}"'
            f' data-latest-result-revision="{html.escape(result_file_revision(path_value))}"'
        )
    return f"""
      <section class="panel span-12">
        <div class="panel-header">
          <div><h3>{html.escape(title)}</h3></div>
        </div>
        <div class="panel-body"{result_attrs}>
          {content}
        </div>
      </section>"""


def render_latest_result_content(project: Path, path_value: str, empty_text: str) -> str:
    if not path_value:
        return f'<p class="muted">{html.escape(empty_text)}</p>'
    return _render_file_summary(project, Path(path_value))


def result_file_revision(path_value: str) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        return ""
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def render_weekly_report_status_card(report_job: object) -> str:
    if not isinstance(report_job, dict) or not report_job:
        body = '<div class="status-check-item" data-weekly-report-status-body><strong>未运行</strong><p>当前没有正在执行的周报任务。</p></div>'
    else:
        status_class = _weekly_report_status_class(report_job)
        message = str(report_job.get("message", "") or "暂无状态信息。")
        step = str(report_job.get("step", "") or "处理中")
        metric_text = " · ".join(_weekly_report_metrics(report_job))
        current_source = str(report_job.get("current_source", "") or "") if str(report_job.get("stage", "") or "") == "fetching" else ""
        current_source_html = _optional_status_line("当前来源", current_source, mono=True)
        current_summary_html = _optional_status_line("当前单篇", _current_summary_label(report_job))
        body = (
            f'<div class="{status_class}" data-weekly-report-status-body>'
            f"<strong>{html.escape(step)}</strong>"
            f"<p>{html.escape(message)}</p>"
            f"<p>{html.escape(metric_text)}</p>"
            f"{current_source_html}"
            f"{current_summary_html}"
            f"</div>"
        )
    return f"""
      <section class="panel span-12" data-weekly-report-status-root>
        <div class="panel-header">
          <div><h3>周报运行状态</h3></div>
        </div>
        <div class="panel-body">
          <div class="status-check-list">
            {body}
          </div>
        </div>
      </section>"""


def render_deep_read_status_card(deep_read_job: object) -> str:
    if not isinstance(deep_read_job, dict) or not deep_read_job:
        body = '<div class="status-check-item" data-deep-read-status-body><strong>未运行</strong><p>当前没有正在执行的深度解读任务。</p></div>'
    else:
        status_class = _deep_read_status_class(deep_read_job)
        message = str(deep_read_job.get("message", "") or "暂无状态信息。")
        step = str(deep_read_job.get("step", "") or "处理中")
        metric_text = " · ".join(_deep_read_metrics(deep_read_job))
        current_pdf_html = _optional_status_line("当前 PDF", str(deep_read_job.get("current_pdf", "") or ""))
        body = (
            f'<div class="{status_class}" data-deep-read-status-body>'
            f"<strong>{html.escape(step)}</strong>"
            f"<p>{html.escape(message)}</p>"
            f"{f'<p>{html.escape(metric_text)}</p>' if metric_text else ''}"
            f"{current_pdf_html}"
            f"</div>"
        )
    return f"""
      <section class="panel span-12" data-deep-read-status-root>
        <div class="panel-header">
          <div><h3>深度解读运行状态</h3></div>
        </div>
        <div class="panel-body">
          <div class="status-check-list">
            {body}
          </div>
        </div>
      </section>"""


def _weekly_report_status_class(report_job: dict) -> str:
    status = str(report_job.get("status", "") or "")
    return {
        "running": "status-check-item",
        "success": "status-check-item ok",
        "paused_quota": "status-check-item ok",
        "paused_timeout": "status-check-item ok",
        "error": "status-check-item error",
    }.get(status, "status-check-item")


def _deep_read_status_class(deep_read_job: dict) -> str:
    status = str(deep_read_job.get("status", "") or "")
    return {
        "running": "status-check-item",
        "success": "status-check-item ok",
        "paused_quota": "status-check-item ok",
        "paused_timeout": "status-check-item ok",
        "error": "status-check-item error",
    }.get(status, "status-check-item")


def _current_summary_label(report_job: dict) -> str:
    title = str(report_job.get("summary_current_title", "") or "")
    journal = str(report_job.get("summary_current_journal", "") or "")
    if journal and title.startswith(f"{journal} · "):
        return title
    if journal and title:
        return f"{journal} · {title}"
    return title


def _weekly_report_metrics(report_job: dict) -> list[str]:
    status = str(report_job.get("status", "") or "")
    fetched = int(report_job.get("fetched_count", 0) or 0)
    kept = int(report_job.get("kept_count", 0) or 0)
    paper_count = int(report_job.get("paper_count", 0) or 0)
    journal_count = int(report_job.get("journal_count", 0) or 0)
    source_index = int(report_job.get("source_index", 0) or 0)
    source_total = int(report_job.get("source_total", 0) or 0)
    summary_total = int(report_job.get("summary_total", 0) or 0)
    summary_completed = int(report_job.get("summary_completed", 0) or 0)
    summary_skipped = int(report_job.get("summary_skipped", 0) or 0)
    summary_provider = str(report_job.get("summary_provider", "") or "")
    summary_model = str(report_job.get("summary_model", "") or "")
    summary_reasoning_effort = str(report_job.get("summary_reasoning_effort", "") or "")
    summary_avg_tokens = int(report_job.get("summary_avg_tokens", 0) or 0)
    summary_token_samples = int(report_job.get("summary_token_samples", 0) or 0)
    elapsed = _format_duration_seconds(report_job.get("elapsed_seconds"))
    estimated = _format_duration_seconds(report_job.get("estimated_total_seconds"))
    metrics: list[str] = [f"运行时长：{elapsed}"]
    if status == "paused_quota":
        metrics.append("状态：等待额度恢复后继续")
    if status == "paused_timeout":
        metrics.append("状态：本地模型超时，可调整超时后继续")
    if estimated:
        metrics.append(f"预计总时长：{estimated}")
    if fetched:
        metrics.append(f"已抓取：{fetched}")
    if kept:
        metrics.append(f"已保留：{kept}")
    if paper_count:
        metrics.append(f"周报论文：{paper_count}")
    if journal_count:
        metrics.append(f"期刊数：{journal_count}")
    if source_total:
        metrics.append(f"来源进度：{source_index}/{source_total}")
    if summary_total:
        metrics.append(f"单篇总结：{summary_completed}/{summary_total}")
    if summary_skipped:
        metrics.append(f"未完成单篇：{summary_skipped}")
    if summary_model:
        metrics.append(f"模型：{summary_model}")
    elif summary_provider:
        metrics.append(f"后端：{summary_provider}")
    if summary_provider == "codex_local" and summary_reasoning_effort:
        metrics.append(f"推理强度：{summary_reasoning_effort}")
    if summary_avg_tokens:
        metrics.append(f"平均单篇 token：{summary_avg_tokens}")
    elif summary_total and summary_provider in {"codex_local", "openai_api", "openrouter_api", "ollama_api"} and summary_token_samples == 0:
        metrics.append("平均单篇 token：本次未新调用")
    return metrics


def _deep_read_metrics(deep_read_job: dict) -> list[str]:
    metrics: list[str] = []
    elapsed = _format_duration_seconds(deep_read_job.get("elapsed_seconds"))
    estimated = _format_duration_seconds(deep_read_job.get("estimated_total_seconds"))
    if elapsed:
        metrics.append(f"运行时长：{elapsed}")
    if estimated:
        metrics.append(f"预计总时长：{estimated}")
    total = int(deep_read_job.get("total", 0) or 0)
    completed = int(deep_read_job.get("completed", 0) or 0)
    if total > 1:
        metrics.append(f"批量进度：{completed}/{total}")
    success_count = int(deep_read_job.get("success_count", 0) or 0)
    failure_count = int(deep_read_job.get("failure_count", 0) or 0)
    if total > 1 or success_count or failure_count:
        metrics.append(f"成功：{success_count}")
        metrics.append(f"失败：{failure_count}")
    source_kind = str(deep_read_job.get("source_kind", "") or "")
    if source_kind:
        metrics.append(f"全文来源：{source_kind}")
    output_path = str(deep_read_job.get("output_path", "") or "")
    if output_path:
        metrics.append(f"最新输出：{Path(output_path).name}")
    return metrics


def _optional_status_line(label: str, value: str, *, mono: bool = False) -> str:
    if not value:
        return ""
    content = f'<span class="mono">{html.escape(value)}</span>' if mono else html.escape(value)
    return f"<p>{html.escape(label)}：{content}</p>"


def _render_file_summary(project: Path, path: Path) -> str:
    if not path.exists():
        return f'<p class="muted">文件不存在：<code>{html.escape(str(path))}</code></p>'
    if path.suffix.lower() == ".md":
        return _render_markdown_file_summary(project, path)
    link = _render_file_link(path, label=path.name, new_tab=True)
    relative_hint = _render_relative_hint(project, path)
    return f'<div class="result-block"><div class="result-path">{link}</div><div class="muted">{relative_hint}</div></div>'


def _render_markdown_file_summary(project: Path, path: Path) -> str:
    link = _render_file_link(path, label=path.name, new_tab=True)
    relative_hint = _render_relative_hint(project, path)
    rendered = render_obsidian_markdown_file(path)
    return f"""
      <div class="result-block">
        <div class="result-path">{link}</div>
        <div class="muted">{relative_hint}</div>
        <article class="markdown-render">{rendered}</article>
      </div>"""


def _render_relative_hint(project: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(project.resolve())
        return relative.as_posix()
    except ValueError:
        try:
            relative = path.resolve().relative_to(output_root(project).resolve())
            return f"out/{relative.as_posix()}"
        except ValueError:
            return str(path)


def _format_duration_seconds(value: object) -> str:
    try:
        seconds = max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return ""
    minutes, remain = divmod(int(round(seconds)), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {remain}s"
    return f"{remain}s"


def _render_file_link(path: Path, *, label: str, download: bool = False, new_tab: bool = False) -> str:
    params = {"path": str(path)}
    if download:
        params["download"] = "1"
    href = "/local-file?" + urlencode(params)
    attrs = ' target="_blank" rel="noopener noreferrer"' if new_tab else ""
    return f'<a class="file-link" href="{html.escape(href)}"{attrs}>{html.escape(label)}</a>'
