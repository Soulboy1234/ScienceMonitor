from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_CONFIG_JSON_BLOCK_RE = re.compile(r"(?ms)^## Sync: (config/[^\n]+)\n```json\n(.*?)\n```")


def find_project_config_json_blocks(text: str) -> list[tuple[str, str]]:
    return PROJECT_CONFIG_JSON_BLOCK_RE.findall(text)


def parse_project_config_json_blocks(text: str, *, sync_targets: tuple[str, ...]) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for relative_path, block in find_project_config_json_blocks(text):
        if relative_path not in sync_targets:
            continue
        payloads[relative_path] = json.loads(block)
    return payloads


def build_project_config_markdown(
    *,
    project: Path,
    runtime: dict,
    analysis: dict,
    paths: dict,
    research_preferences: dict,
) -> str:
    lines: list[str] = []
    lines.extend(_build_intro_section(project))
    lines.extend(_build_runtime_sync_section(runtime))
    lines.extend(_build_analysis_sync_section(analysis))
    lines.extend(_build_paths_sync_section(paths))
    lines.extend(_build_recommended_profiles_section())
    lines.extend(_build_strategy_section())
    lines.extend(_build_other_files_section())
    lines.extend(_build_research_preferences_section(research_preferences))
    lines.extend(_build_usage_section())
    return "\n".join(lines)


def _build_intro_section(project: Path) -> list[str]:
    return [
        "# Project Config",
        "",
        "这个文件是项目的人类可读控制面板，也是推荐的日常配置入口。",
        "",
        "程序启动时会读取这里标记为 `## Sync:` 的配置段，并同步到对应的 `config/*.json` 文件。",
        "建议把这里当成日常调整入口；如果你直接改了 `config/*.json`，后续再次启动时这里的内容会覆盖它们。",
        "如果你改坏了同步区的格式，程序会在启动时直接报错，并指出具体的位置。",
        "",
        "## 当前环境与说明",
        "",
        f"- 项目根目录：`{project}`",
        f"- 本地 Python：`{project / '.venv' / 'bin' / 'python'}`",
        "- 默认入口脚本：`./scripts/run_science_monitor.sh`",
        "- 本地配置界面：`./scripts/run_science_monitor.sh config-ui`",
        "- PDF 工具：`pdftotext`、`pdfinfo`、`pdftoppm` 由项目环境优先提供",
        "- 当前 LLM provider 由下方 `config/analysis.json` 同步块控制",
        "- 调研默认时间范围、每个来源抓取上限等由下方 `config/runtime.json` 同步块控制",
        "- 输出目录由下方 `config/paths.json` 同步块控制",
        "",
        "## 你通常会调的设置",
        "",
        "- 切换 LLM 模式：修改 `provider` 为 `codex_local`、`openai_api` 或 `chatgpt_web_manual`",
        "- 切换模型：修改 `codex_local.model` 或 `openai_api.model`；`chatgpt_web_manual` 不需要配置 API key 或模型名",
        "- 调整 Codex 推理强度：修改 `article_summaries.reasoning_effort`、`report.reasoning_effort`、`deep_reads.reasoning_effort`",
        "- 配置 API key：优先使用环境变量；也可写入 `openai_api.api_key`",
        "- 调整单篇总结走 LLM 的数量：修改 `article_summaries.max_items_per_run`",
        "- 调整周报送入 LLM 的文章数：修改 `report.max_papers_in_prompt`",
        "- 调整默认调研窗口：修改 `cli_defaults.*_days_back` 或 `cli_defaults.*_window_days`",
        "- 调整每个期刊的抓取上限：修改 `cli_defaults.*_max_per_source`",
        "- 切换输出 Obsidian 仓库：修改 `config/paths.json` 中的 `output_root`",
        "",
        "## 当前推荐理解",
        "",
        "- 如果 `codex_local.model` 留空，项目不会显式指定模型，而是交给本机 `codex` 自己选择默认模型。",
        "- `reasoning_effort` 只对 `codex_local` 生效；单篇总结和周报默认 `medium`，深度解读默认 `high`。",
        "- 如果你想在不同电脑上得到更稳定一致的结果，建议直接把 `codex_local.model` 写死。",
        "- 如果你更关心质量，建议优先提高 `article_summaries.max_items_per_run`，让更多单篇总结直接走 LLM。",
        "- 如果你更关心速度或额度，建议先保留 `report.enabled=true`，并限制 `article_summaries.max_items_per_run`。",
        "",
    ]


def _build_runtime_sync_section(runtime: dict) -> list[str]:
    return [
        "## Sync: config/runtime.json",
        "```json",
        json.dumps(runtime, ensure_ascii=False, indent=2),
        "```",
        "",
        "说明：",
        "- `features.weekly_report_enabled`：是否真正生成周报文件",
        "- `daily_days_back`：`daily` 命令默认回看多少天",
        "- `update_days_back`：`update` 命令默认抓取多少天",
        "- `report_window_days`：`report` 命令默认汇总多少天",
        "- `summaries_window_days`：`summaries` 命令默认写多少天的单篇总结",
        "- `audit_window_days`：`audit` 命令默认核查多少天",
        "- `*_max_per_source`：每个期刊/来源一次最多请求多少条",
        "- `update_hydrate`：抓取时是否默认补抓 DOI 落地页摘要",
        "- `deep_read.search_full_text_when_pdf_missing`：没给 PDF 时是否自动按 DOI/题目找全文",
        "- `deep_read.pdf_page_limit`：深度解读最多读取 PDF 的前多少页",
        "",
    ]


def _build_analysis_sync_section(analysis: dict) -> list[str]:
    return [
        "## Sync: config/analysis.json",
        "```json",
        json.dumps(analysis, ensure_ascii=False, indent=2),
        "```",
        "",
        "说明：",
        "- `provider`：当前分析后端，可选 `codex_local`、`openai_api`、`chatgpt_web_manual`",
        "- `article_summaries.enabled`：是否启用单篇总结的 LLM 分析",
        "- `article_summaries.max_items_per_run`：每次运行最多多少篇走 LLM；`0` 表示不设上限",
        "- `article_summaries.reasoning_effort`：单篇总结使用 codex_local 时的推理强度",
        "- `report.enabled`：是否启用周报的 LLM 分析",
        "- `report.max_papers_in_prompt`：周报提示词最多放多少篇文章",
        "- `report.reasoning_effort`：周报使用 codex_local 时的推理强度",
        "- `deep_reads.enabled`：是否启用深度解读功能",
        "- `deep_reads.max_input_chars`：深度解读送入 LLM 的全文最大字符数",
        "- `deep_reads.reasoning_effort`：深度解读使用 codex_local 时的推理强度",
        "- `codex_local.executable`：手动指定 `codex` 可执行文件路径",
        "- `openai_api.api_key_env`：优先读取的 API key 环境变量名",
        "- `openai_api.base_url`：兼容接口地址，默认是 OpenAI Responses API",
        "- `chatgpt_web_manual`：人工中转模式。运行时会在 `data/chatgpt_web_manual/` 生成请求包，等待你在 ChatGPT 网页完成后导入响应",
        "",
    ]


def _build_paths_sync_section(paths: dict) -> list[str]:
    return [
        "## Sync: config/paths.json",
        "```json",
        json.dumps(paths, ensure_ascii=False, indent=2),
        "```",
        "",
        "说明：",
        "- `output_root`：最终输出目录。周报、单篇总结、深度解读、article_index、my_work 都会写到这里",
        "",
    ]


def _build_recommended_profiles_section() -> list[str]:
    return [
        "## 常见推荐配置档",
        "",
        "这些不是自动同步块，而是推荐的改法。你可以把下面的值手动复制到对应的 `## Sync:` JSON 配置块里。",
        "",
        "### 配置档 A：质量优先",
        "",
        "适合正式周报、完整单篇总结、深度阅读较多的阶段。",
        "",
        "- `provider`：`codex_local`",
        "- `article_summaries.max_items_per_run`：`0`",
        "- `report.max_papers_in_prompt`：`50` 或更高",
        "- `daily_days_back` / `report_window_days`：`7`",
        "- `update_max_per_source`：`50` 到 `100`",
        "",
        "### 配置档 B：速度优先",
        "",
        "适合平时快速扫读，先看趋势，再决定是否补跑全量 LLM。",
        "",
        "- `provider`：`codex_local`",
        "- `article_summaries.max_items_per_run`：`5` 到 `10`",
        "- `report.max_papers_in_prompt`：`20` 到 `30`",
        "- `daily_days_back` / `report_window_days`：`7`",
        "- `update_max_per_source`：`20` 到 `50`",
        "",
        "### 配置档 C：脱离 Codex 独立部署",
        "",
        "适合其他电脑没有本地 Codex，改为外部 API 运行。",
        "",
        "- `provider`：`openai_api`",
        "- `openai_api.api_key_env`：推荐保留为 `SCIENCEMONITOR_OPENAI_API_KEY`",
        "- `openai_api.model`：按你自己的接口能力设置",
        "- `codex_local.model` / `codex_local.executable`：可留空",
        "",
        "### 配置档 D：无 Codex 的独立运行",
        "",
        "适合没有本地 Codex、但希望继续生成高质量单篇总结和周报的环境。",
        "",
        "- `provider`：`openai_api`",
        "- `article_summaries.enabled`：`true`",
        "- `report.enabled`：`true`",
        "- `openai_api.api_key_env`：推荐保留为 `SCIENCEMONITOR_OPENAI_API_KEY`",
        "",
        "### 配置档 E：ChatGPT 网页人工中转",
        "",
        "适合减少本地 Codex 或 API 消耗，把高成本分析转到 ChatGPT 网页人工处理中转。",
        "",
        "- `provider`：`chatgpt_web_manual`",
        "- `article_summaries.enabled`：`true`",
        "- `report.enabled`：`true`",
        "- `deep_reads.enabled`：`true`",
        "- 运行后按提示处理 `data/chatgpt_web_manual/requests/` 下的请求包，再用 `manual-llm-import` 导入响应",
        "",
    ]


def _build_strategy_section() -> list[str]:
    return [
        "## 建议的模型策略",
        "",
        "- `codex_local.model` 留空：使用本机 Codex 默认模型，最省心，但不同机器上不一定完全一致。",
        "- `codex_local.model` 写死：结果更稳定，更适合长期运行和多机部署。",
        "- `openai_api.model`：适合需要跨机器一致、且明确控制外部接口模型的情况。",
        "- `chatgpt_web_manual`：适合把高消耗分析分流到 ChatGPT 网页人工处理中转，代价是需要人工导入响应，不能全自动跑完。",
        "",
    ]


def _build_other_files_section() -> list[str]:
    return [
        "## 其他可配置文件",
        "",
        "这些内容目前不建议直接塞进这个 Markdown 同步块里，因为体量较大、编辑风险也更高；请直接编辑对应文件：",
        "",
        "- `config/sources.json`：期刊监控列表、期刊层级、抓取模式、ISSN 等",
        "- `config/topics.json`：空间物理主题分类与关键词规则",
        "- `config/focus_tags.json`：标签体系、层级标签、同义词归一化",
        "- `config/research_preferences.json`：运行时落地文件，通常由上面的研究偏好同步段自动生成，不建议手改",
        "- `config/templates/article_summary_template.md`：单篇总结运行时模板",
        "- `config/templates/daily_report_template.md`：周报运行时模板",
        "- `config/templates/deep_reading_report_template.md`：深度解读运行时模板",
        "- `docs/workflow_specs/*.md`：风格参考、prompt 契约与标签参考",
        "",
    ]


def _build_research_preferences_section(research_preferences: dict) -> list[str]:
    return [
        "## Sync: config/research_preferences.json",
        "",
        "这里是研究偏好的日常编辑入口。程序启动时会把下面内容同步到 `config/research_preferences.json`，不需要直接改 JSON。",
        "",
        "### 当前研究重心",
        *[f"- {item}" for item in research_preferences.get("research_focus", [])],
        "",
        "### 特别提醒策略",
        *[f"- {item}" for item in research_preferences.get("priority_alerts", [])],
        "",
        "### 高优先级文章信号",
        *[f"- {item}" for item in research_preferences.get("priority_article_signals", [])],
        "",
        "### 监测范围",
        f"- 监测：{research_preferences.get('monitoring_scope', {}).get('monitoring_domain', 'space_physics')}",
        f"- 单篇总结：{research_preferences.get('monitoring_scope', {}).get('article_summary_domain', 'space_physics')}",
        f"- 周报：{research_preferences.get('monitoring_scope', {}).get('report_domain', 'space_physics')}",
        "",
        "### 深度解读范围",
        f"- 主领域：{research_preferences.get('deep_read_scope', {}).get('primary_domain', 'space_physics')}",
        f"- 允许相关学科：{'是' if research_preferences.get('deep_read_scope', {}).get('allow_related_disciplines', True) else '否'}",
        f"- 优先相关学科：{', '.join(research_preferences.get('deep_read_scope', {}).get('preferred_related_disciplines', [])) or '无'}",
        "",
    ]


def _build_usage_section() -> list[str]:
    return [
        "## 推荐操作方式",
        "",
        "1. 日常运行参数、路径、LLM 后端：优先改这个文件里的三个 `## Sync:` 配置块。",
        "2. 学科知识和产出风格：改 `config/*.json` 的学科配置文件、`config/templates/*.md` 与相关 workflow specs。",
        "3. 用户偏好与重点提醒：改这个文件里的 `## Sync: config/research_preferences.json` 段。",
        "",
    ]
