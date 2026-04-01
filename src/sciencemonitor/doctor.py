from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .config import data_root, load_path_overrides, logs_root, output_root, project_root
from .llm import AnalysisEngine


def run_doctor(root: Path | None = None) -> dict:
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
    if not venv_active:
        warnings.append("当前解释器不是项目 .venv/bin/python。建议通过 ./scripts/run_science_monitor.sh 或 ./.venv/bin/python 启动。")
    if Path(env_path_first).resolve() != local_bin.resolve():
        warnings.append("PATH 首项不是 .venv/bin。某些子进程可能不会优先命中项目环境。")
    if not all(tools.values()):
        missing = [name for name, value in tools.items() if not value]
        warnings.append(f"PDF 工具缺失：{', '.join(missing)}。")
    if provider_status["provider"] == "codex_local" and not provider_status["codex_available"]:
        warnings.append("当前选择 codex_local，但没有找到 codex 可执行文件。")
    if provider_status["provider"] == "openai_api" and not provider_status["openai_api_key_present"]:
        warnings.append("当前选择 openai_api，但没有检测到 API key。")
    if configured_paths.get("output_root") and not out_root.exists():
        warnings.append("config/paths.json 指定的 output_root 当前不存在。首次部署前请确认路径。")

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
        "warnings": warnings,
    }
