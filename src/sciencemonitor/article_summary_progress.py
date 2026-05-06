from __future__ import annotations

from pathlib import Path
from typing import Callable

from .llm import AnalysisEngine
from .token_monitor import api_usage_record_snapshot, parse_codex_total_tokens


def build_summary_progress_tracker(analysis_engine: AnalysisEngine | None, *, total: int) -> dict[str, object]:
    provider = ""
    model = ""
    reasoning_effort = ""
    seen_logs: dict[str, Path] = {}
    if analysis_engine is not None:
        status = analysis_engine.provider_status()
        provider = str(status.get("provider", "") or "")
        if provider == "codex_local":
            model = str(status.get("codex_model", "") or "本机默认")
            reasoning_effort = str(status.get("article_reasoning_effort", "") or "")
            seen_logs = article_token_log_snapshot(analysis_engine)
        elif provider == "openai_api":
            model = str(status.get("openai_model", "") or "")
        elif provider == "openrouter_api":
            model = str(status.get("openrouter_model", "") or "")
        elif provider == "ollama_api":
            model = str(status.get("ollama_model", "") or "")
        if provider in {"openai_api", "openrouter_api", "ollama_api"}:
            seen_logs = api_usage_record_snapshot(analysis_engine.root, provider=provider, request_prefix="article_")
    return {
        "summary_total": int(total),
        "summary_completed": 0,
        "summary_current_index": 0,
        "summary_current_title": "",
        "summary_current_journal": "",
        "summary_provider": provider,
        "summary_model": model,
        "summary_reasoning_effort": reasoning_effort,
        "summary_token_total": 0,
        "summary_token_samples": 0,
        "summary_avg_tokens": None,
        "summary_seen_logs": seen_logs,
        "summary_skipped": 0,
    }


def emit_summary_progress(
    callback: Callable[[dict], None] | None,
    tracker: dict[str, object],
    *,
    current_index: int | None = None,
    current_title: str | None = None,
    current_journal: str | None = None,
) -> None:
    if callback is None:
        return
    callback(
        {
            "stage": "summary_generation",
            "summary_total": int(tracker.get("summary_total", 0) or 0),
            "summary_completed": int(tracker.get("summary_completed", 0) or 0),
            "summary_current_index": int(current_index if current_index is not None else tracker.get("summary_current_index", 0) or 0),
            "summary_current_title": str(current_title if current_title is not None else tracker.get("summary_current_title", "") or ""),
            "summary_current_journal": str(current_journal if current_journal is not None else tracker.get("summary_current_journal", "") or ""),
            "summary_provider": str(tracker.get("summary_provider", "") or ""),
            "summary_model": str(tracker.get("summary_model", "") or ""),
            "summary_reasoning_effort": str(tracker.get("summary_reasoning_effort", "") or ""),
            "summary_avg_tokens": tracker.get("summary_avg_tokens"),
            "summary_token_samples": int(tracker.get("summary_token_samples", 0) or 0),
            "summary_skipped": int(tracker.get("summary_skipped", 0) or 0),
        }
    )


def mark_summary_progress_completed(tracker: dict[str, object], analysis_engine: AnalysisEngine | None) -> None:
    tracker["summary_completed"] = int(tracker.get("summary_completed", 0) or 0) + 1
    tracker["summary_current_index"] = int(tracker.get("summary_completed", 0) or 0)
    if analysis_engine is None:
        return
    provider = str(tracker.get("summary_provider", "") or "")
    if provider in {"openai_api", "openrouter_api", "ollama_api"}:
        _update_api_token_progress(tracker, analysis_engine, provider)
        return
    if provider != "codex_local":
        return
    seen_logs = tracker.get("summary_seen_logs")
    if not isinstance(seen_logs, dict):
        seen_logs = {}
    current_logs = article_token_log_snapshot(analysis_engine)
    new_logs = [path for name, path in current_logs.items() if name not in seen_logs]
    token_total = int(tracker.get("summary_token_total", 0) or 0)
    token_samples = int(tracker.get("summary_token_samples", 0) or 0)
    for path in sorted(new_logs, key=lambda item: item.stat().st_mtime):
        tokens = parse_codex_total_tokens(path)
        if tokens is None:
            continue
        token_total += tokens
        token_samples += 1
    tracker["summary_seen_logs"] = current_logs
    tracker["summary_token_total"] = token_total
    tracker["summary_token_samples"] = token_samples
    tracker["summary_avg_tokens"] = round(token_total / token_samples) if token_samples else None


def article_token_log_snapshot(analysis_engine: AnalysisEngine) -> dict[str, Path]:
    return {
        path.name: path
        for path in analysis_engine.tmp_root.glob("article_*_codex.stderr.log")
        if path.is_file()
    }


def _update_api_token_progress(tracker: dict[str, object], analysis_engine: AnalysisEngine, provider: str) -> None:
    seen_records = tracker.get("summary_seen_logs")
    if not isinstance(seen_records, dict):
        seen_records = {}
    current_records = api_usage_record_snapshot(analysis_engine.root, provider=provider, request_prefix="article_")
    new_keys = [key for key in current_records if key not in seen_records]
    token_total = int(tracker.get("summary_token_total", 0) or 0)
    token_samples = int(tracker.get("summary_token_samples", 0) or 0)
    for key in sorted(new_keys):
        token_total += int(current_records.get(key, 0) or 0)
        token_samples += 1
    tracker["summary_seen_logs"] = current_records
    tracker["summary_token_total"] = token_total
    tracker["summary_token_samples"] = token_samples
    tracker["summary_avg_tokens"] = round(token_total / token_samples) if token_samples else None


def mark_summary_progress_skipped(tracker: dict[str, object]) -> None:
    tracker["summary_completed"] = int(tracker.get("summary_completed", 0) or 0) + 1
    tracker["summary_current_index"] = int(tracker.get("summary_completed", 0) or 0)
    tracker["summary_skipped"] = int(tracker.get("summary_skipped", 0) or 0) + 1
