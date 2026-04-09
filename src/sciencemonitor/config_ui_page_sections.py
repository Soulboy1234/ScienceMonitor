from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from .analysis_providers import ALL_PROVIDER_LABELS, automatic_provider_choices
from .chatgpt_web_manual import ManualRequestStatus
from .config import config_ui_state_path, output_root
from .config_ui_markdown import render_obsidian_markdown_file


def render_sidebar(project: Path, runtime: dict, analysis: dict, paths: dict, doctor: dict, nav_items: list[tuple[str, str]]) -> str:
    provider = _display_provider_label(str(analysis.get("provider", "codex_local") or "codex_local"))
    effective_output = str(paths.get("effective_output_root", paths.get("output_root", "")) or "")
    manual_pending = int(doctor.get("provider_status", {}).get("chatgpt_web_manual_pending", 0) or 0)
    manual_ready = int(doctor.get("provider_status", {}).get("chatgpt_web_manual_ready", 0) or 0)
    current_version = _current_release_version(project)
    ui_url = _current_ui_url(project) or "未记录"
    nav_html = []
    for target, label in nav_items:
        nav_html.append(
            f'<a class="nav-link" href="#{html.escape(target)}" data-nav-target="{html.escape(target)}">'
            f'<span class="nav-label">{html.escape(label)}</span>'
            f"</a>"
        )
    weekly_enabled = bool(runtime.get("features", {}).get("weekly_report_enabled", True))
    return f"""
    <aside class="sidebar">
      <div class="brand">
        <h1>ScienceMonitor <span class="brand-version">{html.escape(current_version)}</span></h1>
      </div>
      <div class="sidebar-group">
        <div class="sidebar-title">主导航</div>
        <div class="nav-list">
          {''.join(nav_html)}
        </div>
      </div>
      <div class="sidebar-footer">
        <p class="footer-line"><strong>当前 provider</strong><br>{html.escape(provider)}</p>
        <p class="footer-line"><strong>周报模式</strong><br>{"手动生成已启用" if weekly_enabled else "已关闭"}</p>
        <p class="footer-line"><strong>人工中转</strong><br>pending {manual_pending} / ready {manual_ready}</p>
        <p class="footer-line"><strong>面板地址</strong><br><span class="mono">{html.escape(ui_url)}</span></p>
        <p class="footer-line"><strong>实际输出目录</strong><br><span class="mono">{html.escape(effective_output or "-")}</span></p>
      </div>
    </aside>"""


def render_topbar() -> str:
    return """
      <section class="topbar">
        <div>
          <h2 data-current-title>总览</h2>
        </div>
      </section>"""


def render_runtime_checks_panel(project: Path, doctor: dict, ui_state: dict) -> str:
    warnings = doctor.get("warnings", [])
    maintenance = ui_state.get("maintenance_status", {}) or {}
    maintenance_path = str(maintenance.get("path", "") or "")
    maintenance_link = _render_file_link(Path(maintenance_path), label="打开维护报告", new_tab=True) if maintenance_path else ""
    environment_status = "存在告警" if warnings else "正常"
    environment_detail = "；".join(str(item) for item in warnings) if warnings else "当前 doctor 无告警。"
    maintenance_overall = str(maintenance.get("overall", "unknown") or "unknown")
    maintenance_summary = {
        "ok": "最近 maintenance-check 通过。",
        "failed": "最近 maintenance-check 未通过，需要重新检查。",
        "unknown": "尚未找到 maintenance-check 报告。",
    }.get(maintenance_overall, "尚未找到 maintenance-check 报告。")
    code_check_lines = []
    if maintenance.get("doctor"):
        code_check_lines.append(f"doctor={maintenance['doctor']}")
    if maintenance.get("pytest"):
        code_check_lines.append(f"pytest={maintenance['pytest']}")
    if maintenance.get("harness"):
        code_check_lines.append(f"harness={maintenance['harness']}")
    if maintenance.get("entropy"):
        code_check_lines.append(f"entropy={maintenance['entropy']}")
    code_check_text = " / ".join(code_check_lines) if code_check_lines else "未记录"
    return f"""
      <section class="panel">
        <div class="panel-header">
          <div><h3>运行状态检查</h3></div>
        </div>
        <div class="panel-body">
          <div class="status-check-list">
            <div class="status-check-item {'error' if warnings else 'ok'}">
              <strong>环境检查</strong>
              <p>{html.escape(environment_status)}</p>
              <p>{html.escape(environment_detail)}</p>
            </div>
            <div class="status-check-item {'ok' if maintenance_overall == 'ok' else ''}">
              <strong>代码维护检查</strong>
              <p>{html.escape(maintenance_summary)}</p>
              <p>{html.escape(code_check_text)}</p>
              {f'<div class="status-check-link">{maintenance_link}</div>' if maintenance_link else ''}
            </div>
          </div>
        </div>
      </section>"""


def render_overview_view(
    project: Path,
    runtime: dict,
    analysis: dict,
    paths: dict,
    doctor: dict,
    status: dict[str, str],
    manual_requests: list[ManualRequestStatus],
    ui_state: dict,
) -> str:
    counts = ui_state.get("counts", {})
    provider_status = doctor.get("provider_status", {})
    current_python = html.escape(str(doctor.get("current_python", "") or ""))
    provider = html.escape(_display_provider_label(str(analysis.get("provider", "codex_local") or "codex_local")))
    model_name = _current_model_label(analysis)
    token_usage = html.escape(str(ui_state.get("token_usage", "未记录") or "未记录"))
    return f"""
      <section class="view active" data-view="overview">
        {_render_run_stats_card(status, counts)}
        {render_runtime_checks_panel(project, doctor, ui_state)}
        <div class="section-grid fixed-layout">
          <div class="card span-12">
            <h4>运行环境</h4>
            <div class="info-lines">
              <div class="info-line"><strong>Python</strong><span class="mono">{current_python}</span></div>
              <div class="info-line"><strong>环境自检</strong><span class="mono">./scripts/run_science_monitor.sh doctor</span></div>
              <div class="info-line"><strong>维护入口</strong><span class="mono">maintenance-check / harness-check</span></div>
            </div>
          </div>
          <div class="card span-12">
            <h4>LLM 状态</h4>
            <div class="info-lines">
              <div class="info-line"><strong>当前 provider</strong><span>{provider}</span></div>
              <div class="info-line"><strong>当前模型</strong><span>{model_name}</span></div>
              <div class="info-line"><strong>最近 token 记录</strong><span>{token_usage}</span></div>
              <div class="info-line"><strong>人工中转</strong><span>pending {int(provider_status.get("chatgpt_web_manual_pending", 0) or 0)} / ready {int(provider_status.get("chatgpt_web_manual_ready", 0) or 0)}</span></div>
            </div>
          </div>
        </div>
      </section>"""


def render_weekly_report_view(project: Path, runtime: dict, status: dict[str, str], ui_state: dict) -> str:
    latest_report = _resolve_latest_result_path(ui_state.get("latest_report", ""), status, status_title_prefixes=("周报生成完成",))
    journal_groups = ui_state.get("journal_groups", [])
    journal_items = "".join(
        f'<div class="text-group"><strong>{html.escape(str(group.get("label", "")))}</strong><div class="plain-text-list">{html.escape(chr(10).join(group.get("items", [])))}</div></div>'
        for group in journal_groups
    ) or '<p class="muted">当前没有期刊配置。</p>'
    return f"""
      <section class="view" data-view="weekly-report">
        <div class="section-grid fixed-layout equal-height weekly-report-grid">
          <form class="card span-9 card-fill weekly-report-form-card" method="post" action="/run-report">
            <h4>周报生成参数</h4>
            <div class="form-stack">
              <div class="row">
                {_date_input("report_date", date.today().isoformat(), "报告日期", "这是本次周报的目标日期。程序会把它当作统计锚点，决定向前回看哪些文献；改到更早的日期，生成的周报会回到更早的观察窗口。")}
                {_number("report_window_days_run", runtime.get("cli_defaults", {}).get("report_window_days", 7), "统计窗口（天）", "这个参数定义周报统计多少天内的文献。它只在“不先更新再生成”时生效；数字越大，纳入周报的历史文献越多，周报覆盖面更宽。")}
              </div>
              <div class="checks">
                {_checkbox("run_update_before_report", True, "先更新再生成", "这个开关决定周报是否先执行抓取流程。勾选后，程序会先更新数据库中的最新文献再生成周报；取消勾选则只基于当前数据库已有内容重建周报。")}
                {_checkbox("report_update_hydrate", runtime.get("cli_defaults", {}).get("update_hydrate", True), "抓取时自动补摘要", "这个开关控制抓取阶段是否主动补全文摘要。勾选后，程序会在元数据缺摘要时尝试用 DOI 或网页补全摘要；这样总结质量通常更好，但抓取会更慢。")}
              </div>
              <div class="row">
                {_number("report_update_days_back", runtime.get("cli_defaults", {}).get("daily_days_back", 7), "更新回看天数", "这个参数决定抓取流程向前回看多少天内的新文献。值越大，漏抓风险越低，但抓取范围更广、耗时也更长。")}
                {_number("report_max_per_source_run", runtime.get("cli_defaults", {}).get("daily_max_per_source", 20), "每源抓取上限", "这个参数限制每个期刊源单次最多抓取多少条候选。值越大，覆盖更全；值越小，运行更快，但可能漏掉高峰期的新文献。")}
              </div>
              {_text("report_source_ids", "", "限定期刊 source_ids（可选，逗号分隔）", "这个字段用于临时缩小本次周报的抓取范围。只在“先更新再生成”时生效；填写后，程序只处理指定期刊源，适合做局部测试或专题监测。")}
              <div class="actions">
                <button type="submit" class="secondary" title="根据当前参数执行周报流程。">开始生成周报</button>
              </div>
            </div>
          </form>
          <div class="card span-3 card-fill weekly-report-journals-card">
            <h4>当前监测期刊</h4>
            <div class="scroll-fill">{journal_items}</div>
          </div>
          {_render_latest_result_card(project, "周报最新结果", latest_report, empty_text="当前没有周报结果。")}
        </div>
      </section>"""


def render_deep_read_view(project: Path, runtime: dict, paths: dict, status: dict[str, str], ui_state: dict) -> str:
    latest_deep_read = _resolve_latest_result_path(
        ui_state.get("latest_deep_read", ""),
        status,
        status_title_prefixes=("深度解读完成", "人工中转深度解读已生成"),
    )
    local_hint = (
        "当前本机私有覆盖已启用，实际输出会优先使用 local.paths.json。"
        if paths.get("local_output_root")
        else "如需写入私人 Obsidian vault，请在本机私有输出目录中填写路径；该文件不会上传 GitHub。"
    )
    return f"""
      <section class="view" data-view="deep-read">
        <div class="section-grid fixed-layout">
          <form class="card span-12" method="post" action="/run-deep-read" enctype="multipart/form-data">
            <h4>深度解读任务面板</h4>
            <div class="form-stack">
              {_file_input("deep_read_pdf", "deep_read_pdf", "拖拽或选择 PDF", "这是深度解读最可靠的输入材料。上传 PDF 后，程序会优先基于全文组织解读；如果不提供，系统只能做简单网页定位，拿不到全文时会要求补 PDF。")}
              {_text("deep_read_pdf_path", "", "或填写本地 PDF 路径（可选）", "这个字段和上传 PDF 作用相同，适用于文件已在本机磁盘的情况。填写后程序会直接读取该路径，避免重复上传。")}
              <div class="row">
                {_text("deep_read_doi", "", "DOI（可选）", "DOI 是论文的稳定标识。程序会把它作为定位线索，用于网页搜索和元数据补全；但仅有 DOI 不能保证一定拿到全文。")}
                {_text("deep_read_title", "", "论文题目（可选）", "题目用于辅助定位论文和标注输出结果。在没有 DOI 时尤其重要；题目越准确，搜索和人工中转的命中率越高。")}
              </div>
              <div class="row">
                {_text("deep_read_journal", "", "期刊名（可选）", "期刊名用于缩小定位范围，并改善输出标题和引用信息。填写缩写或正式刊名都可以。")}
                {_text("deep_read_url", "", "落地页 URL（可选）", "如果你已经知道论文网页地址，填这里可以直接减少搜索步骤。程序会优先使用这个地址做定位。")}
              </div>
              {_number("deep_read_pdf_page_limit", runtime.get("deep_read", {}).get("pdf_page_limit", 40), "PDF 最多读取页数（0 = 全部）", "这个参数控制本次深度解读最多读取多少页 PDF。0 表示读完整篇；值越大，覆盖越完整，但全文抽取和后续分析更慢。")}
              <div class="actions">
                <button type="submit" title="按当前输入生成一篇深度解读。">开始深度解读</button>
              </div>
            </div>
          </form>
          <div class="card span-12">
            <h4>深度解读文章数量统计</h4>
            <div class="info-lines">
              <div class="info-line"><strong>已生成深度解读</strong><span>{int(ui_state.get("counts", {}).get("deep_reads", 0) or 0)} 篇</span></div>
              <div class="info-line"><strong>当前 PDF 页数限制</strong><span>{int(runtime.get("deep_read", {}).get("pdf_page_limit", 40) or 40)}</span></div>
              <div class="info-line"><strong>路径说明</strong><span>{html.escape(local_hint)}</span></div>
            </div>
          </div>
          {_render_latest_result_card(project, "最新深度解读报告", latest_deep_read, empty_text="当前没有深度解读结果。")}
        </div>
      </section>"""


def render_manual_view(project: Path, status: dict[str, str], manual_requests: list[ManualRequestStatus], ui_state: dict) -> str:
    prompt_path = _manual_prompt_path_from_status(status)
    prompt_preview = _load_text_preview(prompt_path)
    latest_manual_result = _latest_manual_result_path(ui_state, status)
    request_items = "".join(
        f"<li>{html.escape(item.display_label)}</li>" for item in manual_requests[:3]
    ) or "<li>当前没有人工中转活动。</li>"
    prompt_actions = _render_prompt_actions(prompt_path)
    return f"""
      <section class="view" data-view="manual-llm">
        <div class="section-grid fixed-layout">
          <div class="card span-12">
            <h4>人工中转最近活动</h4>
            <ul class="activity-list compact">{request_items}</ul>
          </div>
          <form class="card span-12" method="post" action="/manual-llm-create">
            <h4>请求生成面板</h4>
            <div class="form-stack">
              {_select("manual_create_kind", "article_summary", [("article_summary", "文章总结"), ("deep_read", "深度解读")], "任务类型", "这个字段决定程序要生成哪种人工中转请求。选“文章总结”会生成轻量分析 prompt；选“深度解读”会生成更长、更强调方法和证据的 prompt。")}
              <div class="row">
                {_text("manual_create_title", "", "论文题目（可选）", "题目是人工中转请求最直接的定位信息。程序会用它生成 `prompt.md`、请求标签和结果标题；题目越准确，网页端定位越稳定。")}
                {_text("manual_create_doi", "", "DOI（可选）", "DOI 会写进请求文件，供网页端模型直接检索论文。提供 DOI 通常能降低定位歧义。")}
              </div>
              <div class="row">
                {_text("manual_create_journal", "", "期刊缩写 / 名称（可选）", "期刊信息用于进一步限定请求上下文，减少重名论文或同题材料带来的干扰。")}
                {_text("manual_create_url", "", "网页 URL（可选）", "如果你已经知道落地页，把它写进请求能减少网页端模型自行搜索的工作量。")}
              </div>
              <div class="actions">
                <button type="submit" title="生成 prompt.md、request.md 和 metadata.json。">生成请求文件</button>
                {prompt_actions}
              </div>
            </div>
            {_render_prompt_preview_card(prompt_path, prompt_preview)}
          </form>
          <form class="card span-12" method="post" action="/manual-llm-import-upload" enctype="multipart/form-data">
            <h4>ChatGPT 响应文件解读面板</h4>
            <div class="form-stack">
              {_file_input("manual_response_upload", "manual_response_upload", "拖拽或上传 ChatGPT 返回的 JSON 文件", "这里接收网页端生成的 JSON 响应文件。程序会解析其中的结构化结果，自动继续完成文章总结或深度解读。", accept=".json,application/json")}
              {_text("manual_request_id", "", "request_id（仅在自动识别失败时填写）", "这个字段是人工中转任务的内部关联键。正常情况下程序会自动识别；只有文件名或 JSON 内容无法匹配时，才需要手动填写。")}
              <div class="actions">
                <button type="submit" title="导入 JSON 并自动继续生成对应结果。">解读响应文件</button>
              </div>
            </div>
          </form>
          {_render_latest_result_card(project, "通过响应文件生成的最新结果", latest_manual_result, empty_text="当前没有人工中转生成结果。")}
        </div>
      </section>"""


def render_settings_view(runtime: dict, analysis: dict, paths: dict) -> str:
    provider = str(analysis.get("provider", "codex_local") or "codex_local")
    if provider not in {"codex_local", "openai_api", "openrouter_api"}:
        provider = "codex_local"
    return f"""
      <section class="view" data-view="settings">
        <form method="post" action="/save-config">
          <div class="section-grid fixed-layout">
            {_render_llm_settings_card(analysis, provider, span="span-12")}
            {_render_paths_settings_card(paths, span="span-12")}
          </div>
          <div class="settings-actions">
            <button type="submit">保存配置并同步 PROJECT_CONFIG.md</button>
            <button type="submit" formaction="/shutdown-ui" formmethod="post">关闭面板服务</button>
          </div>
        </form>
      </section>"""


def _render_llm_settings_card(analysis: dict, provider: str, *, span: str = "span-8") -> str:
    codex_class = "provider-only active" if provider == "codex_local" else "provider-only"
    openai_class = "provider-only active" if provider == "openai_api" else "provider-only"
    openrouter_class = "provider-only active" if provider == "openrouter_api" else "provider-only"
    return f"""
            <div class="card {span}">
              <h4>分析后端与服务</h4>
              <div class="form-stack">
                {_select("provider", provider, automatic_provider_choices(), "分析后端", "这是项目默认使用的自动分析后端。它决定单篇总结、周报和深度解读优先调用哪类模型服务；切换后会改变程序走本地 Codex、OpenAI API 还是 OpenRouter API。", extra_attrs='data-provider-select')}
                <div class="{codex_class}" data-provider-only="codex_local">
                  <div class="form-stack">
                    {_text("codex_model", analysis.get("codex_local", {}).get("model", ""), "Codex 模型名（留空则使用本机默认）", "这个字段指定本地 Codex 调用的模型名。留空时程序使用本机默认模型；填具体模型名时，会把后续自动分析固定到该模型。")}
                    {_text("codex_executable", analysis.get("codex_local", {}).get("executable", ""), "codex 可执行文件路径（可留空）", "这个字段指定 `codex` 可执行文件位置。正常情况下程序会自动发现；只有自动发现失败时，才需要手动填路径。")}
                    <div class="row">
                      {_select("codex_sandbox", analysis.get("codex_local", {}).get("sandbox", "read-only"), [("read-only", "read-only"), ("workspace-write", "workspace-write"), ("danger-full-access", "danger-full-access")], "Codex sandbox", "这个字段控制 `codex exec` 的文件系统权限。权限越高，可做的事越多，但风险也越大；默认建议保持 `read-only`。")}
                      {_number("codex_timeout_seconds", analysis.get("codex_local", {}).get("timeout_seconds", 300), "Codex 超时秒数", "这个字段控制单次本地模型分析最多等待多久。值越大，长任务更容易完成；值越小，失败会更快暴露。")}
                    </div>
                    <div class="row">
                      {_select("article_summaries_reasoning_effort", analysis.get("article_summaries", {}).get("reasoning_effort", "medium"), [("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "xhigh")], "单篇总结推理强度", "这个字段控制单篇总结调用本地 Codex 时的推理强度。强度越高，理解更深，但 token 和时间消耗更高。")}
                      {_select("report_reasoning_effort", analysis.get("report", {}).get("reasoning_effort", "medium"), [("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "xhigh")], "周报推理强度", "这个字段控制周报生成时的推理强度。提高强度会增加综合归纳能力，但也会增加耗时和消耗。")}
                    </div>
                    {_select("deep_reads_reasoning_effort", analysis.get("deep_reads", {}).get("reasoning_effort", "high"), [("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "xhigh")], "深度解读推理强度", "这个字段控制深度解读调用本地 Codex 时的分析深度。提高强度通常能提升结构化判断，但会明显增加时间和 token 消耗。")}
                  </div>
                </div>
                <div class="{openai_class}" data-provider-only="openai_api">
                  <div class="form-stack">
                    {_text("openai_model", analysis.get("openai_api", {}).get("model", "gpt-5-mini"), "OpenAI 模型名", "这个字段指定通过 OpenAI 接口调用的模型。改成更强模型通常会提升质量，但也会提高成本。")}
                    {_text("openai_base_url", analysis.get("openai_api", {}).get("base_url", "https://api.openai.com/v1/responses"), "OpenAI base_url", "这个字段定义 OpenAI 兼容接口地址。默认是官方 Responses API；如果你使用代理或兼容层，需要改成对应服务地址。")}
                    {_text("openai_api_key_env", analysis.get("openai_api", {}).get("api_key_env", "SCIENCEMONITOR_OPENAI_API_KEY"), "API key 环境变量名", "这个字段告诉程序去哪个环境变量里取 API key。优先使用环境变量，可以避免把密钥直接写进项目配置。")}
                    {_text("openai_api_key", analysis.get("openai_api", {}).get("api_key", ""), "直接写入配置的 API key（不推荐）", "这个字段允许直接把 key 写进本机配置。只有环境变量不可用时才建议使用，因为它的泄露风险更高。")}
                    {_number("openai_timeout_seconds", analysis.get("openai_api", {}).get("timeout_seconds", 120), "API 超时秒数", "这个字段控制单次 OpenAI API 请求允许等待多久。值越大，长任务成功率更高；值越小，失败暴露更快。")}
                  </div>
                </div>
                <div class="{openrouter_class}" data-provider-only="openrouter_api">
                  <div class="form-stack">
                    {_text("openrouter_model", analysis.get("openrouter_api", {}).get("model", "openai/gpt-5-mini"), "OpenRouter 模型名", "这个字段指定通过 OpenRouter 路由的模型标识，例如 `openai/gpt-5-mini`。切换后会改变后续请求实际命中的上游模型。")}
                    {_text("openrouter_base_url", analysis.get("openrouter_api", {}).get("base_url", "https://openrouter.ai/api/v1/chat/completions"), "OpenRouter base_url", "这个字段定义 OpenRouter 兼容接口地址。默认使用官方地址；如果你走自建代理，需要改成代理地址。")}
                    {_text("openrouter_api_key_env", analysis.get("openrouter_api", {}).get("api_key_env", "SCIENCEMONITOR_OPENROUTER_API_KEY"), "API key 环境变量名", "这个字段定义程序从哪个环境变量读取 OpenRouter key。优先使用环境变量，便于公开仓库和本机私有密钥分离。")}
                    {_text("openrouter_api_key", analysis.get("openrouter_api", {}).get("api_key", ""), "直接写入配置的 API key（不推荐）", "这个字段允许把 OpenRouter key 直接写进本机配置。只有环境变量不方便时才建议使用。")}
                    <div class="row">
                      {_text("openrouter_site_url", analysis.get("openrouter_api", {}).get("site_url", ""), "HTTP-Referer（可选）", "这个字段会写进请求头的站点来源信息。有些路由会用它做统计、鉴权辅助或配额识别。")}
                      {_text("openrouter_app_name", analysis.get("openrouter_api", {}).get("app_name", "ScienceMonitor"), "X-Title（可选）", "这个字段会写进请求头的应用名称。它主要用于平台侧识别你的应用来源，不影响分析内容本身。")}
                    </div>
                    {_number("openrouter_timeout_seconds", analysis.get("openrouter_api", {}).get("timeout_seconds", 120), "API 超时秒数", "这个字段控制单次 OpenRouter 请求允许等待多久。值越大，更适合长响应；值越小，更适合快速失败和排查。")}
                  </div>
                </div>
              </div>
            </div>"""


def _render_paths_settings_card(paths: dict, *, span: str = "span-4") -> str:
    return f"""
            <div class="card {span}">
              <h4>路径与输出</h4>
              <div class="form-stack">
                {_text("local_output_root", paths.get("local_output_root", ""), "真实输出目录（本机私有）", "这个字段定义你当前这台机器真正写出报告的目录。程序会把它写入 `config/local.paths.json`；修改后会直接影响本机报告落点，但不会污染公开仓库配置。")}
                <p class="muted">实际输出目录：<code>{html.escape(paths.get("effective_output_root", paths.get("output_root", "")))}</code></p>
                <p class="muted">私有配置文件位置：<code>{html.escape(paths.get("local_paths_config", ""))}</code></p>
              </div>
            </div>"""


def _render_run_stats_card(status: dict[str, str], counts: dict) -> str:
    error_html = ""
    if status.get("kind") == "error":
        error_html = (
            '<div class="inline-alert error">'
            f'<strong>{html.escape(status.get("title", "运行报错"))}</strong>'
            f'<p>{html.escape(status.get("message", ""))}</p>'
            "</div>"
        )
    return f"""
      <section class="card run-stats-card">
        <h4>运行统计</h4>
        {error_html}
        <div class="stats-strip">
          <div class="stat-chip"><strong>已总结文章数</strong><span>{int(counts.get("article_summaries", 0) or 0)}</span></div>
          <div class="stat-chip"><strong>已深度解读数</strong><span>{int(counts.get("deep_reads", 0) or 0)}</span></div>
          <div class="stat-chip"><strong>已生成周报数</strong><span>{int(counts.get("reports", 0) or 0)}</span></div>
          <div class="stat-chip"><strong>人工中转文件数</strong><span>{int(counts.get("manual_files", 0) or 0)}</span></div>
        </div>
      </section>"""


def _render_latest_result_card(project: Path, title: str, path_value: str, empty_text: str) -> str:
    content = (
        _render_file_summary(project, Path(path_value))
        if path_value
        else f'<p class="muted">{html.escape(empty_text)}</p>'
    )
    return f"""
          <div class="card span-12">
            <h4>{html.escape(title)}</h4>
            {content}
          </div>"""


def _render_prompt_preview_card(prompt_path: str, preview_text: str) -> str:
    if not prompt_path:
        return ""
    preview_html = html.escape(preview_text) if preview_text else "未能读取 prompt 内容。"
    return f"""
      <div class="subpanel">
        <pre class="file-preview">{preview_html}</pre>
      </div>"""


def _render_status_entry(status: dict[str, str]) -> str:
    if not status.get("kind"):
        return '<div class="log-entry"><strong>最近操作</strong><p>本次加载没有新的操作结果。</p></div>'
    banner_class = "ok" if status.get("kind") == "ok" else "error"
    title = html.escape(status.get("title", ""))
    message = html.escape(status.get("message", ""))
    details = [f"<p>{message}</p>"] if message else []
    primary = status.get("path", "").strip()
    secondary = status.get("extra_path", "").strip()
    if primary:
        details.append(f'<p><span class="mono">输出：</span>{_render_file_link(Path(primary), label=Path(primary).name)}</p>')
    if secondary:
        details.append(f'<p><span class="mono">资源：</span>{_render_file_link(Path(secondary), label=Path(secondary).name)}</p>')
    return f'<div class="log-entry {banner_class}"><strong>{title}</strong>{"".join(details)}</div>'


def _render_prompt_actions(prompt_path: str) -> str:
    if not prompt_path:
        return ""
    path = Path(prompt_path)
    download_link = _render_file_link(path, label="下载 prompt.md", download=True)
    open_link = _render_file_link(path, label="打开 prompt.md", new_tab=True)
    return f"{download_link}{open_link}"


def _current_ui_url(project: Path) -> str:
    path = config_ui_state_path(project)
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("url", "") or "")


def _current_release_version(project: Path) -> str:
    changelog_path = project / "CHANGELOG.md"
    if not changelog_path.exists():
        return "dev"
    pattern = re.compile(r"^## \[(v[^\]]+)\]")
    for line in changelog_path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match and match.group(1).lower() != "unreleased":
            return match.group(1)
    return "dev"


def _current_model_label(analysis: dict) -> str:
    provider = str(analysis.get("provider", "codex_local") or "codex_local")
    if provider == "codex_local":
        return str(analysis.get("codex_local", {}).get("model", "") or "本机默认")
    if provider == "openai_api":
        return str(analysis.get("openai_api", {}).get("model", "") or "未配置")
    if provider == "openrouter_api":
        return str(analysis.get("openrouter_api", {}).get("model", "") or "未配置")
    return "ChatGPT 网页人工中转"


def _resolve_latest_result_path(latest_path: str, status: dict[str, str], status_title_prefixes: tuple[str, ...]) -> str:
    if status.get("kind") == "ok" and any(status.get("title", "").startswith(prefix) for prefix in status_title_prefixes):
        return status.get("path", "")
    return latest_path


def _latest_manual_result_path(ui_state: dict, status: dict[str, str]) -> str:
    if status.get("kind") == "ok" and status.get("title", "").startswith(("人工中转文章总结已生成", "人工中转深度解读已生成")):
        return status.get("path", "")
    candidates = [ui_state.get("latest_article_summary", ""), ui_state.get("latest_deep_read", "")]
    existing = [Path(item) for item in candidates if item and Path(item).exists()]
    if not existing:
        return ""
    latest = max(existing, key=lambda item: item.stat().st_mtime)
    return str(latest)


def _manual_prompt_path_from_status(status: dict[str, str]) -> str:
    if status.get("kind") == "ok" and status.get("title", "") == "人工中转请求已生成":
        return status.get("path", "")
    return ""


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


def _render_file_link(path: Path, *, label: str, download: bool = False, new_tab: bool = False) -> str:
    attrs = ['class="file-link"', f'href="{html.escape(_local_file_href(path))}"']
    if download:
        attrs.append("download")
        attrs.append('draggable="true"')
    if new_tab:
        attrs.append('target="_blank"')
        attrs.append('rel="noreferrer"')
    return f"<a {' '.join(attrs)}>{html.escape(label)}</a>"


def _local_file_href(path: Path) -> str:
    return "/local-file?" + urlencode({"path": str(path)})


def _load_text_preview(path_value: str, limit: int = 4000) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n..."


def _checkbox(name: str, checked: bool, label: str, help_text: str = "") -> str:
    help_html = _help_anchor(help_text) if help_text else ""
    return (
        f'<div class="field-shell field-shell-check">'
        f'<label class="checkbox-label">'
        f'<input type="checkbox" name="{html.escape(name)}" {"checked" if checked else ""}> '
        f'<span>{html.escape(label)}</span>{help_html}'
        f"</label>"
        f"</div>"
    )


def _text(name: str, value: str, label: str, help_text: str = "") -> str:
    return (
        f'<div class="field-shell">'
        f'{_label_html(name, label, help_text)}'
        f'<input type="text" id="{html.escape(name)}" name="{html.escape(name)}" value="{html.escape(str(value or ""))}">'
        f"</div>"
    )


def _number(name: str, value: int, label: str, help_text: str = "") -> str:
    return (
        f'<div class="field-shell">'
        f'{_label_html(name, label, help_text)}'
        f'<input type="number" id="{html.escape(name)}" name="{html.escape(name)}" value="{int(value)}">'
        f"</div>"
    )


def _date_input(name: str, value: str, label: str, help_text: str = "") -> str:
    return (
        f'<div class="field-shell">'
        f'{_label_html(name, label, help_text)}'
        f'<input type="date" id="{html.escape(name)}" name="{html.escape(name)}" value="{html.escape(str(value or ""))}">'
        f"</div>"
    )


def _file_input(name: str, input_id: str, label: str, help_text: str = "", *, accept: str = "") -> str:
    accept_attr = f' accept="{html.escape(accept)}"' if accept else ""
    return (
        f'<div class="field-shell field-shell-file">'
        f'{_label_html(input_id, label, help_text)}'
        f'<input type="file" id="{html.escape(input_id)}" name="{html.escape(name)}"{accept_attr}>'
        f"</div>"
    )


def _select(name: str, value: str, options: list[tuple[str, str]], label: str, help_text: str = "", extra_attrs: str = "") -> str:
    option_html = "".join(
        f'<option value="{html.escape(option_value)}" {"selected" if option_value == value else ""}>{html.escape(option_label)}</option>'
        for option_value, option_label in options
    )
    attrs = f" {extra_attrs.strip()}" if extra_attrs.strip() else ""
    return (
        f'<div class="field-shell">'
        f'{_label_html(name, label, help_text)}'
        f'<select id="{html.escape(name)}" name="{html.escape(name)}"{attrs}>{option_html}</select>'
        f"</div>"
    )


def _label_html(name: str, label: str, help_text: str = "") -> str:
    return (
        f'<div class="field-label">'
        f'<label for="{html.escape(name)}">{html.escape(label)}</label>'
        f'{_help_anchor(help_text) if help_text else ""}'
        f"</div>"
    )


def _help_anchor(help_text: str) -> str:
    return (
        f'<span class="help-anchor" tabindex="0" data-tooltip="{html.escape(help_text)}" '
        f'aria-label="{html.escape(help_text)}">?</span>'
    )


def _display_provider_label(provider: str) -> str:
    return ALL_PROVIDER_LABELS.get(provider, provider)
