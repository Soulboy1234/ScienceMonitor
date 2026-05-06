from __future__ import annotations

import time
from pathlib import Path
from threading import Thread
from typing import Any, Callable

from .config_ui_runtime import read_config_ui_runtime_state, set_weekly_report_job_state
from .llm import AnalysisProviderTimeout, AnalysisQuotaExceeded
from .pipeline import ScienceMonitor


def start_report_action(project: Path, params: dict[str, Any]) -> dict[str, str]:
    runtime_state = read_config_ui_runtime_state(project)
    current_job = runtime_state.get("report_job")
    if isinstance(current_job, dict) and current_job.get("status") == "running":
        raise ValueError("周报任务仍在运行中，请等待当前任务结束后再启动新的周报。")

    started_at = _report_timestamp()
    set_weekly_report_job_state(
        project,
        {
            "status": "running",
            "job_type": "weekly_report",
            "started_at": started_at,
            "step": "准备启动",
            "message": "已接收周报任务，正在准备执行。",
            "run_update": bool(params["run_update"]),
            "report_date": params["report_date"].isoformat(),
            "window_days": int(params["window_days"]),
            "fetched_count": 0,
            "kept_count": 0,
            "paper_count": 0,
            "journal_count": 0,
            "source_index": 0,
            "source_total": 0,
            "summary_total": 0,
            "summary_completed": 0,
            "summary_current_index": 0,
            "summary_current_title": "",
            "summary_provider": "",
            "summary_model": "",
            "summary_reasoning_effort": "",
            "summary_avg_tokens": None,
            "summary_token_samples": 0,
            "summary_skipped": 0,
            "elapsed_seconds": 0.0,
            "estimated_total_seconds": None,
            "report_path": "",
            "error": "",
        },
    )

    worker = Thread(
        target=_run_report_job_worker,
        args=(project, params),
        name="sciencemonitor-ui-weekly-report",
        daemon=True,
    )
    worker.start()
    return {
        "kind": "ok",
        "title": "周报任务已开始",
        "message": "后台任务已启动，周报页面会实时刷新运行状态。",
        "path": "",
        "extra_path": "",
    }


def execute_report_action(
    project: Path,
    params: dict[str, Any],
    *,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict[str, str]:
    monitor = ScienceMonitor(project)
    try:
        if params["run_update"]:
            update_result, report_path, stats = monitor.run_daily(
                report_date=params["report_date"],
                days_back=params["update_days_back"],
                max_per_source=params["max_per_source"],
                hydrate=params["hydrate"],
                source_ids=params["source_ids"] or None,
                progress_callback=progress_callback,
                reuse_existing_summaries=bool(params.get("reuse_existing_summaries", True)),
            )
            message = (
                f"已完成更新并生成周报。候选 {update_result.fetched_count} 条，保留 {update_result.kept_count} 篇；"
                f"周报覆盖 {stats.get('paper_count', 0)} 篇论文、{stats.get('journal_count', 0)} 本期刊。"
            )
            if stats.get("skipped_summary_count", 0):
                message += f" 另有 {stats.get('skipped_summary_count', 0)} 篇单篇总结未完成，已在周报中列出。"
            if update_result.error_count:
                message += f" 另有 {update_result.error_count} 个来源报错，请再检查日志。"
        else:
            _emit_report_progress(
                progress_callback,
                stage="building_report",
                report_date=params["report_date"].isoformat(),
                window_days=params["window_days"],
            )
            report_path, stats = monitor.generate_windowed_report(
                report_date=params["report_date"],
                window_days=params["window_days"],
                progress_callback=progress_callback,
                reuse_existing_summaries=bool(params.get("reuse_existing_summaries", True)),
            )
            message = (
                f"已基于当前数据库重建周报，窗口 {params['window_days']} 天；"
                f"覆盖 {stats.get('paper_count', 0)} 篇论文、{stats.get('journal_count', 0)} 本期刊。"
            )
            if stats.get("skipped_summary_count", 0):
                message += f" 另有 {stats.get('skipped_summary_count', 0)} 篇单篇总结未完成，已在周报中列出。"
            if params["source_ids"]:
                message += " 注意：未勾选“先更新再生成”时，限定期刊 source_ids 不生效。"
        return {
            "kind": "ok",
            "title": "周报生成完成",
            "message": message,
            "path": str(report_path),
            "paper_count": str(stats.get("paper_count", 0)),
            "journal_count": str(stats.get("journal_count", 0)),
            "skipped_summary_count": str(stats.get("skipped_summary_count", 0)),
        }
    finally:
        monitor.close()


def _run_report_job_worker(project: Path, params: dict[str, Any]) -> None:
    started_monotonic = time.monotonic()

    def _update_status(payload: dict[str, Any] | None = None, **updates: Any) -> None:
        if isinstance(payload, dict):
            updates = {**payload, **updates}
        elapsed_seconds = max(time.monotonic() - started_monotonic, 0.0)
        existing_job = read_config_ui_runtime_state(project).get("report_job", {})
        if not isinstance(existing_job, dict):
            existing_job = {}
        state_values = {**existing_job, **updates}
        stage = str(state_values.get("stage", "") or "")
        source_total = int(state_values.get("source_total") or 0)
        source_index = int(state_values.get("source_index") or 0)
        estimated_total = _estimate_total_seconds(elapsed_seconds, stage, source_index, source_total)
        message = str(state_values.get("message", "") or "")
        if "message" not in updates and stage == "summary_generation":
            message = "正在生成单篇总结；本地模型较慢时，单篇可能需要数分钟。"
        current_source = str(state_values.get("current_source", "") or "")
        if stage not in {"fetching"}:
            current_source = ""
        set_weekly_report_job_state(
            project,
            {
                **updates,
                "step": _report_step_label(stage),
                "message": message,
                "elapsed_seconds": round(elapsed_seconds, 1),
                "estimated_total_seconds": round(estimated_total, 1) if estimated_total is not None else None,
                "current_source": current_source,
                "fetched_count": int(state_values.get("fetched_count") or 0),
                "kept_count": int(state_values.get("kept_count") or 0),
                "source_index": source_index,
                "source_total": source_total,
                "summary_total": int(state_values.get("summary_total") or 0),
                "summary_completed": int(state_values.get("summary_completed") or 0),
                "summary_current_index": int(state_values.get("summary_current_index") or 0),
                "summary_current_title": str(state_values.get("summary_current_title", "") or ""),
                "summary_current_journal": str(state_values.get("summary_current_journal", "") or ""),
                "summary_provider": str(state_values.get("summary_provider", "") or ""),
                "summary_model": str(state_values.get("summary_model", "") or ""),
                "summary_reasoning_effort": str(state_values.get("summary_reasoning_effort", "") or ""),
                "summary_avg_tokens": int(state_values.get("summary_avg_tokens") or 0) or None,
                "summary_token_samples": int(state_values.get("summary_token_samples") or 0),
                "summary_skipped": int(state_values.get("summary_skipped") or 0),
            },
        )

    try:
        result = execute_report_action(project, params, progress_callback=_update_status)
    except AnalysisQuotaExceeded as exc:
        elapsed_seconds = round(max(time.monotonic() - started_monotonic, 0.0), 1)
        summary_completed = int(read_config_ui_runtime_state(project).get("report_job", {}).get("summary_completed", 0) or 0)
        summary_total = int(read_config_ui_runtime_state(project).get("report_job", {}).get("summary_total", 0) or 0)
        set_weekly_report_job_state(
            project,
            {
                "status": "paused_quota",
                "step": "等待额度恢复",
                "message": _quota_pause_message(exc, summary_completed=summary_completed, summary_total=summary_total),
                "error": str(exc),
                "recoverable": True,
                "retry_after": exc.retry_after,
                "elapsed_seconds": elapsed_seconds,
                "estimated_total_seconds": None,
            },
        )
        return
    except AnalysisProviderTimeout as exc:
        elapsed_seconds = round(max(time.monotonic() - started_monotonic, 0.0), 1)
        report_job = read_config_ui_runtime_state(project).get("report_job", {})
        if not isinstance(report_job, dict):
            report_job = {}
        summary_completed = int(report_job.get("summary_completed", 0) or 0)
        summary_total = int(report_job.get("summary_total", 0) or 0)
        set_weekly_report_job_state(
            project,
            {
                "status": "paused_timeout",
                "step": "本地模型超时",
                "message": _timeout_pause_message(exc, summary_completed=summary_completed, summary_total=summary_total),
                "error": str(exc),
                "recoverable": True,
                "elapsed_seconds": elapsed_seconds,
                "estimated_total_seconds": None,
            },
        )
        return
    except Exception as exc:
        set_weekly_report_job_state(
            project,
            {
                "status": "error",
                "step": "运行失败",
                "message": str(exc),
                "error": str(exc),
                "elapsed_seconds": round(max(time.monotonic() - started_monotonic, 0.0), 1),
                "estimated_total_seconds": None,
            },
        )
        return

    elapsed_seconds = round(max(time.monotonic() - started_monotonic, 0.0), 1)
    set_weekly_report_job_state(
        project,
        {
            "status": "success",
            "step": "已完成",
            "message": str(result.get("message", "") or ""),
            "report_path": str(result.get("path", "") or ""),
            "paper_count": int(result.get("paper_count", "0") or 0),
            "journal_count": int(result.get("journal_count", "0") or 0),
            "summary_skipped": int(result.get("skipped_summary_count", "0") or 0),
            "elapsed_seconds": elapsed_seconds,
            "estimated_total_seconds": elapsed_seconds,
            "error": "",
        },
    )


def _emit_report_progress(callback: Callable[[dict], None] | None, **payload: Any) -> None:
    if callback is None:
        return
    callback(payload)


def _report_step_label(stage: object) -> str:
    labels = {
        "starting": "准备启动",
        "fetch_prepare": "准备抓取来源",
        "fetching": "抓取与筛选文章",
        "deduplicating": "去重并写入数据库",
        "update_complete": "更新阶段完成",
        "building_report": "准备生成周报",
        "summary_generation": "生成单篇总结",
        "report_render": "渲染周报内容",
        "sync_output": "同步输出目录",
        "done": "已完成",
    }
    return labels.get(str(stage or ""), "处理中")


def _estimate_total_seconds(elapsed_seconds: float, stage: object, source_index: int, source_total: int) -> float | None:
    stage_name = str(stage or "")
    if source_total > 0 and source_index > 0 and stage_name in {"fetching", "deduplicating", "update_complete"}:
        progress = min(max(source_index / max(source_total, 1), 0.05), 0.9)
        if stage_name == "deduplicating":
            progress = 0.92
        elif stage_name == "update_complete":
            progress = 0.96
        return elapsed_seconds / progress
    stage_progress = {
        "starting": 0.05,
        "building_report": 0.7,
        "summary_generation": 0.8,
        "report_render": 0.9,
        "sync_output": 0.96,
    }.get(stage_name)
    if stage_progress:
        return elapsed_seconds / stage_progress
    return None


def _report_timestamp() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def _quota_pause_message(exc: AnalysisQuotaExceeded, *, summary_completed: int, summary_total: int) -> str:
    progress_text = ""
    if summary_total > 0:
        progress_text = f" 已完成单篇总结 {summary_completed}/{summary_total}，已完成内容会直接保留。"
    retry_text = f" 可在 {exc.retry_after} 后重试。" if exc.retry_after else " 额度恢复后可直接重试。"
    return (
        f"{exc.ui_message()}{progress_text}{retry_text}"
        " 再次点击“开始生成周报”即可继续；保持“跳过已生成总结”开启即可避免重做已完成部分。"
    )


def _timeout_pause_message(exc: AnalysisProviderTimeout, *, summary_completed: int, summary_total: int) -> str:
    progress_text = ""
    if summary_total > 0:
        progress_text = f" 已完成单篇总结 {summary_completed}/{summary_total}，已完成内容会直接保留。"
    return (
        f"{exc.ui_message()}{progress_text}"
        " 可以调大 Ollama 超时秒数后再次点击“开始生成周报”；保持“跳过已生成总结”开启即可避免重做已完成部分。"
    )
