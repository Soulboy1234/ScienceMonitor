from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from .config import config_ui_state_path


_STATE_LOCK = Lock()


def read_config_ui_runtime_state(project: Path) -> dict[str, Any]:
    path = config_ui_state_path(project)
    with _STATE_LOCK:
        return _read_state_unlocked(path)


def write_config_ui_runtime_state(project: Path, *, host: str, port: int, url: str, token: str = "") -> None:
    path = config_ui_state_path(project)
    payload = {
        "pid": os.getpid(),
        "host": host,
        "port": port,
        "url": url,
        "token": token,
        "started_at": _now_iso(),
    }
    with _STATE_LOCK:
        existing = _read_state_unlocked(path)
        report_job = existing.get("report_job")
        if isinstance(report_job, dict):
            payload["report_job"] = report_job
        deep_read_job = existing.get("deep_read_job")
        if isinstance(deep_read_job, dict):
            payload["deep_read_job"] = deep_read_job
        _write_state_unlocked(path, payload)


def clear_config_ui_runtime_state(project: Path) -> None:
    path = config_ui_state_path(project)
    with _STATE_LOCK:
        if path.exists():
            path.unlink()


def update_config_ui_runtime_state(project: Path, updater: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    path = config_ui_state_path(project)
    with _STATE_LOCK:
        payload = _read_state_unlocked(path)
        updater(payload)
        _write_state_unlocked(path, payload)
        return json.loads(json.dumps(payload))


def set_weekly_report_job_state(project: Path, updates: dict[str, Any]) -> dict[str, Any]:
    def _apply(payload: dict[str, Any]) -> None:
        job = payload.get("report_job")
        if not isinstance(job, dict):
            job = {}
        job.update(updates)
        job["updated_at"] = _now_iso()
        payload["report_job"] = job

    return update_config_ui_runtime_state(project, _apply)


def clear_weekly_report_job_state(project: Path) -> dict[str, Any]:
    def _apply(payload: dict[str, Any]) -> None:
        payload.pop("report_job", None)

    return update_config_ui_runtime_state(project, _apply)


def set_deep_read_job_state(project: Path, updates: dict[str, Any]) -> dict[str, Any]:
    def _apply(payload: dict[str, Any]) -> None:
        job = payload.get("deep_read_job")
        if not isinstance(job, dict):
            job = {}
        job.update(updates)
        job["updated_at"] = _now_iso()
        payload["deep_read_job"] = job

    return update_config_ui_runtime_state(project, _apply)


def clear_deep_read_job_state(project: Path) -> dict[str, Any]:
    def _apply(payload: dict[str, Any]) -> None:
        payload.pop("deep_read_job", None)

    return update_config_ui_runtime_state(project, _apply)


def active_config_ui_task(project: Path) -> dict[str, Any]:
    state = read_config_ui_runtime_state(project)
    return _active_task_from_payload(state)


def _active_task_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    report_job = payload.get("report_job")
    if isinstance(report_job, dict) and str(report_job.get("status", "") or "") == "running":
        return {
            "kind": "weekly_report",
            "label": "周报任务",
            "step": str(report_job.get("step", "") or "处理中"),
            "message": str(report_job.get("message", "") or ""),
            "status": "running",
        }
    deep_read_job = payload.get("deep_read_job")
    if isinstance(deep_read_job, dict) and str(deep_read_job.get("status", "") or "") == "running":
        return {
            "kind": "deep_read",
            "label": str(deep_read_job.get("label", "") or "深度解读"),
            "step": str(deep_read_job.get("step", "") or "处理中"),
            "message": str(deep_read_job.get("message", "") or ""),
            "status": "running",
        }
    return {}


def _read_state_unlocked(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_state_unlocked(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
