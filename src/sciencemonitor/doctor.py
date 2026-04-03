from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .article_summaries import load_article_summary_template
from .config import (
    collect_project_config_sync_drift,
    data_root,
    load_path_overrides,
    logs_root,
    output_root,
    project_root,
    templates_root,
    validate_project_config_markdown,
    validate_research_preferences_config,
)
from .deep_reads import _load_deep_read_template
from .llm import AnalysisEngine
from .reporting import load_report_template
from .tags import load_tag_taxonomy


def run_doctor(root: Path | None = None, *, strict_runtime: bool = True) -> dict:
    project = root or project_root()
    local_python = project / ".venv" / "bin" / "python"
    local_bin = project / ".venv" / "bin"
    current_python = Path(sys.executable)
    current_prefix = Path(sys.prefix)
    env_path_first = os.environ.get("PATH", "").split(os.pathsep)[0] if os.environ.get("PATH") else ""
    venv_active = current_prefix.resolve() == (project / ".venv").resolve() or Path(os.environ.get("VIRTUAL_ENV", "")).resolve() == (project / ".venv").resolve()

    analysis_engine = AnalysisEngine(project)
    provider_status = analysis_engine.provider_status()

    tools: dict[str, str] = {}
    for tool in ("pdftotext", "pdfinfo", "pdftoppm"):
        local_tool = local_bin / tool
        if local_tool.exists():
            tools[tool] = str(local_tool)
            continue
        resolved = shutil.which(tool) or ""
        tools[tool] = resolved

    configured_paths = load_path_overrides(project)
    out_root = output_root(project)
    state_data_root = data_root(project)
    state_logs_root = logs_root(project)

    warnings: list[str] = []
    if strict_runtime:
        if not venv_active:
            warnings.append("当前解释器不是项目 .venv/bin/python。建议通过 ./scripts/run_science_monitor.sh 或 ./.venv/bin/python 启动。")
        if Path(env_path_first).resolve() != local_bin.resolve():
            warnings.append("PATH 首项不是 .venv/bin。某些子进程可能不会优先命中项目环境。")
        if not all(tools.values()):
            missing = [name for name, value in tools.items() if not value]
            warnings.append(f"PDF 工具缺失：{', '.join(missing)}。")
        if not provider_status.get("provider_supported", False):
            warnings.append(
                "当前 analysis provider 不再受支持。请将 config/analysis.json 中的 provider 改为 codex_local 或 openai_api。"
            )
        if provider_status["provider"] == "codex_local" and not provider_status["codex_available"]:
            warnings.append("当前选择 codex_local，但没有找到 codex 可执行文件。")
        if provider_status["provider"] == "openai_api" and not provider_status["openai_api_key_present"]:
            warnings.append("当前选择 openai_api，但没有检测到 API key。")
        if configured_paths.get("output_root") and not out_root.exists():
            warnings.append("config/paths.json 指定的 output_root 当前不存在。首次部署前请确认路径。")

    consistency_checks = _run_consistency_checks(project)
    for check in consistency_checks:
        if check["status"] != "ok":
            for issue in check["issues"]:
                warnings.append(f"{check['label']}：{issue}")

    return {
        "project_root": str(project),
        "current_python": str(current_python),
        "current_prefix": str(current_prefix),
        "local_python": str(local_python),
        "venv_active": venv_active,
        "path_first": env_path_first,
        "tools": tools,
        "paths": {
            "output_root": str(out_root),
            "data_root": str(state_data_root),
            "log_root": str(state_logs_root),
        },
        "provider_status": provider_status,
        "skills_runtime_dependency": False,
        "consistency_checks": consistency_checks,
        "warnings": warnings,
    }


def _run_consistency_checks(project: Path) -> list[dict[str, object]]:
    return [
        _check_project_config_sync(project),
        _check_research_preferences(project),
        _check_template(project, "单篇总结模板", templates_root(project) / "article_summary_template.md", load_article_summary_template),
        _check_template(project, "周报模板", templates_root(project) / "daily_report_template.md", load_report_template),
        _check_template(project, "深度解读模板", templates_root(project) / "deep_reading_report_template.md", _load_deep_read_template),
        _check_focus_tags(project),
    ]


def _check_project_config_sync(project: Path) -> dict[str, object]:
    issues = validate_project_config_markdown(project)
    issues.extend(collect_project_config_sync_drift(project))
    return _build_check_result("project_config_sync", "PROJECT_CONFIG 同步段", issues)


def _check_research_preferences(project: Path) -> dict[str, object]:
    issues = validate_research_preferences_config(project)
    return _build_check_result("research_preferences", "研究偏好配置", issues)


def _check_template(project: Path, label: str, path: Path, loader) -> dict[str, object]:
    issues: list[str] = []
    try:
        loader(path)
    except FileNotFoundError:
        issues.append(f"缺少模板文件：{path}")
    except Exception as exc:
        issues.append(str(exc))
    return _build_check_result(path.stem, label, issues)


def _check_focus_tags(project: Path) -> dict[str, object]:
    issues: list[str] = []
    try:
        taxonomy = load_tag_taxonomy(project)
        if not taxonomy.preferred_labels:
            issues.append("focus_tags.json 未定义任何 canonical 标签。")
        if not taxonomy.category_order:
            issues.append("focus_tags.json 未定义标签类别顺序。")
        if taxonomy.default_max_tags <= 0:
            issues.append("focus_tags.json 的 default_max_tags 必须大于 0。")
        if not taxonomy.candidate_log_path.strip():
            issues.append("focus_tags.json 的 candidate_log_path 不能为空。")
    except Exception as exc:
        issues.append(str(exc))
    return _build_check_result("focus_tags", "标签配置", issues)


def _build_check_result(check_id: str, label: str, issues: list[str]) -> dict[str, object]:
    return {
        "id": check_id,
        "label": label,
        "status": "ok" if not issues else "warning",
        "issues": issues,
    }
