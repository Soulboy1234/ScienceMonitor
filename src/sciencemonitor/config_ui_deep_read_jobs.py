from __future__ import annotations

import time
from pathlib import Path
from threading import Thread
from typing import Any, Callable

from .config import load_runtime_config
from .config_ui_runtime import read_config_ui_runtime_state, set_deep_read_job_state
from .deep_reads import run_deep_read, run_deep_read_folder
from .llm import AnalysisProviderInvalidOutput, AnalysisProviderTimeout, AnalysisQuotaExceeded
from .pipeline import ScienceMonitor


def start_deep_read_action(project: Path, params: dict[str, Any]) -> dict[str, str]:
    _guard_no_running_deep_read_job(project)
    started_at = _deep_read_timestamp()
    title = str(params.get("title", "") or params.get("doi", "") or Path(str(params.get("pdf_path", "") or "")).stem or "深度解读")
    set_deep_read_job_state(
        project,
        {
            "status": "running",
            "job_type": "deep_read",
            "label": "深度解读",
            "stage": "starting",
            "step": "准备启动",
            "message": "已接收深度解读任务，后台正在准备执行。",
            "started_at": started_at,
            "title": title,
            "pdf_path": str(params.get("pdf_path", "") or ""),
            "folder_path": "",
            "total": 1,
            "completed": 0,
            "success_count": 0,
            "failure_count": 0,
            "current_index": 0,
            "current_pdf": "",
            "source_kind": "",
            "output_path": "",
            "pdf_output_path": "",
            "error": "",
            "elapsed_seconds": 0.0,
            "estimated_total_seconds": None,
        },
    )
    worker = Thread(
        target=_run_deep_read_job_worker,
        args=(project, params, execute_deep_read_action),
        name="sciencemonitor-ui-deep-read",
        daemon=True,
    )
    worker.start()
    return {
        "kind": "ok",
        "title": "深度解读任务已开始",
        "message": "后台任务已启动，深度解读页面会实时刷新运行状态。",
        "path": "",
        "extra_path": "",
    }


def start_deep_read_folder_action(project: Path, params: dict[str, Any]) -> dict[str, str]:
    _guard_no_running_deep_read_job(project)
    started_at = _deep_read_timestamp()
    folder_path = str(params.get("folder_path", "") or "")
    set_deep_read_job_state(
        project,
        {
            "status": "running",
            "job_type": "deep_read_folder",
            "label": "批量深度解读",
            "stage": "starting",
            "step": "准备启动",
            "message": "已接收批量深度解读任务，后台正在准备执行。",
            "started_at": started_at,
            "title": "",
            "pdf_path": "",
            "folder_path": folder_path,
            "recursive": bool(params.get("recursive", False)),
            "total": 0,
            "completed": 0,
            "success_count": 0,
            "failure_count": 0,
            "current_index": 0,
            "current_pdf": "",
            "source_kind": "",
            "output_path": "",
            "pdf_output_path": "",
            "error": "",
            "elapsed_seconds": 0.0,
            "estimated_total_seconds": None,
        },
    )
    worker = Thread(
        target=_run_deep_read_job_worker,
        args=(project, params, execute_deep_read_folder_action),
        name="sciencemonitor-ui-deep-read-folder",
        daemon=True,
    )
    worker.start()
    return {
        "kind": "ok",
        "title": "批量深度解读任务已开始",
        "message": "后台任务已启动，深度解读页面会实时刷新运行状态。",
        "path": "",
        "extra_path": "",
    }


def execute_deep_read_action(
    project: Path,
    params: dict[str, Any],
    *,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict[str, str]:
    runtime = load_runtime_config(project)
    runtime.setdefault("deep_read", {})
    runtime["deep_read"]["pdf_page_limit"] = int(params.get("pdf_page_limit", 0) or 0)

    monitor = ScienceMonitor(project)
    try:
        result = run_deep_read(
            root=project,
            storage=monitor.storage,
            doi=str(params.get("doi", "") or ""),
            title=str(params.get("title", "") or ""),
            pdf_path=str(params.get("pdf_path", "") or ""),
            journal=str(params.get("journal", "") or ""),
            url=str(params.get("url", "") or ""),
            runtime_override=runtime,
            progress_callback=progress_callback,
        )
    finally:
        monitor.close()

    if not result.success:
        return {
            "kind": "error",
            "title": "深度解读失败",
            "message": result.message,
            "path": str(params.get("uploaded_path", "") or ""),
            "extra_path": "",
        }

    message = f"已完成深度解读，全文来源类型：{result.source_kind or 'unknown'}。"
    if not str(params.get("pdf_path", "") or ""):
        message += " 本次未提供 PDF，系统已自动尝试获取全文。"
    return {
        "kind": "ok",
        "title": "深度解读完成",
        "message": message,
        "path": str(result.output_path) if result.output_path else "",
        "extra_path": str(result.pdf_output_path) if result.pdf_output_path else "",
        "source_kind": result.source_kind or "",
    }


def execute_deep_read_folder_action(
    project: Path,
    params: dict[str, Any],
    *,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict[str, str]:
    runtime = load_runtime_config(project)
    runtime.setdefault("deep_read", {})
    runtime["deep_read"]["pdf_page_limit"] = int(params.get("pdf_page_limit", 0) or 0)

    monitor = ScienceMonitor(project)
    try:
        result = run_deep_read_folder(
            root=project,
            storage=monitor.storage,
            folder_path=str(params.get("folder_path", "") or ""),
            recursive=bool(params.get("recursive", False)),
            runtime_override=runtime,
            progress_callback=progress_callback,
        )
    finally:
        monitor.close()

    if result.total == 0:
        return {
            "kind": "error",
            "title": "未找到 PDF",
            "message": f"指定文件夹中没有可处理的 PDF：{result.folder_path}",
            "path": "",
            "extra_path": "",
        }

    failure_message = _format_deep_read_batch_failures(result.failed_items)
    title = "批量深度解读完成" if result.failure_count == 0 else "批量深度解读部分完成"
    message = (
        f"共发现 {result.total} 个 PDF，成功 {result.success_count} 篇，失败 {result.failure_count} 篇。"
        + failure_message
    )
    latest_output = result.successful_outputs[-1] if result.successful_outputs else None
    return {
        "kind": "ok" if result.success_count > 0 else "error",
        "title": title,
        "message": message,
        "path": str(latest_output) if latest_output else "",
        "extra_path": "",
    }


def _run_deep_read_job_worker(
    project: Path,
    params: dict[str, Any],
    executor: Callable[..., dict[str, str]],
) -> None:
    started_monotonic = time.monotonic()

    def _update_status(payload: dict[str, Any] | None = None, **updates: Any) -> None:
        if isinstance(payload, dict):
            updates = {**payload, **updates}
        elapsed_seconds = max(time.monotonic() - started_monotonic, 0.0)
        existing_job = read_config_ui_runtime_state(project).get("deep_read_job", {})
        if not isinstance(existing_job, dict):
            existing_job = {}
        state_values = {**existing_job, **updates}
        stage = str(state_values.get("stage", "") or "")
        total = int(state_values.get("total") or 0)
        completed = int(state_values.get("completed") or 0)
        estimated_total = _estimate_deep_read_total_seconds(elapsed_seconds, stage, completed, total)
        message = str(state_values.get("message", "") or "")
        if "message" not in updates:
            message = _default_deep_read_message(stage, state_values)
        set_deep_read_job_state(
            project,
            {
                **updates,
                "step": _deep_read_step_label(stage),
                "message": message,
                "elapsed_seconds": round(elapsed_seconds, 1),
                "estimated_total_seconds": round(estimated_total, 1) if estimated_total is not None else None,
                "total": total,
                "completed": completed,
                "success_count": int(state_values.get("success_count") or 0),
                "failure_count": int(state_values.get("failure_count") or 0),
                "current_index": int(state_values.get("current_index") or 0),
                "current_pdf": str(state_values.get("current_pdf", "") or ""),
                "source_kind": str(state_values.get("source_kind", "") or ""),
                "output_path": str(state_values.get("output_path", "") or ""),
                "pdf_output_path": str(state_values.get("pdf_output_path", "") or ""),
            },
        )

    try:
        result = executor(project, params, progress_callback=_update_status)
    except AnalysisQuotaExceeded as exc:
        _finish_deep_read_job(
            project,
            status="paused_quota",
            step="等待额度恢复",
            message=exc.ui_message(),
            error=str(exc),
            elapsed_seconds=max(time.monotonic() - started_monotonic, 0.0),
            recoverable=True,
            retry_after=exc.retry_after,
        )
        return
    except AnalysisProviderTimeout as exc:
        _finish_deep_read_job(
            project,
            status="paused_timeout",
            step="本地模型超时",
            message=exc.ui_message(),
            error=str(exc),
            elapsed_seconds=max(time.monotonic() - started_monotonic, 0.0),
            recoverable=True,
        )
        return
    except AnalysisProviderInvalidOutput as exc:
        _finish_deep_read_job(
            project,
            status="error",
            step="结构化输出错误",
            message=exc.ui_message(),
            error=str(exc),
            elapsed_seconds=max(time.monotonic() - started_monotonic, 0.0),
        )
        return
    except Exception as exc:
        _finish_deep_read_job(
            project,
            status="error",
            step="运行失败",
            message=str(exc),
            error=str(exc),
            elapsed_seconds=max(time.monotonic() - started_monotonic, 0.0),
        )
        return

    elapsed_seconds = max(time.monotonic() - started_monotonic, 0.0)
    status = "success" if result.get("kind") == "ok" else "error"
    _finish_deep_read_job(
        project,
        status=status,
        step="已完成" if status == "success" else "运行失败",
        message=str(result.get("message", "") or ""),
        error="" if status == "success" else str(result.get("message", "") or ""),
        elapsed_seconds=elapsed_seconds,
        output_path=str(result.get("path", "") or ""),
        pdf_output_path=str(result.get("extra_path", "") or ""),
        source_kind=str(result.get("source_kind", "") or ""),
    )


def _finish_deep_read_job(
    project: Path,
    *,
    status: str,
    step: str,
    message: str,
    error: str,
    elapsed_seconds: float,
    **extra: Any,
) -> None:
    existing_job = read_config_ui_runtime_state(project).get("deep_read_job", {})
    if not isinstance(existing_job, dict):
        existing_job = {}
    total = int(existing_job.get("total") or 0)
    completed = int(existing_job.get("completed") or 0)
    if status == "success" and total <= 1:
        total = 1
        completed = 1
        extra.setdefault("success_count", 1)
    set_deep_read_job_state(
        project,
        {
            **extra,
            "status": status,
            "stage": "done" if status == "success" else "error",
            "step": step,
            "message": message,
            "error": error,
            "elapsed_seconds": round(max(elapsed_seconds, 0.0), 1),
            "estimated_total_seconds": round(max(elapsed_seconds, 0.0), 1) if status == "success" else None,
            "total": total,
            "completed": completed,
        },
    )


def _guard_no_running_deep_read_job(project: Path) -> None:
    deep_read_job = read_config_ui_runtime_state(project).get("deep_read_job")
    if isinstance(deep_read_job, dict) and deep_read_job.get("status") == "running":
        raise ValueError("深度解读任务仍在运行中，请等待当前任务结束后再启动新的深度解读。")


def _format_deep_read_batch_failures(items) -> str:
    if not items:
        return ""
    lines = []
    for item in items[:5]:
        lines.append(f"{item.pdf_path.name}: {item.result.message}")
    if len(items) > 5:
        lines.append(f"另有 {len(items) - 5} 篇失败。")
    return " 失败明细：" + "；".join(lines)


def _deep_read_step_label(stage: object) -> str:
    labels = {
        "starting": "准备启动",
        "metadata": "解析论文信息",
        "full_text": "获取全文",
        "analysis": "深度分析",
        "ollama_evidence": "Ollama 证据预分析",
        "ollama_final": "Ollama 最终报告",
        "ollama_revision": "Ollama 修订报告",
        "render": "渲染报告",
        "review": "审核格式",
        "sync": "同步索引",
        "batch_scanning": "扫描 PDF",
        "batch_item_start": "处理当前 PDF",
        "batch_item_done": "当前 PDF 已完成",
        "done": "已完成",
        "error": "运行失败",
    }
    return labels.get(str(stage or ""), "处理中")


def _default_deep_read_message(stage: str, state: dict[str, Any]) -> str:
    if stage == "metadata":
        return "正在解析 DOI、题目和期刊信息。"
    if stage == "full_text":
        return "正在读取 PDF 或定位网页全文。"
    if stage == "analysis":
        return "正在调用当前 LLM 后端生成深度解读；本地模型可能需要数分钟。"
    if stage == "ollama_evidence":
        return "正在用全文整理研究问题、方法链和证据边界。"
    if stage == "ollama_final":
        return "正在基于证据提纲生成最终深度解读。"
    if stage == "ollama_revision":
        return "正在修订密度不足或证据边界不清的段落。"
    if stage == "render":
        return "正在渲染深度解读 Markdown。"
    if stage == "review":
        return "正在执行标签与格式审核。"
    if stage == "sync":
        return "正在同步输出索引。"
    if stage == "batch_scanning":
        return "正在扫描文件夹内的 PDF。"
    if stage == "batch_item_start":
        current = state.get("current_pdf", "")
        index = int(state.get("current_index") or 0)
        total = int(state.get("total") or 0)
        prefix = f"正在处理第 {index}/{total} 篇" if total else "正在处理当前 PDF"
        return f"{prefix}：{current}" if current else prefix
    return "任务正在运行中。"


def _estimate_deep_read_total_seconds(elapsed_seconds: float, stage: str, completed: int, total: int) -> float | None:
    if total > 1 and completed > 0:
        progress = min(max(completed / max(total, 1), 0.05), 0.95)
        return elapsed_seconds / progress
    stage_progress = {
        "starting": 0.03,
        "metadata": 0.08,
        "full_text": 0.18,
        "analysis": 0.68,
        "ollama_evidence": 0.36,
        "ollama_final": 0.72,
        "ollama_revision": 0.84,
        "render": 0.9,
        "review": 0.94,
        "sync": 0.97,
    }.get(stage)
    if stage_progress:
        return elapsed_seconds / stage_progress
    return None


def _deep_read_timestamp() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")
