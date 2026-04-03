from __future__ import annotations

import cgi
import html
import io
import json
import os
import webbrowser
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlparse

from .article_summaries import sanitize_filename
from .config import (
    config_ui_state_path,
    load_runtime_config,
    path_config_path,
    project_config_markdown_path,
    project_root,
    runtime_config_path,
    sync_configs_from_project_markdown,
    write_project_config_markdown,
)
from .deep_reads import run_deep_read
from .doctor import run_doctor
from .llm import DEFAULT_ANALYSIS_CONFIG, SUPPORTED_ANALYSIS_PROVIDERS
from .pipeline import ScienceMonitor


def serve_config_ui(
    root: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    project = root or project_root()
    server = ThreadingHTTPServer((host, port), _build_handler(project))
    url = f"http://{host}:{port}/"
    _write_config_ui_state(project, host=host, port=port, url=url)
    print(f"ScienceMonitor config UI is running at {url}")
    print("Press Ctrl-C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _clear_config_ui_state(project)


def _build_handler(project: Path):
    class ConfigUIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            sync_configs_from_project_markdown(project)
            query = parse_qs(urlparse(self.path).query)
            status = _status_payload_from_query(query)
            doctor = run_doctor(project)
            runtime = load_runtime_config(project)
            analysis = _load_analysis_config(project)
            paths = _load_paths_config(project)
            payload = _render_page(project, runtime, analysis, paths, doctor, status)
            self._send_html(payload)

        def do_POST(self) -> None:  # noqa: N802
            action = urlparse(self.path).path or "/save-config"
            try:
                if action == "/shutdown-ui":
                    payload = _render_shutdown_page(project)
                    self._send_html(payload)
                    Thread(target=self.server.shutdown, daemon=True).start()
                    return

                form, files = _parse_form_data(self)
                if action == "/save-config":
                    _save_from_form(project, form)
                    params = {"kind": "ok", "title": "配置已保存", "message": "配置已保存，并同步回 PROJECT_CONFIG.md。"}
                elif action == "/run-report":
                    params = _run_report_action(project, form)
                elif action == "/run-deep-read":
                    params = _run_deep_read_action(project, form, files)
                else:
                    payload = _render_error_page(project, f"未知操作路径：{action}")
                    self._send_html(payload, status=HTTPStatus.NOT_FOUND)
                    return
            except Exception as exc:
                payload = _render_error_page(project, str(exc))
                self._send_html(payload, status=HTTPStatus.BAD_REQUEST)
                return

            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/?" + urlencode(params))
            self.end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send_html(self, payload: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return ConfigUIHandler


def _save_from_form(project: Path, form: dict[str, list[str]]) -> None:
    runtime = load_runtime_config(project)
    analysis = _load_analysis_config(project)
    paths = _load_paths_config(project)

    runtime.setdefault("features", {})
    runtime.setdefault("cli_defaults", {})
    runtime.setdefault("deep_read", {})
    analysis.setdefault("article_summaries", {})
    analysis.setdefault("report", {})
    analysis.setdefault("deep_reads", {})
    analysis.setdefault("codex_local", {})
    analysis.setdefault("openai_api", {})
    analysis["article_summaries"].pop("fallback_to_rules", None)
    analysis["report"].pop("fallback_to_rules", None)
    analysis["deep_reads"].pop("fallback_to_rules", None)

    runtime["features"]["weekly_report_enabled"] = _bool_field(form, "weekly_report_enabled")

    runtime["cli_defaults"]["daily_days_back"] = _int_field(form, "daily_days_back", minimum=1)
    runtime["cli_defaults"]["daily_max_per_source"] = _int_field(form, "daily_max_per_source", minimum=1)
    runtime["cli_defaults"]["update_days_back"] = _int_field(form, "update_days_back", minimum=1)
    runtime["cli_defaults"]["update_max_per_source"] = _int_field(form, "update_max_per_source", minimum=1)
    runtime["cli_defaults"]["update_hydrate"] = _bool_field(form, "update_hydrate")
    runtime["cli_defaults"]["report_window_days"] = _int_field(form, "report_window_days", minimum=1)
    runtime["cli_defaults"]["summaries_window_days"] = _int_field(form, "summaries_window_days", minimum=1)
    runtime["cli_defaults"]["audit_window_days"] = _int_field(form, "audit_window_days", minimum=1)
    runtime["cli_defaults"]["audit_max_per_source"] = _int_field(form, "audit_max_per_source", minimum=1)

    runtime["deep_read"]["search_full_text_when_pdf_missing"] = _bool_field(form, "search_full_text_when_pdf_missing")
    runtime["deep_read"]["pdf_page_limit"] = _int_field(form, "pdf_page_limit", minimum=1)

    analysis["provider"] = _text_field(form, "provider") or "codex_local"
    if analysis["provider"] not in SUPPORTED_ANALYSIS_PROVIDERS:
        supported = "、".join(SUPPORTED_ANALYSIS_PROVIDERS)
        raise ValueError(f"provider 只支持：{supported}")
    analysis["article_summaries"]["enabled"] = _bool_field(form, "article_summaries_enabled")
    analysis["article_summaries"]["max_items_per_run"] = _int_field(form, "article_summaries_max_items_per_run", minimum=0)
    analysis["article_summaries"]["reasoning_effort"] = _text_field(form, "article_summaries_reasoning_effort") or "medium"
    analysis["report"]["enabled"] = _bool_field(form, "report_enabled")
    analysis["report"]["max_papers_in_prompt"] = _int_field(form, "report_max_papers_in_prompt", minimum=1)
    analysis["report"]["reasoning_effort"] = _text_field(form, "report_reasoning_effort") or "medium"
    analysis["deep_reads"]["enabled"] = _bool_field(form, "deep_reads_enabled")
    analysis["deep_reads"]["max_input_chars"] = _int_field(form, "deep_reads_max_input_chars", minimum=2000)
    analysis["deep_reads"]["reasoning_effort"] = _text_field(form, "deep_reads_reasoning_effort") or "high"
    analysis["codex_local"]["model"] = _text_field(form, "codex_model")
    analysis["codex_local"]["executable"] = _text_field(form, "codex_executable")
    analysis["codex_local"]["sandbox"] = _text_field(form, "codex_sandbox") or "read-only"
    analysis["codex_local"]["timeout_seconds"] = _int_field(form, "codex_timeout_seconds", minimum=30)
    analysis["openai_api"]["api_key"] = _text_field(form, "openai_api_key")
    analysis["openai_api"]["api_key_env"] = _text_field(form, "openai_api_key_env") or "SCIENCEMONITOR_OPENAI_API_KEY"
    analysis["openai_api"]["model"] = _text_field(form, "openai_model") or "gpt-5-mini"
    analysis["openai_api"]["base_url"] = _text_field(form, "openai_base_url") or "https://api.openai.com/v1/responses"
    analysis["openai_api"]["timeout_seconds"] = _int_field(form, "openai_timeout_seconds", minimum=30)

    paths["output_root"] = _text_field(form, "output_root")
    if not paths["output_root"]:
        raise ValueError("output_root 不能为空。")

    runtime_config_path(project).write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (project / "config" / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path_config_path(project).write_text(json.dumps(paths, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_project_config_markdown(project)


def _render_page(
    project: Path,
    runtime: dict,
    analysis: dict,
    paths: dict,
    doctor: dict,
    status: dict[str, str],
) -> str:
    status_html = ""
    if status.get("kind"):
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
        status_html = f'<div class="banner {banner_class}"><strong>{title}</strong>{body}</div>'

    provider = str(analysis.get("provider", "codex_local") or "codex_local")
    if provider not in SUPPORTED_ANALYSIS_PROVIDERS:
        provider = "codex_local"
    codex_model = str(analysis.get("codex_local", {}).get("model", "") or "").strip()
    effective_model = codex_model or "由本机 codex 默认模型决定"
    warnings = doctor.get("warnings", [])
    warnings_html = (
        "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in warnings) + "</ul>"
        if warnings
        else "<p>当前自检无告警。</p>"
    )

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
  <section class="hero">
    <h1>ScienceMonitor 控制台</h1>
    <p class="muted">推荐先在这里修改常用配置。保存后会同步更新 JSON 配置文件和 <code>{html.escape(str(project_config_markdown_path(project)))}</code>。</p>
    {status_html}
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
  </section>

  <section class="card" style="margin-bottom: 20px;">
    <h2>环境状态</h2>
    {warnings_html}
    <p class="muted">如果这里出现告警，建议先运行 <code>./scripts/run_science_monitor.sh doctor</code> 定位环境问题。关闭浏览器页签不会自动关闭后台服务；如需停止，可使用下方按钮或根目录的 <code>关闭操作面板.app</code>。</p>
    <form method="post" action="/shutdown-ui" style="margin-top: 12px;">
      <button type="submit">关闭面板服务</button>
    </form>
  </section>

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
  </section>

  <form method="post" action="/save-config">
    <div class="grid">
      <section class="card">
        <h2>功能开关</h2>
        <div class="checks">
          {_checkbox("weekly_report_enabled", runtime.get("features", {}).get("weekly_report_enabled", True), "启用周报生成功能")}
          {_checkbox("deep_reads_enabled", analysis.get("deep_reads", {}).get("enabled", True), "启用深度解读功能")}
          {_checkbox("search_full_text_when_pdf_missing", runtime.get("deep_read", {}).get("search_full_text_when_pdf_missing", True), "未提供 PDF 时自动搜索全文")}
        </div>
        <p class="muted">深度解读优先使用 PDF；如果没有 PDF，会按 DOI/题目尝试获取全文，失败时返回需要提供 PDF 的提示。</p>
      </section>

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
      </section>

      <section class="card">
        <h2>LLM 总体配置</h2>
        {_select("provider", provider, [("codex_local", "codex_local"), ("openai_api", "openai_api")], "分析后端")}
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
        <p class="muted">当前已不再支持规则法兜底。单篇总结、周报和深度解读都需要有效的 LLM 分析结果。推理强度设置仅对 codex_local 生效。</p>
      </section>

      <section class="card">
        <h2>Codex Local</h2>
        {_text("codex_model", analysis.get("codex_local", {}).get("model", ""), "模型名（留空则使用本机 Codex 默认模型）")}
        {_text("codex_executable", analysis.get("codex_local", {}).get("executable", ""), "codex 可执行文件路径（可留空）")}
        <div class="row">
          {_select("codex_sandbox", analysis.get("codex_local", {}).get("sandbox", "read-only"), [("read-only", "read-only"), ("workspace-write", "workspace-write"), ("danger-full-access", "danger-full-access")], "sandbox")}
          {_number("codex_timeout_seconds", analysis.get("codex_local", {}).get("timeout_seconds", 300), "超时秒数")}
        </div>
      </section>

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
      </section>

      <section class="card">
        <h2>深度解读参数</h2>
        <div class="row">
          {_number("pdf_page_limit", runtime.get("deep_read", {}).get("pdf_page_limit", 40), "PDF 最多读取页数")}
          {_text("output_root", paths.get("output_root", ""), "输出目录 output_root")}
        </div>
        <p class="muted">深度解读会优先读取 PDF；如果 PDF 缺失，则尝试依据 DOI/题目搜索全文。若未获得 PDF 或可判定的全文页面，命令会明确返回失败并提示提供 PDF。</p>
      </section>
    </div>

    <div class="actions">
      <button type="submit">保存配置并同步 PROJECT_CONFIG.md</button>
    </div>
  </form>
</main>
</body>
</html>"""


def _render_error_page(project: Path, message: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>ScienceMonitor Config UI</title></head>
<body style="font-family: sans-serif; margin: 32px;">
  <h1>配置保存失败</h1>
  <p>{html.escape(message)}</p>
  <p><a href="/">返回配置界面</a></p>
  <p><code>{html.escape(str(project_config_markdown_path(project)))}</code></p>
</body></html>"""


def _render_shutdown_page(project: Path) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>ScienceMonitor Config UI</title></head>
<body style="font-family: sans-serif; margin: 32px;">
  <h1>控制面板服务正在关闭</h1>
  <p>浏览器页签可以直接关闭。后续如果还要使用，请重新双击启动器。</p>
  <p><code>{html.escape(str(config_ui_state_path(project)))}</code></p>
</body></html>"""


def _load_analysis_config(project: Path) -> dict:
    path = project / "config" / "analysis.json"
    merged = json.loads(json.dumps(DEFAULT_ANALYSIS_CONFIG))
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        _deep_update(merged, payload if isinstance(payload, dict) else {})
    return merged


def _load_paths_config(project: Path) -> dict:
    path = path_config_path(project)
    if not path.exists():
        return {"output_root": "out"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"output_root": "out"}


def _status_payload_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    return {
        "kind": query.get("kind", [""])[0],
        "title": query.get("title", [""])[0],
        "message": query.get("message", [""])[0],
        "path": query.get("path", [""])[0],
        "extra_path": query.get("extra_path", [""])[0],
    }


def _write_config_ui_state(project: Path, host: str, port: int, url: str) -> None:
    payload = {
        "pid": os.getpid(),
        "host": host,
        "port": port,
        "url": url,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    path = config_ui_state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clear_config_ui_state(project: Path) -> None:
    path = config_ui_state_path(project)
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        path.unlink(missing_ok=True)
        return
    if int(payload.get("pid", -1)) == os.getpid():
        path.unlink(missing_ok=True)


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


def _parse_form_data(handler: BaseHTTPRequestHandler) -> tuple[dict[str, list[str]], dict[str, cgi.FieldStorage]]:
    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
        "CONTENT_LENGTH": handler.headers.get("Content-Length", "0"),
    }
    form_data = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ=environ,
        keep_blank_values=True,
    )
    fields: dict[str, list[str]] = {}
    files: dict[str, cgi.FieldStorage] = {}
    if not form_data.list:
        return fields, files
    for item in form_data.list:
        if item.filename:
            files[item.name] = item
            continue
        fields.setdefault(item.name, []).append(str(item.value or ""))
    return fields, files


def _run_report_action(project: Path, form: dict[str, list[str]]) -> dict[str, str]:
    report_date = _date_field(form, "report_date")
    window_days = _int_field(form, "report_window_days_run", minimum=1)
    run_update = _bool_field(form, "run_update_before_report")
    max_per_source = _int_field(form, "report_max_per_source_run", minimum=1)
    update_days_back = _int_field(form, "report_update_days_back", minimum=1)
    source_ids = _source_ids_field(form, "report_source_ids")

    monitor = ScienceMonitor(project)
    try:
        if not monitor.weekly_report_enabled():
            raise ValueError("周报功能当前已关闭。请先在配置中开启“启用周报生成功能”，再生成周报。")
        if run_update:
            update_result, report_path, stats = monitor.run_daily(
                report_date=report_date,
                days_back=update_days_back,
                max_per_source=max_per_source,
                source_ids=source_ids or None,
            )
            message = (
                f"已完成更新并生成周报。候选 {update_result.fetched_count} 条，保留 {update_result.kept_count} 篇；"
                f"周报覆盖 {stats.get('paper_count', 0)} 篇论文、{stats.get('journal_count', 0)} 本期刊。"
            )
            if update_result.error_count:
                message += f" 另有 {update_result.error_count} 个来源报错，请再检查日志。"
        else:
            report_path, stats = monitor.generate_windowed_report(report_date=report_date, window_days=window_days)
            message = (
                f"已基于当前数据库重建周报，窗口 {window_days} 天；"
                f"覆盖 {stats.get('paper_count', 0)} 篇论文、{stats.get('journal_count', 0)} 本期刊。"
            )
            if source_ids:
                message += " 注意：未勾选“先更新再生成”时，限定期刊 source_ids 不生效。"
        return {
            "kind": "ok",
            "title": "周报生成完成",
            "message": message,
            "path": str(report_path),
        }
    finally:
        monitor.close()


def _run_deep_read_action(
    project: Path,
    form: dict[str, list[str]],
    files: dict[str, cgi.FieldStorage],
) -> dict[str, str]:
    uploaded_pdf = files.get("deep_read_pdf")
    uploaded_path = _save_uploaded_pdf(project, uploaded_pdf) if uploaded_pdf else None
    local_pdf_path = _text_field(form, "deep_read_pdf_path")
    pdf_path = str(uploaded_path) if uploaded_path else local_pdf_path
    doi = _text_field(form, "deep_read_doi")
    title = _text_field(form, "deep_read_title")
    journal = _text_field(form, "deep_read_journal")
    url = _text_field(form, "deep_read_url")

    if not pdf_path and not doi and not title:
        raise ValueError("请至少提供 PDF、DOI 或论文题目中的一项。")

    monitor = ScienceMonitor(project)
    try:
        result = run_deep_read(
            root=project,
            storage=monitor.storage,
            doi=doi,
            title=title,
            pdf_path=pdf_path,
            journal=journal,
            url=url,
        )
    finally:
        monitor.close()

    if not result.success:
        return {
            "kind": "error",
            "title": "深度解读失败",
            "message": result.message,
            "path": str(uploaded_path) if uploaded_path else "",
        }

    message = f"已完成深度解读，全文来源类型：{result.source_kind or 'unknown'}。"
    if not pdf_path:
        message += " 本次未提供 PDF，系统已自动尝试获取全文。"
    return {
        "kind": "ok",
        "title": "深度解读完成",
        "message": message,
        "path": str(result.output_path) if result.output_path else "",
        "extra_path": str(result.pdf_output_path) if result.pdf_output_path else "",
    }


def _save_uploaded_pdf(project: Path, file_item: cgi.FieldStorage | None) -> Path | None:
    if file_item is None or not getattr(file_item, "filename", ""):
        return None
    filename = sanitize_filename(Path(str(file_item.filename)).name) or "uploaded.pdf"
    suffix = Path(filename).suffix.lower()
    content_type = str(getattr(file_item, "type", "") or "").lower()
    if suffix != ".pdf" and content_type != "application/pdf":
        raise ValueError("当前只支持上传 PDF 文件。")

    upload_dir = project / "tmp" / "ui_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(filename).stem or "uploaded"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = upload_dir / f"{timestamp}-{stem}.pdf"
    index = 1
    while candidate.exists():
        candidate = upload_dir / f"{timestamp}-{stem}-{index}.pdf"
        index += 1

    with candidate.open("wb") as handle:
        payload = file_item.file.read()
        handle.write(payload if isinstance(payload, bytes) else bytes(payload))
    return candidate


def _date_field(form: dict[str, list[str]], name: str) -> date:
    raw = _text_field(form, name)
    if not raw:
        raise ValueError(f"{name} 不能为空。")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是 YYYY-MM-DD 格式。") from exc


def _source_ids_field(form: dict[str, list[str]], name: str) -> set[str]:
    raw = _text_field(form, name)
    return {item.strip() for item in raw.split(",") if item.strip()}


def _deep_update(target: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _bool_field(form: dict[str, list[str]], name: str) -> bool:
    return name in form


def _int_field(form: dict[str, list[str]], name: str, minimum: int = 0) -> int:
    raw = _text_field(form, name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数。") from exc
    if value < minimum:
        raise ValueError(f"{name} 必须大于等于 {minimum}。")
    return value


def _text_field(form: dict[str, list[str]], name: str) -> str:
    return str(form.get(name, [""])[0]).strip()


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
