from __future__ import annotations

import html
from pathlib import Path

from .chatgpt_web_manual import ManualRequestStatus
from .config import config_ui_state_path, project_config_markdown_path
from .config_ui_page_sections import (
    render_deep_read_view,
    render_manual_view,
    render_overview_view,
    render_settings_view,
    render_sidebar,
    render_topbar,
    render_weekly_report_view,
)


def render_page(
    project: Path,
    runtime: dict,
    analysis: dict,
    paths: dict,
    doctor: dict,
    status: dict[str, str],
    manual_requests: list[ManualRequestStatus] | None = None,
    ui_state: dict | None = None,
    ui_token: str = "",
) -> str:
    manual_requests = manual_requests or []
    ui_state = ui_state or {}
    css_text = _load_asset("config_ui.css")
    js_text = _load_asset("config_ui.js")
    nav_items = [
        ("overview", "总览"),
        ("weekly-report", "周报"),
        ("deep-read", "深度解读"),
        ("manual-llm", "人工中转"),
        ("settings", "设置"),
    ]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
	  <meta charset="utf-8">
	  <meta name="sciencemonitor-ui" content="config-ui">
	  <meta name="sciencemonitor-ui-token" content="{html.escape(ui_token)}">
	  <title>ScienceMonitor 控制台</title>
  <style>{css_text}</style>
</head>
<body>
  <div class="app">
    <div class="sidebar-shell">
      {render_sidebar(project, runtime, analysis, paths, doctor, nav_items, ui_state)}
    </div>
    <div class="sidebar-resizer" data-sidebar-resizer role="separator" aria-orientation="vertical" aria-label="调整导航栏宽度"></div>
    <main class="main">
      <div class="main-shell">
        {render_topbar()}
        <div class="stack">
	      {render_overview_view(project, runtime, analysis, paths, doctor, status, manual_requests, ui_state, ui_token=ui_token)}
	      {render_weekly_report_view(project, runtime, status, ui_state, ui_token=ui_token)}
	      {render_deep_read_view(project, runtime, paths, status, ui_state, ui_token=ui_token)}
	      {render_manual_view(project, status, manual_requests, ui_state, ui_token=ui_token)}
	      {render_settings_view(project, runtime, analysis, paths, ui_token=ui_token)}
        </div>
      </div>
    </main>
  </div>
  <script>{js_text}</script>
</body>
</html>"""


def render_error_page(project: Path, message: str) -> str:
    from html import escape

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>ScienceMonitor 控制台</title></head>
<body style="font-family: sans-serif; margin: 32px;">
  <h1>控制台操作失败</h1>
  <p>{escape(message)}</p>
  <p><a href="/">返回控制台</a></p>
  <p><code>{escape(str(project_config_markdown_path(project)))}</code></p>
</body></html>"""


def render_shutdown_page(project: Path) -> str:
    from html import escape

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>ScienceMonitor 控制台</title></head>
<body style="font-family: sans-serif; margin: 32px;">
  <h1>控制台服务正在关闭</h1>
  <p>浏览器页签可以直接关闭。后续如需继续使用，请重新启动 config-ui。</p>
  <p><code>{escape(str(config_ui_state_path(project)))}</code></p>
</body></html>"""


def _load_asset(name: str) -> str:
    return (Path(__file__).with_name("ui_assets") / name).read_text(encoding="utf-8")
