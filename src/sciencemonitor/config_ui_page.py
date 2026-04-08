from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

from .config import config_ui_state_path, project_config_markdown_path
from .llm import SUPPORTED_ANALYSIS_PROVIDERS


def render_page(
    project: Path,
    runtime: dict,
    analysis: dict,
    paths: dict,
    doctor: dict,
    status: dict[str, str],
) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>ScienceMonitor Config UI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; margin: 0; background: #f6f7fb; color: #1f2937; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    .hero {{ background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 28px rgba(15, 23, 42, 0.08); margin-bottom: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .card {{ background: white; border-radius: 16px; padding: 18px; box-shadow: 0 8px 28px rgba(15, 23, 42, 0.08); }}
    .banner {{ border-radius: 12px; padding: 12px 14px; margin-bottom: 16px; }}
    .banner.ok {{ background: #e8fff1; color: #12663a; }}
    .banner.error {{ background: #fff1f2; color: #9f1239; }}
    .muted {{ color: #6b7280; font-size: 14px; }}
    .muted-label {{ color: #6b7280; font-size: 13px; margin-right: 6px; }}
    label {{ display: block; font-size: 14px; margin-bottom: 6px; font-weight: 600; }}
    input[type="text"], input[type="number"], input[type="date"], select {{ width: 100%; box-sizing: border-box; border: 1px solid #d1d5db; border-radius: 10px; padding: 10px 12px; margin-bottom: 12px; background: #fff; }}
    input[type="file"] {{ width: 100%; box-sizing: border-box; border: 1px dashed #94a3b8; border-radius: 12px; padding: 12px; margin-bottom: 12px; background: #f8fafc; }}
    .checks label {{ display: flex; align-items: center; gap: 8px; font-weight: 500; margin-bottom: 10px; }}
    .row {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .actions {{ position: sticky; bottom: 0; background: rgba(246,247,251,0.92); backdrop-filter: blur(8px); padding-top: 16px; }}
    .op-actions {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
    button {{ border: 0; border-radius: 999px; padding: 12px 18px; background: #0f766e; color: white; font-size: 15px; cursor: pointer; }}
    button.secondary {{ background: #1d4ed8; }}
    code {{ background: #eef2ff; padding: 2px 6px; border-radius: 6px; }}
    .pill {{ display: inline-block; padding: 4px 10px; border-radius: 999px; background: #eef2ff; color: #3730a3; font-size: 13px; margin-right: 8px; margin-bottom: 8px; }}
    .path-line {{ margin-top: 8px; word-break: break-all; }}
    .hint {{ margin-top: 8px; color: #475569; font-size: 13px; }}
  </style>
</head>
<body>
<main>
  {_render_hero_section(project, runtime, analysis, paths, doctor, status)}
  {_render_environment_section(warnings=doctor.get("warnings", []))}
  {_render_operations_section(runtime)}
  {_render_settings_form(runtime, analysis, paths)}
</main>
</body>
</html>"""


def _render_hero_section(project: Path, runtime: dict, analysis: dict, paths: dict, doctor: dict, status: dict[str, str]) -> str:
    provider = str(analysis.get("provider", "codex_local") or "codex_local")
    if provider not in SUPPORTED_ANALYSIS_PROVIDERS:
        provider = "codex_local"
    codex_model = str(analysis.get("codex_local", {}).get("model", "") or "").strip()
    effective_model = codex_model or "由本机 codex 默认模型决定"
    if provider == "chatgpt_web_manual":
        effective_model = "ChatGPT 网页人工中转"
    return f"""
  <section class="hero">
    <h1>ScienceMonitor 控制台</h1>
    <p class="muted">推荐先在这里修改常用配置。保存后会同步更新 JSON 配置文件和 <code>{html.escape(str(project_config_markdown_path(project)))}</code>。</p>
    {_render_status_banner(status)}
    <div class="grid">
      <div>
        <div class="pill">当前 provider: {html.escape(provider)}</div>
        <div class="pill">codex 模型: {html.escape(effective_model)}</div>
        <div class="pill">周报功能: {"开启" if runtime.get("features", {}).get("weekly_report_enabled", True) else "关闭"}</div>
        <div class="pill">深度解读功能: {"开启" if analysis.get("deep_reads", {}).get("enabled", True) else "关闭"}</div>
        <div class="pill">面板地址: {html.escape(_current_ui_url(project) or "未记录")}</div>
      </div>
      <div class="muted">
        <div>当前 Python：<code>{html.escape(doctor.get("current_python", ""))}</code></div>
        <div>输出目录：<code>{html.escape(paths.get("output_root", ""))}</code></div>
        <div>PDF 工具：<code>pdftotext / pdfinfo / pdftoppm</code></div>
      </div>
    </div>
  </section>"""


def _render_status_banner(status: dict[str, str]) -> str:
    if not status.get("kind"):
        return ""
    banner_class = "ok" if status.get("kind") == "ok" else "error"
    title = html.escape(status.get("title", ""))
    message = html.escape(status.get("message", ""))
    primary_path_html = _status_path_html(status.get("path", ""))
    secondary_path_html = _status_path_html(status.get("extra_path", ""))
    details = []
    if message:
        details.append(f"<div>{message}</div>")
    if primary_path_html:
        details.append(f'<div class="path-line"><span class="muted-label">输出：</span>{primary_path_html}</div>')
    if secondary_path_html:
        details.append(f'<div class="path-line"><span class="muted-label">资源：</span>{secondary_path_html}</div>')
    body = "".join(details)
    return f'<div class="banner {banner_class}"><strong>{title}</strong>{body}</div>'


def _render_environment_section(*, warnings: list[str]) -> str:
    warnings_html = (
        "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in warnings) + "</ul>"
        if warnings
        else "<p>当前自检无告警。</p>"
    )
    return f"""
  <section class="card" style="margin-bottom: 20px;">
    <h2>环境状态</h2>
    {warnings_html}
    <p class="muted">如果这里出现告警，建议先运行 <code>./scripts/run_science_monitor.sh doctor</code> 定位环境问题。关闭浏览器页签不会自动关闭后台服务；如需停止，可使用下方按钮或根目录的 <code>关闭操作面板.app</code>。</p>
    <form method="post" action="/shutdown-ui" style="margin-top: 12px;">
      <button type="submit">关闭面板服务</button>
    </form>
  </section>"""


def _render_operations_section(runtime: dict) -> str:
    return f"""
  <section class="grid" style="margin-bottom: 20px;">
    <form class="card" method="post" action="/run-report">
      <h2>开始生成周报</h2>
      <p class="muted">这里是直接执行任务的入口。可以选择先抓取更新，再自动完成单篇总结和周报输出。</p>
      <div class="row">
        {_date_input("report_date", date.today().isoformat(), "报告日期")}
        {_number("report_window_days_run", runtime.get("cli_defaults", {}).get("report_window_days", 7), "统计窗口（天）")}
      </div>
      <div class="checks">
        {_checkbox("run_update_before_report", True, "先更新再生成")}
      </div>
      <div class="row">
        {_number("report_update_days_back", runtime.get("cli_defaults", {}).get("daily_days_back", 7), "更新回看天数")}
        {_number("report_max_per_source_run", runtime.get("cli_defaults", {}).get("daily_max_per_source", 20), "每源抓取上限")}
      </div>
      {_text("report_source_ids", "", "限定期刊 source_ids（可选，逗号分隔）")}
      <div class="op-actions">
        <button type="submit" class="secondary">开始生成周报</button>
      </div>
      <p class="hint">生成链路：抓取更新 -> 单篇总结 -> 周报输出。若取消“先更新再生成”，则直接基于当前数据库重建周报。</p>
    </form>

    <form class="card" method="post" action="/run-deep-read" enctype="multipart/form-data">
      <h2>开始深度解读</h2>
      <p class="muted">优先提供 PDF。没有 PDF 时，系统会按 DOI 或题目尝试搜索全文；如果仍然找不到，会明确返回需要提供 PDF 的提示。</p>
      <label for="deep_read_pdf">拖拽或选择 PDF</label>
      <input type="file" id="deep_read_pdf" name="deep_read_pdf" accept=".pdf,application/pdf">
      {_text("deep_read_pdf_path", "", "或填写本地 PDF 路径（可选）")}
      {_text("deep_read_doi", "", "DOI（可选）")}
      {_text("deep_read_title", "", "论文题目（可选）")}
      <div class="row">
        {_text("deep_read_journal", "", "期刊名（可选）")}
        {_text("deep_read_url", "", "落地页 URL（可选）")}
      </div>
      <div class="op-actions">
        <button type="submit">开始深度解读</button>
      </div>
      <p class="hint">有 PDF 时优先按 PDF 深读；没有 PDF 时会尝试 DOI / 题目检索全文。</p>
    </form>
  </section>"""


def _render_settings_form(runtime: dict, analysis: dict, paths: dict) -> str:
    provider = str(analysis.get("provider", "codex_local") or "codex_local")
    if provider not in SUPPORTED_ANALYSIS_PROVIDERS:
        provider = "codex_local"
    return f"""
  <form method="post" action="/save-config">
    <div class="grid">
      {_render_feature_flags_card(runtime, analysis)}
      {_render_runtime_window_card(runtime)}
      {_render_llm_card(analysis, provider)}
      {_render_codex_card(analysis)}
      {_render_openai_card(analysis)}
      {_render_deep_read_card(runtime, paths)}
    </div>

    <div class="actions">
      <button type="submit">保存配置并同步 PROJECT_CONFIG.md</button>
    </div>
  </form>"""


def _render_feature_flags_card(runtime: dict, analysis: dict) -> str:
    return f"""
      <section class="card">
        <h2>功能开关</h2>
        <div class="checks">
          {_checkbox("weekly_report_enabled", runtime.get("features", {}).get("weekly_report_enabled", True), "启用周报生成功能")}
          {_checkbox("deep_reads_enabled", analysis.get("deep_reads", {}).get("enabled", True), "启用深度解读功能")}
          {_checkbox("search_full_text_when_pdf_missing", runtime.get("deep_read", {}).get("search_full_text_when_pdf_missing", True), "未提供 PDF 时自动搜索全文")}
        </div>
        <p class="muted">深度解读优先使用 PDF；如果没有 PDF，会按 DOI/题目尝试获取全文，失败时返回需要提供 PDF 的提示。</p>
      </section>"""


def _render_runtime_window_card(runtime: dict) -> str:
    return f"""
      <section class="card">
        <h2>调研时间与抓取范围</h2>
        <div class="row">
          {_number("daily_days_back", runtime.get("cli_defaults", {}).get("daily_days_back", 7), "daily 回看天数")}
          {_number("daily_max_per_source", runtime.get("cli_defaults", {}).get("daily_max_per_source", 20), "daily 每源上限")}
        </div>
        <div class="row">
          {_number("update_days_back", runtime.get("cli_defaults", {}).get("update_days_back", 7), "update 回看天数")}
          {_number("update_max_per_source", runtime.get("cli_defaults", {}).get("update_max_per_source", 20), "update 每源上限")}
        </div>
        <div class="row">
          {_number("report_window_days", runtime.get("cli_defaults", {}).get("report_window_days", 7), "report 窗口天数")}
          {_number("summaries_window_days", runtime.get("cli_defaults", {}).get("summaries_window_days", 7), "summaries 窗口天数")}
        </div>
        <div class="row">
          {_number("audit_window_days", runtime.get("cli_defaults", {}).get("audit_window_days", 7), "audit 窗口天数")}
          {_number("audit_max_per_source", runtime.get("cli_defaults", {}).get("audit_max_per_source", 100), "audit 每源上限")}
        </div>
        <div class="checks">
          {_checkbox("update_hydrate", runtime.get("cli_defaults", {}).get("update_hydrate", True), "抓取时自动补摘要")}
        </div>
      </section>"""


def _render_llm_card(analysis: dict, provider: str) -> str:
    return f"""
      <section class="card">
        <h2>LLM 总体配置</h2>
        {_select("provider", provider, [("codex_local", "codex_local"), ("openai_api", "openai_api"), ("chatgpt_web_manual", "chatgpt_web_manual")], "分析后端")}
        <div class="row">
          {_checkbox("article_summaries_enabled", analysis.get("article_summaries", {}).get("enabled", True), "启用单篇总结 LLM")}
          {_checkbox("report_enabled", analysis.get("report", {}).get("enabled", True), "启用周报 LLM 分析")}
        </div>
        <div class="row">
          {_number("article_summaries_max_items_per_run", analysis.get("article_summaries", {}).get("max_items_per_run", 0), "单篇总结 LLM 数量")}
          {_number("report_max_papers_in_prompt", analysis.get("report", {}).get("max_papers_in_prompt", 50), "周报送入 LLM 篇数")}
        </div>
        <div class="row">
          {_select("article_summaries_reasoning_effort", analysis.get("article_summaries", {}).get("reasoning_effort", "medium"), [("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "xhigh")], "单篇总结推理强度")}
          {_select("report_reasoning_effort", analysis.get("report", {}).get("reasoning_effort", "medium"), [("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "xhigh")], "周报推理强度")}
        </div>
        <p class="muted">当前已不再支持规则法兜底。单篇总结、周报和深度解读都需要有效的 LLM 分析结果。推理强度设置仅对 codex_local 生效；如果选择 chatgpt_web_manual，程序会写出请求包，等待你在 ChatGPT 网页完成后再导入响应。</p>
      </section>"""


def _render_codex_card(analysis: dict) -> str:
    return f"""
      <section class="card">
        <h2>Codex Local</h2>
        {_text("codex_model", analysis.get("codex_local", {}).get("model", ""), "模型名（留空则使用本机 Codex 默认模型）")}
        {_text("codex_executable", analysis.get("codex_local", {}).get("executable", ""), "codex 可执行文件路径（可留空）")}
        <div class="row">
          {_select("codex_sandbox", analysis.get("codex_local", {}).get("sandbox", "read-only"), [("read-only", "read-only"), ("workspace-write", "workspace-write"), ("danger-full-access", "danger-full-access")], "sandbox")}
          {_number("codex_timeout_seconds", analysis.get("codex_local", {}).get("timeout_seconds", 300), "超时秒数")}
        </div>
      </section>"""


def _render_openai_card(analysis: dict) -> str:
    return f"""
      <section class="card">
        <h2>OpenAI API / 兼容接口</h2>
        {_text("openai_model", analysis.get("openai_api", {}).get("model", "gpt-5-mini"), "模型名")}
        {_text("openai_base_url", analysis.get("openai_api", {}).get("base_url", "https://api.openai.com/v1/responses"), "base_url")}
        {_text("openai_api_key_env", analysis.get("openai_api", {}).get("api_key_env", "SCIENCEMONITOR_OPENAI_API_KEY"), "API key 环境变量名")}
        {_text("openai_api_key", analysis.get("openai_api", {}).get("api_key", ""), "直接写入配置的 API key（不推荐）")}
        <div class="row">
          {_number("openai_timeout_seconds", analysis.get("openai_api", {}).get("timeout_seconds", 120), "超时秒数")}
          {_number("deep_reads_max_input_chars", analysis.get("deep_reads", {}).get("max_input_chars", 28000), "深度解读最大输入字符")}
        </div>
        <div class="row">
          {_select("deep_reads_reasoning_effort", analysis.get("deep_reads", {}).get("reasoning_effort", "high"), [("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "xhigh")], "深度解读推理强度")}
          <div></div>
        </div>
      </section>"""


def _render_deep_read_card(runtime: dict, paths: dict) -> str:
    return f"""
      <section class="card">
        <h2>深度解读参数</h2>
        <div class="row">
          {_number("pdf_page_limit", runtime.get("deep_read", {}).get("pdf_page_limit", 40), "PDF 最多读取页数")}
          {_text("output_root", paths.get("output_root", ""), "输出目录 output_root")}
        </div>
        <p class="muted">深度解读会优先读取 PDF；如果 PDF 缺失，则尝试依据 DOI/题目搜索全文。若未获得 PDF 或可判定的全文页面，命令会明确返回失败并提示提供 PDF。</p>
      </section>"""


def render_error_page(project: Path, message: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>ScienceMonitor Config UI</title></head>
<body style="font-family: sans-serif; margin: 32px;">
  <h1>配置保存失败</h1>
  <p>{html.escape(message)}</p>
  <p><a href="/">返回配置界面</a></p>
  <p><code>{html.escape(str(project_config_markdown_path(project)))}</code></p>
</body></html>"""


def render_shutdown_page(project: Path) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>ScienceMonitor Config UI</title></head>
<body style="font-family: sans-serif; margin: 32px;">
  <h1>控制面板服务正在关闭</h1>
  <p>浏览器页签可以直接关闭。后续如果还要使用，请重新双击启动器。</p>
  <p><code>{html.escape(str(config_ui_state_path(project)))}</code></p>
</body></html>"""


def _current_ui_url(project: Path) -> str:
    path = config_ui_state_path(project)
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("url", "") or "")


def _status_path_html(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    path = Path(cleaned).expanduser()
    if path.is_absolute():
        try:
            uri = path.as_uri()
        except ValueError:
            uri = ""
        if uri:
            return f'<a href="{html.escape(uri)}"><code>{html.escape(cleaned)}</code></a>'
    return f"<code>{html.escape(cleaned)}</code>"


def _checkbox(name: str, checked: bool, label: str) -> str:
    return f'<label><input type="checkbox" name="{html.escape(name)}" {"checked" if checked else ""}> {html.escape(label)}</label>'


def _text(name: str, value: str, label: str) -> str:
    return f'<label for="{html.escape(name)}">{html.escape(label)}</label><input type="text" id="{html.escape(name)}" name="{html.escape(name)}" value="{html.escape(str(value or ""))}">'


def _number(name: str, value: int, label: str) -> str:
    return f'<label for="{html.escape(name)}">{html.escape(label)}</label><input type="number" id="{html.escape(name)}" name="{html.escape(name)}" value="{int(value)}">'


def _date_input(name: str, value: str, label: str) -> str:
    return f'<label for="{html.escape(name)}">{html.escape(label)}</label><input type="date" id="{html.escape(name)}" name="{html.escape(name)}" value="{html.escape(str(value or ""))}">'


def _select(name: str, value: str, options: list[tuple[str, str]], label: str) -> str:
    option_html = "".join(
        f'<option value="{html.escape(option_value)}" {"selected" if option_value == value else ""}>{html.escape(option_label)}</option>'
        for option_value, option_label in options
    )
    return f'<label for="{html.escape(name)}">{html.escape(label)}</label><select id="{html.escape(name)}" name="{html.escape(name)}">{option_html}</select>'
