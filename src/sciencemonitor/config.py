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

DEFAULT_RESEARCH_PREFERENCES = {
    "research_focus": [
        "热层密度及其变化机制",
        "空间环境对卫星运行、轨道衰减、阻力环境和任务安全的影响",
        "空间天气对人类生产生活的影响",
        "与应用相关的空间环境风险评估、预报和响应",
        "热层风相关研究，但不再局限于漠河区域",
    ],
    "priority_alerts": [
        "热层质量密度异常、长期变化、建模和数据同化",
        "磁暴、亚暴、行星际环境变化对卫星阻力和轨道环境的影响",
        "空间天气导致的卫星故障、通信导航受扰、轨道维持压力增加等应用问题",
        "空间环境对低轨卫星星座、姿轨控和任务规划的影响",
        "面向业务化或准业务化的预报模型、经验模型、机器学习模型",
        "热层风与热层密度、卫星阻力、能量沉降之间的耦合关系",
    ],
    "priority_article_signals": [
        "直接讨论 TMD、satellite drag、orbit decay、thermospheric forcing 的文章",
        "讨论 space weather societal impacts、operational impacts、infrastructure impacts 的文章",
        "讨论上游空间环境信息如何改善卫星环境建模和预报的文章",
    ],
    "monitoring_scope": {
        "monitoring_domain": "space_physics",
        "article_summary_domain": "space_physics",
        "report_domain": "space_physics",
    },
    "deep_read_scope": {
        "primary_domain": "space_physics",
        "allow_related_disciplines": True,
        "preferred_related_disciplines": ["artificial_intelligence"],
    },
}

PROJECT_CONFIG_SYNC_TARGETS = (
    "config/runtime.json",
    "config/analysis.json",
    "config/paths.json",
)


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
        if relative_path not in PROJECT_CONFIG_SYNC_TARGETS:
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
    research_preferences = _parse_research_preferences_from_project_markdown(text)
    if research_preferences is not None:
        target = research_preferences_path(project)
        target.parent.mkdir(parents=True, exist_ok=True)
        normalized = json.dumps(research_preferences, ensure_ascii=False, indent=2) + "\n"
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
    research_preferences = load_research_preferences_config(project)

    markdown = "\n".join(
        [
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
            "- 切换 LLM 模式：修改 `provider` 为 `codex_local` 或 `openai_api`",
            "- 切换模型：修改 `codex_local.model` 或 `openai_api.model`",
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
            "- `provider`：当前分析后端，可选 `codex_local`、`openai_api`",
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
            "- `config/research_preferences.json`：运行时落地文件，通常由上面的研究偏好同步段自动生成，不建议手改",
            "- `config/templates/article_summary_template.md`：单篇总结运行时模板",
            "- `config/templates/daily_report_template.md`：周报运行时模板",
            "- `config/templates/deep_reading_report_template.md`：深度解读运行时模板",
            "- `docs/workflow_specs/*.md`：风格参考、prompt 契约与标签参考",
            "",
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
            "## 推荐操作方式",
            "",
            "1. 日常运行参数、路径、LLM 后端：优先改这个文件里的三个 `## Sync:` 配置块。",
            "2. 学科知识和产出风格：改 `config/*.json` 的学科配置文件、`config/templates/*.md` 与相关 workflow specs。",
            "3. 用户偏好与重点提醒：改这个文件里的 `## Sync: config/research_preferences.json` 段。",
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
    return (root or project_root()) / "docs"


def research_preferences_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "research_preferences.json"


def legacy_research_preferences_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "research_preferences.md"


def config_templates_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "templates"

def workflow_specs_root(root: Path | None = None) -> Path:
    return docs_root(root) / "workflow_specs"


def runtime_control_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "config"


def harness_control_root(root: Path | None = None) -> Path:
    return workflow_specs_root(root)


def user_guides_root(root: Path | None = None) -> Path:
    return docs_root(root) / "user_guides"


def templates_root(root: Path | None = None) -> Path:
    return config_templates_root(root)


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


def load_research_preferences_config(root: Path | None = None) -> dict:
    path = research_preferences_path(root)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            merged = json.loads(json.dumps(DEFAULT_RESEARCH_PREFERENCES))
            _deep_update_dict(merged, payload)
            return _normalize_research_preferences_payload(merged)

    legacy_path = legacy_research_preferences_path(root)
    if legacy_path.exists():
        legacy_profile = load_master_plan_preferences_from_markdown(legacy_path.read_text(encoding="utf-8"))
        merged = json.loads(json.dumps(DEFAULT_RESEARCH_PREFERENCES))
        if legacy_profile.research_focus:
            merged["research_focus"] = legacy_profile.research_focus
        if legacy_profile.priority_alerts:
            merged["priority_alerts"] = legacy_profile.priority_alerts
        return _normalize_research_preferences_payload(merged)

    return _normalize_research_preferences_payload(json.loads(json.dumps(DEFAULT_RESEARCH_PREFERENCES)))


def validate_project_config_markdown(root: Path | None = None) -> list[str]:
    path = project_config_markdown_path(root)
    if not path.exists():
        return [f"缺少 {path.name}。"]

    text = path.read_text(encoding="utf-8")
    matches = re.findall(r"(?ms)^## Sync: (config/[^\n]+)\n```json\n(.*?)\n```", text)
    found_targets = {relative_path for relative_path, _ in matches}
    issues: list[str] = []

    for relative_path in PROJECT_CONFIG_SYNC_TARGETS:
        if relative_path not in found_targets:
            issues.append(f"缺少同步块：{relative_path}")

    for relative_path, block in matches:
        if relative_path not in PROJECT_CONFIG_SYNC_TARGETS:
            continue
        try:
            payload = json.loads(block)
        except json.JSONDecodeError as exc:
            issues.append(f"{relative_path} 的 JSON 配置块格式无效：{exc}")
            continue
        if not isinstance(payload, dict):
            issues.append(f"{relative_path} 的 JSON 配置块必须是对象。")

    section = _extract_section(text, "Sync: config/research_preferences.json")
    if not section:
        issues.append("缺少研究偏好同步段：config/research_preferences.json")
        return issues

    for heading in (
        "当前研究重心",
        "特别提醒策略",
        "高优先级文章信号",
        "监测范围",
        "深度解读范围",
    ):
        if not re.search(rf"(?m)^### {re.escape(heading)}$", section):
            issues.append(f"研究偏好同步段缺少小节：{heading}")

    try:
        parsed = _parse_research_preferences_from_project_markdown(text)
    except Exception as exc:
        issues.append(f"研究偏好同步段解析失败：{exc}")
        return issues
    if parsed is None:
        issues.append("研究偏好同步段未解析出有效内容。")
    return issues


def validate_research_preferences_config(root: Path | None = None) -> list[str]:
    path = research_preferences_path(root)
    if not path.exists():
        return [f"缺少运行时研究偏好文件：{path.name}。"]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name} 不是合法 JSON：{exc}"]

    if not isinstance(payload, dict):
        return [f"{path.name} 顶层必须是对象。"]

    issues: list[str] = []
    for key in ("research_focus", "priority_alerts", "priority_article_signals"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            issues.append(f"{path.name} 中的 {key} 必须是列表。")

    monitoring_scope = payload.get("monitoring_scope", {})
    if not isinstance(monitoring_scope, dict):
        issues.append(f"{path.name} 中的 monitoring_scope 必须是对象。")

    deep_read_scope = payload.get("deep_read_scope", {})
    if not isinstance(deep_read_scope, dict):
        issues.append(f"{path.name} 中的 deep_read_scope 必须是对象。")
    elif "preferred_related_disciplines" in deep_read_scope and not isinstance(
        deep_read_scope.get("preferred_related_disciplines"), list
    ):
        issues.append(f"{path.name} 中的 deep_read_scope.preferred_related_disciplines 必须是列表。")

    return issues


def collect_project_config_sync_drift(root: Path | None = None) -> list[str]:
    project = root or project_root()
    path = project_config_markdown_path(project)
    if not path.exists():
        return [f"缺少 {path.name}。"]

    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    block_payloads = _parse_project_config_json_blocks(text)
    for relative_path in PROJECT_CONFIG_SYNC_TARGETS:
        expected = block_payloads.get(relative_path)
        if expected is None:
            continue
        target = project / relative_path
        if not target.exists():
            issues.append(f"{relative_path} 不存在，无法与同步块比对。")
            continue
        try:
            actual = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"{relative_path} 不是合法 JSON：{exc}")
            continue
        if actual != expected:
            issues.append(f"{relative_path} 与 PROJECT_CONFIG.md 同步块不一致。")

    expected_preferences = _parse_research_preferences_from_project_markdown(text)
    if expected_preferences is None:
        return issues
    preferences_path = research_preferences_path(project)
    if not preferences_path.exists():
        issues.append(f"{preferences_path.name} 不存在，无法与研究偏好同步段比对。")
        return issues
    try:
        actual_preferences_raw = json.loads(preferences_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(f"{preferences_path.name} 不是合法 JSON：{exc}")
        return issues
    if not isinstance(actual_preferences_raw, dict):
        issues.append(f"{preferences_path.name} 顶层必须是对象。")
        return issues
    actual_preferences = _normalize_research_preferences_payload(actual_preferences_raw)
    if actual_preferences != expected_preferences:
        issues.append(f"{preferences_path.name} 与 PROJECT_CONFIG.md 的研究偏好同步段不一致。")
    return issues


def load_master_plan_preferences(root: Path | None = None) -> UserPreferenceProfile:
    payload = load_research_preferences_config(root)
    focus_items = [str(item).strip() for item in payload.get("research_focus", []) if str(item).strip()]
    alert_items = [str(item).strip() for item in payload.get("priority_alerts", []) if str(item).strip()]
    article_signals = [str(item).strip() for item in payload.get("priority_article_signals", []) if str(item).strip()]
    combined_alerts = alert_items + [item for item in article_signals if item not in alert_items]
    theme_keywords = _derive_theme_keywords(focus_items + combined_alerts)
    return UserPreferenceProfile(
        research_focus=focus_items,
        priority_alerts=combined_alerts,
        priority_themes=list(theme_keywords.keys()),
        theme_keywords=theme_keywords,
    )


def load_master_plan_preferences_from_markdown(text: str) -> UserPreferenceProfile:
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


def _extract_subsection(text: str, heading: str) -> str:
    pattern = rf"(?ms)^### {re.escape(heading)}\n(.*?)(?=^### |\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _extract_bullets(section_text: str) -> list[str]:
    return [item.strip() for item in re.findall(r"(?m)^- (.+)$", section_text)]


def _mapping_value(lines: list[str], key: str, default: str = "") -> str:
    for line in lines:
        if "：" in line:
            current_key, current_value = line.split("：", 1)
        elif ":" in line:
            current_key, current_value = line.split(":", 1)
        else:
            continue
        if current_key.strip() == key:
            return current_value.strip()
    return default


def _parse_yes_no(value: str, default: bool = True) -> bool:
    normalized = value.strip().lower()
    if normalized in {"是", "true", "yes", "y", "1"}:
        return True
    if normalized in {"否", "false", "no", "n", "0"}:
        return False
    return default


def _split_inline_list(value: str) -> list[str]:
    cleaned = value.strip()
    if not cleaned or cleaned == "无":
        return []
    return [item.strip() for item in re.split(r"[，,、]", cleaned) if item.strip()]


def _parse_project_config_json_blocks(text: str) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for relative_path, block in re.findall(r"(?ms)^## Sync: (config/[^\n]+)\n```json\n(.*?)\n```", text):
        if relative_path not in PROJECT_CONFIG_SYNC_TARGETS:
            continue
        payload = json.loads(block)
        if isinstance(payload, dict):
            payloads[relative_path] = payload
    return payloads


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]
    return [str(item).strip() for item in items if str(item).strip()]


def _normalize_research_preferences_payload(payload: dict) -> dict:
    monitoring_scope = payload.get("monitoring_scope", {})
    if not isinstance(monitoring_scope, dict):
        monitoring_scope = {}
    deep_read_scope = payload.get("deep_read_scope", {})
    if not isinstance(deep_read_scope, dict):
        deep_read_scope = {}
    return {
        "research_focus": _normalize_string_list(payload.get("research_focus", [])),
        "priority_alerts": _normalize_string_list(payload.get("priority_alerts", [])),
        "priority_article_signals": _normalize_string_list(payload.get("priority_article_signals", [])),
        "monitoring_scope": {
            "monitoring_domain": str(monitoring_scope.get("monitoring_domain", "space_physics")).strip() or "space_physics",
            "article_summary_domain": str(monitoring_scope.get("article_summary_domain", "space_physics")).strip()
            or "space_physics",
            "report_domain": str(monitoring_scope.get("report_domain", "space_physics")).strip() or "space_physics",
        },
        "deep_read_scope": {
            "primary_domain": str(deep_read_scope.get("primary_domain", "space_physics")).strip() or "space_physics",
            "allow_related_disciplines": bool(deep_read_scope.get("allow_related_disciplines", True)),
            "preferred_related_disciplines": _normalize_string_list(deep_read_scope.get("preferred_related_disciplines", [])),
        },
    }


def _parse_research_preferences_from_project_markdown(text: str) -> dict | None:
    section = _extract_section(text, "Sync: config/research_preferences.json")
    if not section:
        return None

    monitoring_lines = _extract_bullets(_extract_subsection(section, "监测范围"))
    deep_read_lines = _extract_bullets(_extract_subsection(section, "深度解读范围"))
    return _normalize_research_preferences_payload(
        {
            "research_focus": _extract_bullets(_extract_subsection(section, "当前研究重心")),
            "priority_alerts": _extract_bullets(_extract_subsection(section, "特别提醒策略")),
            "priority_article_signals": _extract_bullets(_extract_subsection(section, "高优先级文章信号")),
            "monitoring_scope": {
                "monitoring_domain": _mapping_value(monitoring_lines, "监测", "space_physics"),
                "article_summary_domain": _mapping_value(monitoring_lines, "单篇总结", "space_physics"),
                "report_domain": _mapping_value(monitoring_lines, "周报", "space_physics"),
            },
            "deep_read_scope": {
                "primary_domain": _mapping_value(deep_read_lines, "主领域", "space_physics"),
                "allow_related_disciplines": _parse_yes_no(
                    _mapping_value(deep_read_lines, "允许相关学科", "是"), default=True
                ),
                "preferred_related_disciplines": _split_inline_list(
                    _mapping_value(deep_read_lines, "优先相关学科", "")
                ),
            },
        }
    )


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
