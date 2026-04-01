from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import SourceConfig, TopicProfile


@dataclass(frozen=True)
class UserPreferenceProfile:
    research_focus: list[str] = field(default_factory=list)
    priority_alerts: list[str] = field(default_factory=list)
    priority_themes: list[str] = field(default_factory=list)
    theme_keywords: dict[str, list[str]] = field(default_factory=dict)


DEFAULT_RUNTIME_CONFIG = {
    "features": {
        "weekly_report_enabled": True,
    },
    "cli_defaults": {
        "daily_days_back": 7,
        "daily_max_per_source": 20,
        "update_days_back": 7,
        "update_max_per_source": 20,
        "update_hydrate": True,
        "report_window_days": 7,
        "summaries_window_days": 7,
        "audit_window_days": 7,
        "audit_max_per_source": 100,
    },
    "deep_read": {
        "search_full_text_when_pdf_missing": True,
        "pdf_page_limit": 40,
    },
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_override_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _resolve_configured_path(base_root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base_root / candidate
    return candidate.resolve()


def path_config_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "paths.json"


def runtime_config_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "runtime.json"


def project_config_markdown_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "PROJECT_CONFIG.md"


def load_path_overrides(root: Path | None = None) -> dict:
    config_path = path_config_path(root)
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def load_runtime_config(root: Path | None = None) -> dict:
    config_path = runtime_config_path(root)
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(DEFAULT_RUNTIME_CONFIG, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return json.loads(json.dumps(DEFAULT_RUNTIME_CONFIG))
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    merged = json.loads(json.dumps(DEFAULT_RUNTIME_CONFIG))
    _deep_update_dict(merged, payload if isinstance(payload, dict) else {})
    return merged


def sync_configs_from_project_markdown(root: Path | None = None) -> list[Path]:
    project = root or project_root()
    markdown_path = project_config_markdown_path(project)
    if not markdown_path.exists():
        write_project_config_markdown(project)
        return []

    text = markdown_path.read_text(encoding="utf-8")
    matches = re.findall(r"(?ms)^## Sync: (config/[^\n]+)\n```json\n(.*?)\n```", text)
    updated: list[Path] = []
    for relative_path, block in matches:
        if relative_path not in {"config/runtime.json", "config/analysis.json", "config/paths.json"}:
            continue
        try:
            payload = json.loads(block)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{markdown_path} 中的 {relative_path} JSON 配置块格式无效：{exc}"
            ) from exc
        target = project / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        normalized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if not target.exists() or target.read_text(encoding="utf-8") != normalized:
            target.write_text(normalized, encoding="utf-8")
            updated.append(target)
    return updated


def write_project_config_markdown(root: Path | None = None) -> Path:
    project = root or project_root()
    runtime = load_runtime_config(project)
    analysis_path = project / "config" / "analysis.json"
    paths_path = project / "config" / "paths.json"
    if not analysis_path.exists():
        analysis_path.write_text("{}\n", encoding="utf-8")
    if not paths_path.exists():
        paths_path.write_text("{}\n", encoding="utf-8")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    paths = json.loads(paths_path.read_text(encoding="utf-8"))

    markdown = "\n".join(
        [
            "# Project Config",
            "",
            "这个文件是项目的人类可读控制面板，也是推荐的日常配置入口。",
            "",
            "程序启动时会读取这里标记为 `## Sync:` 的 JSON 配置块，并同步到对应的 `config/*.json` 文件。",
            "建议把这里当成日常调整入口；如果你直接改了 `config/*.json`，后续再次启动时这里的内容会覆盖它们。",
            "如果你改坏了 JSON 语法，程序会在启动时直接报错，并指出具体的配置块。",
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
            "- 切换 LLM 模式：修改 `provider` 为 `rules`、`codex_local` 或 `openai_api`",
            "- 切换模型：修改 `codex_local.model` 或 `openai_api.model`",
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
            "- 如果你想在不同电脑上得到更稳定一致的结果，建议直接把 `codex_local.model` 写死。",
            "- 如果你更关心质量，建议优先提高 `article_summaries.max_items_per_run`，让更多单篇总结直接走 LLM。",
            "- 如果你更关心速度或额度，建议先保留 `report.enabled=true`，并限制 `article_summaries.max_items_per_run`。",
            "",
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
            "## Sync: config/analysis.json",
            "```json",
            json.dumps(analysis, ensure_ascii=False, indent=2),
            "```",
            "",
            "说明：",
            "- `provider`：当前分析后端，可选 `rules`、`codex_local`、`openai_api`",
            "- `article_summaries.enabled`：是否启用单篇总结的 LLM 分析",
            "- `article_summaries.max_items_per_run`：每次运行最多多少篇走 LLM；`0` 表示不设上限",
            "- `report.enabled`：是否启用周报的 LLM 分析",
            "- `report.max_papers_in_prompt`：周报提示词最多放多少篇文章",
            "- `deep_reads.enabled`：是否启用深度解读功能",
            "- `deep_reads.max_input_chars`：深度解读送入 LLM 的全文最大字符数",
            "- `fallback_to_rules`：LLM 失败时是否回退到规则法",
            "- `codex_local.executable`：手动指定 `codex` 可执行文件路径",
            "- `openai_api.api_key_env`：优先读取的 API key 环境变量名",
            "- `openai_api.base_url`：兼容接口地址，默认是 OpenAI Responses API",
            "",
            "## Sync: config/paths.json",
            "```json",
            json.dumps(paths, ensure_ascii=False, indent=2),
            "```",
            "",
            "说明：",
            "- `output_root`：最终输出目录。周报、单篇总结、深度解读、article_index、my_work 都会写到这里",
            "",
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
            "- `provider`：`codex_local` 或 `rules`",
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
            "### 配置档 D：只做抓取和规则总结",
            "",
            "适合排障、无额度、或者新电脑刚部署完先验证主流程。",
            "",
            "- `provider`：`rules`",
            "- `article_summaries.enabled`：`true`",
            "- `report.enabled`：`true`",
            "- `article_summaries.max_items_per_run`：保持任意值都无影响，因为不会走 LLM",
            "",
            "## 建议的模型策略",
            "",
            "- `codex_local.model` 留空：使用本机 Codex 默认模型，最省心，但不同机器上不一定完全一致。",
            "- `codex_local.model` 写死：结果更稳定，更适合长期运行和多机部署。",
            "- `openai_api.model`：适合需要跨机器一致、且明确控制外部接口模型的情况。",
            "",
            "## 其他可配置文件",
            "",
            "这些内容目前不建议直接塞进这个 Markdown 同步块里，因为体量较大、编辑风险也更高；请直接编辑对应文件：",
            "",
            "- `config/sources.json`：期刊监控列表、期刊层级、抓取模式、ISSN 等",
            "- `config/topics.json`：空间物理主题分类与关键词规则",
            "- `config/focus_tags.json`：标签体系、层级标签、同义词归一化",
            "- `doc/runtime_control/master plan.md`：研究偏好、特别提醒策略、近期方向变化",
            "- `doc/harness_control/templates/*.md`：单篇总结、深度解读和周报模板",
            "",
            "## 推荐操作方式",
            "",
            "1. 日常运行参数、路径、LLM 后端：优先改这个文件里的三个 `## Sync:` 配置块。",
            "2. 学科知识和产出风格：改 `config/*.json` 的学科配置文件与 `doc/harness_control/templates/*.md`。",
            "3. 用户偏好与重点提醒：改 `doc/runtime_control/master plan.md`。",
            "",
        ]
    )
    path = project_config_markdown_path(project)
    path.write_text(markdown + "\n", encoding="utf-8")
    return path


def state_root(root: Path | None = None) -> Path:
    override = _resolve_override_path(os.environ.get("SCIENCEMONITOR_STATE_ROOT"))
    if override is not None:
        return override
    return root or project_root()


def docs_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "doc"


def runtime_control_root(root: Path | None = None) -> Path:
    return docs_root(root) / "runtime_control"


def harness_control_root(root: Path | None = None) -> Path:
    return docs_root(root) / "harness_control"


def user_guides_root(root: Path | None = None) -> Path:
    return docs_root(root) / "user_guides"


def templates_root(root: Path | None = None) -> Path:
    return harness_control_root(root) / "templates"


def output_root(root: Path | None = None) -> Path:
    project = root or project_root()
    override = _resolve_override_path(os.environ.get("SCIENCEMONITOR_OUTPUT_ROOT"))
    if override is not None:
        return override
    configured = _resolve_configured_path(project, load_path_overrides(project).get("output_root"))
    if configured is not None:
        return configured
    return project / "out"


def data_root(root: Path | None = None) -> Path:
    override = _resolve_override_path(os.environ.get("SCIENCEMONITOR_DATA_ROOT"))
    if override is not None:
        return override
    return state_root(root) / "data"


def auto_output_root(root: Path | None = None) -> Path:
    return output_root(root) / "auto"


def manual_notes_root(root: Path | None = None) -> Path:
    return output_root(root) / "manual"


def reports_root(root: Path | None = None) -> Path:
    return output_root(root) / "research_reports"


def article_summaries_root(root: Path | None = None) -> Path:
    return auto_output_root(root) / "article_summaries"


def deep_reads_root(root: Path | None = None) -> Path:
    return auto_output_root(root) / "deep_reads"


def deep_reads_pdf_root(root: Path | None = None) -> Path:
    return auto_output_root(root) / "deep_reads_pdf"


def article_index_root(root: Path | None = None) -> Path:
    return output_root(root) / "article_index"


def article_sub_index_root(root: Path | None = None) -> Path:
    return article_index_root(root) / "sub_index"


def logs_root(root: Path | None = None) -> Path:
    override = _resolve_override_path(os.environ.get("SCIENCEMONITOR_LOG_ROOT"))
    if override is not None:
        return override
    return state_root(root) / "log"


def audit_logs_root(root: Path | None = None) -> Path:
    return logs_root(root) / "audit"


def llm_tmp_root(root: Path | None = None) -> Path:
    return logs_root(root) / "llm_tmp"


def llm_cache_root(root: Path | None = None) -> Path:
    return data_root(root) / "llm_cache"


def config_ui_state_path(root: Path | None = None) -> Path:
    override = _resolve_override_path(os.environ.get("SCIENCEMONITOR_CONFIG_UI_STATE_PATH"))
    if override is not None:
        return override
    return logs_root(root) / "config_ui_state.json"


def output_relative_path(path: Path, root: Path | None = None) -> Path:
    project = root or project_root()
    resolved = path.resolve()
    preferred_bases = [output_root(project).resolve(), project.resolve()]
    for base in preferred_bases:
        try:
            relative = resolved.relative_to(base)
            if base == project.resolve() and relative.parts[:1] == ("out",):
                trimmed = relative.parts[1:]
                return Path(*trimmed) if trimmed else Path()
            return relative
        except ValueError:
            continue
    return resolved


def obsidian_target(path: Path, root: Path | None = None, keep_suffix: bool = False) -> str:
    relative = output_relative_path(path, root)
    if not keep_suffix:
        relative = relative.with_suffix("")
    return relative.as_posix()


def load_sources(path: Path | None = None) -> list[SourceConfig]:
    source_path = path or project_root() / "config" / "sources.json"
    with source_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [SourceConfig(**item) for item in payload]


def load_topics(path: Path | None = None) -> list[TopicProfile]:
    topics_path = path or project_root() / "config" / "topics.json"
    with topics_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [TopicProfile(**item) for item in payload]


def load_focus_tags(path: Path | None = None) -> dict:
    focus_tags_path = path or project_root() / "config" / "focus_tags.json"
    if not focus_tags_path.exists():
        focus_tags_path = project_root() / "config" / "focus_tags.json"
    with focus_tags_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_master_plan_preferences(root: Path | None = None) -> UserPreferenceProfile:
    path = runtime_control_root(root) / "master plan.md"
    if not path.exists():
        return UserPreferenceProfile()

    text = path.read_text(encoding="utf-8")
    focus_section = _extract_section(text, "当前用户研究重心")
    alert_section = _extract_section(text, "文献调研中的特别提醒策略")
    focus_bullets = _extract_bullets(focus_section)
    alert_bullets = _extract_bullets(alert_section)
    theme_keywords = _derive_theme_keywords(focus_bullets + alert_bullets)

    return UserPreferenceProfile(
        research_focus=focus_bullets,
        priority_alerts=alert_bullets,
        priority_themes=list(theme_keywords.keys()),
        theme_keywords=theme_keywords,
    )


def _deep_update_dict(target: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update_dict(target[key], value)
        else:
            target[key] = value


def _extract_section(text: str, heading: str) -> str:
    pattern = rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _extract_bullets(section_text: str) -> list[str]:
    return [item.strip() for item in re.findall(r"(?m)^- (.+)$", section_text)]


def _derive_theme_keywords(lines: list[str]) -> dict[str, list[str]]:
    full_text = "\n".join(lines)
    defaults: dict[str, list[str]] = {
        "热层密度": [
            "热层密度",
            "thermospheric mass density",
            "thermospheric density",
            "neutral density",
            "tmd",
            "drag environment",
            "thermospheric forcing",
        ],
        "卫星影响": [
            "卫星",
            "satellite",
            "leo",
            "drag",
            "satellite drag",
            "orbit decay",
            "orbital decay",
            "轨道衰减",
            "轨道环境",
            "星座",
            "constellation",
        ],
        "应用影响": [
            "生产生活",
            "societal impact",
            "operational impact",
            "infrastructure impact",
            "任务安全",
            "风险评估",
            "response",
            "通信",
            "导航",
            "电网",
        ],
        "热层风": [
            "热层风",
            "thermospheric wind",
            "neutral wind",
        ],
        "业务化与预报": [
            "预报",
            "forecast",
            "forecasting",
            "nowcast",
            "业务化",
            "operational",
            "risk",
        ],
        "行星际驱动": [
            "行星际",
            "interplanetary",
            "solar wind",
            "imf",
            "imf by",
            "上游",
        ],
    }

    theme_keywords: dict[str, list[str]] = {}
    for theme, keywords in defaults.items():
        if any(keyword.lower() in full_text.lower() for keyword in keywords):
            theme_keywords[theme] = keywords

    if not theme_keywords:
        theme_keywords = defaults
    return theme_keywords
