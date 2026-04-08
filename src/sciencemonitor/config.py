from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .models import SourceConfig, TopicProfile
from .project_config_markdown import (
    build_project_config_markdown,
    find_project_config_json_blocks,
    parse_project_config_json_blocks as _parse_project_config_json_blocks,
)
from .research_preferences import (
    UserPreferenceProfile,
    build_user_preference_profile,
    extract_section as _extract_section,
    load_research_preferences_payload,
    normalize_research_preferences_payload as _normalize_research_preferences_payload,
    parse_research_preferences_from_project_markdown as _parse_research_preferences_from_project_markdown,
    validate_research_preferences_payload,
)


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


def local_path_config_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "local.paths.json"


def runtime_config_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "runtime.json"


def project_config_markdown_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "PROJECT_CONFIG.md"


def load_path_overrides(root: Path | None = None) -> dict:
    project = root or project_root()
    payload: dict = {}
    for config_path in (path_config_path(project), local_path_config_path(project)):
        if not config_path.exists():
            continue
        with config_path.open("r", encoding="utf-8") as handle:
            current = json.load(handle)
        if isinstance(current, dict):
            payload.update(current)
    return payload


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
    matches = find_project_config_json_blocks(text)
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
    markdown = build_project_config_markdown(
        project=project,
        runtime=runtime,
        analysis=analysis,
        paths=paths,
        research_preferences=research_preferences,
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


def chatgpt_web_manual_root(root: Path | None = None) -> Path:
    return data_root(root) / "chatgpt_web_manual"


def chatgpt_web_manual_requests_root(root: Path | None = None) -> Path:
    return chatgpt_web_manual_root(root) / "requests"


def chatgpt_web_manual_responses_root(root: Path | None = None) -> Path:
    return chatgpt_web_manual_root(root) / "responses"


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
    return load_research_preferences_payload(research_preferences_path(root))


def validate_project_config_markdown(root: Path | None = None) -> list[str]:
    path = project_config_markdown_path(root)
    if not path.exists():
        return [f"缺少 {path.name}。"]

    text = path.read_text(encoding="utf-8")
    matches = find_project_config_json_blocks(text)
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
    return validate_research_preferences_payload(payload, path.name)


def collect_project_config_sync_drift(root: Path | None = None) -> list[str]:
    project = root or project_root()
    path = project_config_markdown_path(project)
    if not path.exists():
        return [f"缺少 {path.name}。"]

    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    block_payloads = _parse_project_config_json_blocks(text, sync_targets=PROJECT_CONFIG_SYNC_TARGETS)
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
    return build_user_preference_profile(load_research_preferences_config(root))

def _deep_update_dict(target: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update_dict(target[key], value)
        else:
            target[key] = value
