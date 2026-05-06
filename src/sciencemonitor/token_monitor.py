from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from .analysis_providers import AUTOMATIC_PROVIDER_LABELS
from .config import llm_tmp_root, token_monitor_root

TOKEN_MONITOR_SCHEMA_VERSION = 3
DEFAULT_CHART_DAYS = 30
DEFAULT_CHART_FUTURE_DAYS = 2
PROVIDER_ORDER = ("codex_local", "openai_api", "openrouter_api", "ollama_api")
PROVIDER_COLORS = {
    "codex_local": "#d9482b",
    "openai_api": "#7c3aed",
    "openrouter_api": "#8b4513",
    "ollama_api": "#2f855a",
}


def parse_codex_total_tokens(path: Path) -> int | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"tokens used\s*([0-9,]+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def record_api_usage(
    root: Path,
    *,
    provider: str,
    model: str,
    raw_usage: dict | None,
    request_name: str = "",
    timestamp: datetime | None = None,
) -> None:
    usage = normalize_usage(provider, raw_usage or {})
    if usage["total_tokens"] <= 0:
        return
    path = _api_usage_events_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now()
    record = {
        "provider": provider,
        "provider_label": _provider_label(provider),
        "model": model.strip(),
        "source": "api",
        "request_name": request_name.strip(),
        "timestamp": stamp.isoformat(timespec="seconds"),
        "date": stamp.date().isoformat(),
        **usage,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
        handle.write("\n")


def api_usage_record_snapshot(root: Path, *, provider: str = "", request_prefix: str = "") -> dict[str, int]:
    records: dict[str, int] = {}
    path = _api_usage_events_path(root)
    if not path.exists():
        return records
    for index, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines()):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if provider and str(payload.get("provider", "") or "") != provider:
            continue
        request_name = str(payload.get("request_name", "") or "")
        if request_prefix and not request_name.startswith(request_prefix):
            continue
        timestamp = str(payload.get("timestamp", "") or "")
        key = f"{timestamp}|{request_name}|{index}"
        records[key] = _int_value(payload.get("total_tokens"))
    return records


def load_token_usage_snapshot(
    root: Path,
    *,
    chart_days: int = DEFAULT_CHART_DAYS,
    chart_future_days: int = DEFAULT_CHART_FUTURE_DAYS,
) -> dict[str, object]:
    chart_days = max(7, int(chart_days or DEFAULT_CHART_DAYS))
    chart_future_days = max(0, int(chart_future_days or 0))
    signature = _build_source_signature(root)
    snapshot_path = _latest_snapshot_path(root)
    snapshot = _load_snapshot_if_fresh(snapshot_path, signature, chart_days, chart_future_days)
    if snapshot is not None:
        return snapshot
    codex_records = _collect_codex_records(root)
    api_records = _load_api_usage_records(root)
    all_records = sorted(
        [*codex_records, *api_records],
        key=lambda item: (str(item.get("timestamp", "")), str(item.get("request_name", ""))),
    )
    daily = _aggregate_daily_records(all_records)
    snapshot = _build_snapshot_payload(
        all_records,
        daily,
        chart_days=chart_days,
        chart_future_days=chart_future_days,
        source_signature=signature,
    )
    monitor_root = token_monitor_root(root)
    monitor_root.mkdir(parents=True, exist_ok=True)
    _write_json_if_changed(_codex_usage_path(root), {"schema_version": TOKEN_MONITOR_SCHEMA_VERSION, "generated_at": _now_text(), "records": codex_records})
    _write_json_if_changed(_daily_usage_path(root), {"schema_version": TOKEN_MONITOR_SCHEMA_VERSION, "generated_at": _now_text(), "days": daily})
    _write_json_if_changed(snapshot_path, snapshot)
    return snapshot


def normalize_usage(provider: str, raw_usage: dict) -> dict[str, int]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = _int_value(usage.get("input_tokens"))
    output_tokens = _int_value(usage.get("output_tokens"))
    if provider == "openrouter_api":
        input_tokens = input_tokens or _int_value(usage.get("prompt_tokens"))
        output_tokens = output_tokens or _int_value(usage.get("completion_tokens"))
    total_tokens = _int_value(usage.get("total_tokens"))
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    return {
        "total_tokens": max(0, total_tokens),
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
    }


def _build_snapshot_payload(
    records: list[dict[str, object]],
    daily: list[dict[str, object]],
    *,
    chart_days: int,
    chart_future_days: int,
    source_signature: dict[str, object],
) -> dict[str, object]:
    today = date.today()
    today_start = datetime(today.year, today.month, today.day)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = datetime(today.year, today.month, 1)
    periods = {
        "today": {"label": "今天", "tokens": 0, "runs": 0},
        "week": {"label": "本周", "tokens": 0, "runs": 0},
        "month": {"label": "本月", "tokens": 0, "runs": 0},
    }
    provider_totals: dict[str, dict[str, object]] = {}
    for record in records:
        stamp = _parse_timestamp(str(record.get("timestamp", "") or ""))
        if stamp is None:
            continue
        provider = str(record.get("provider", "") or "")
        total_tokens = _int_value(record.get("total_tokens"))
        if total_tokens <= 0:
            continue
        provider_bucket = provider_totals.setdefault(
            provider,
            {
                "label": _provider_label(provider),
                "color": _provider_color(provider),
                "tokens": 0,
                "runs": 0,
            },
        )
        provider_bucket["tokens"] = int(provider_bucket.get("tokens", 0) or 0) + total_tokens
        provider_bucket["runs"] = int(provider_bucket.get("runs", 0) or 0) + 1
        if stamp >= today_start:
            _add_period_usage(periods["today"], total_tokens)
        if stamp >= week_start:
            _add_period_usage(periods["week"], total_tokens)
        if stamp >= month_start:
            _add_period_usage(periods["month"], total_tokens)
    chart = _build_chart_series(daily, chart_days=chart_days, chart_future_days=chart_future_days)
    summary_text = " / ".join(
        f"{bucket['label']} {_format_tokens(int(bucket['tokens']))}（{int(bucket['runs'] or 0)}次）"
        for bucket in periods.values()
    )
    return {
        "schema_version": TOKEN_MONITOR_SCHEMA_VERSION,
        "generated_at": _now_text(),
        "generated_on": today.isoformat(),
        "chart_days": chart_days,
        "chart_future_days": chart_future_days,
        "source_signature": source_signature,
        "summary_text": summary_text,
        "periods": periods,
        "chart": chart,
        "providers": provider_totals,
    }


def _build_chart_series(daily: list[dict[str, object]], *, chart_days: int, chart_future_days: int) -> dict[str, object]:
    today = date.today()
    end_day = today + timedelta(days=chart_future_days)
    start_day = end_day - timedelta(days=chart_days - 1)
    daily_map = {str(item.get("date", "")): item for item in daily}
    active_providers = _active_chart_providers(daily)
    max_total = max((int(item.get("total_tokens", 0) or 0) for item in daily), default=0)
    points: list[dict[str, object]] = []
    current = start_day
    while current <= end_day:
        key = current.isoformat()
        day_data = daily_map.get(key, {})
        providers = day_data.get("providers", {})
        if not isinstance(providers, dict):
            providers = {}
        points.append(
            {
                "date": key,
                "label": f"{current.month}月{current.day}日",
                "short_label": f"{current.month}/{current.day}",
                "show_label": current == start_day or current == end_day,
                "total_tokens": int(day_data.get("total_tokens", 0) or 0),
                "runs": int(day_data.get("runs", 0) or 0),
                "providers": {
                    provider: {
                        "tokens": int((providers.get(provider, {}) or {}).get("tokens", 0) or 0),
                        "label": _provider_label(provider),
                        "color": _provider_color(provider),
                    }
                    for provider in active_providers
                },
            }
        )
        current += timedelta(days=1)
    return {
        "max_tokens": max_total,
        "providers": [
            {"key": provider, "label": _provider_label(provider), "color": _provider_color(provider)}
            for provider in active_providers
        ],
        "days": points,
    }


def _active_chart_providers(daily: list[dict[str, object]]) -> list[str]:
    seen: list[str] = []
    for provider in PROVIDER_ORDER:
        if any(int(((item.get("providers", {}) or {}).get(provider, {}) or {}).get("tokens", 0) or 0) > 0 for item in daily):
            seen.append(provider)
    return seen or ["codex_local"]


def _aggregate_daily_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    bucket: dict[str, dict[str, object]] = {}
    for record in records:
        day_key = str(record.get("date", "") or "")
        provider = str(record.get("provider", "") or "")
        total_tokens = _int_value(record.get("total_tokens"))
        if not day_key or not provider or total_tokens <= 0:
            continue
        day_bucket = bucket.setdefault(day_key, {"date": day_key, "total_tokens": 0, "runs": 0, "providers": {}})
        day_bucket["total_tokens"] = int(day_bucket.get("total_tokens", 0) or 0) + total_tokens
        day_bucket["runs"] = int(day_bucket.get("runs", 0) or 0) + 1
        providers = day_bucket.setdefault("providers", {})
        if not isinstance(providers, dict):
            providers = {}
            day_bucket["providers"] = providers
        provider_bucket = providers.setdefault(
            provider,
            {"tokens": 0, "runs": 0, "label": _provider_label(provider), "color": _provider_color(provider)},
        )
        provider_bucket["tokens"] = int(provider_bucket.get("tokens", 0) or 0) + total_tokens
        provider_bucket["runs"] = int(provider_bucket.get("runs", 0) or 0) + 1
    return [bucket[key] for key in sorted(bucket)]


def _collect_codex_records(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(llm_tmp_root(root).glob("*_codex.stderr.log")):
        if not path.is_file():
            continue
        total_tokens = parse_codex_total_tokens(path)
        if total_tokens is None:
            continue
        stamp = datetime.fromtimestamp(path.stat().st_mtime)
        request_name = path.name[: -len("_codex.stderr.log")]
        records.append(
            {
                "provider": "codex_local",
                "provider_label": _provider_label("codex_local"),
                "model": "本机默认",
                "source": "exec",
                "request_name": request_name,
                "timestamp": stamp.isoformat(timespec="seconds"),
                "date": stamp.date().isoformat(),
                "total_tokens": total_tokens,
                "input_tokens": 0,
                "output_tokens": 0,
                "origin_path": str(path),
            }
        )
    return records


def _load_api_usage_records(root: Path) -> list[dict[str, object]]:
    path = _api_usage_events_path(root)
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        provider = str(payload.get("provider", "") or "")
        if not provider:
            continue
        payload["provider_label"] = _provider_label(provider)
        payload["date"] = str(payload.get("date", "") or "") or str(payload.get("timestamp", "") or "")[:10]
        records.append(payload)
    return records


def _build_source_signature(root: Path) -> dict[str, object]:
    codex_paths = [path for path in llm_tmp_root(root).glob("*_codex.stderr.log") if path.is_file()]
    codex_count = len(codex_paths)
    codex_latest_mtime_ns = max((path.stat().st_mtime_ns for path in codex_paths), default=0)
    codex_total_size = sum(path.stat().st_size for path in codex_paths)
    api_path = _api_usage_events_path(root)
    return {
        "codex_log_count": codex_count,
        "codex_latest_mtime_ns": codex_latest_mtime_ns,
        "codex_total_size": codex_total_size,
        "api_events_exists": api_path.exists(),
        "api_events_mtime_ns": api_path.stat().st_mtime_ns if api_path.exists() else 0,
        "api_events_size": api_path.stat().st_size if api_path.exists() else 0,
    }


def _load_snapshot_if_fresh(path: Path, signature: dict[str, object], chart_days: int, chart_future_days: int) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("schema_version", 0) or 0) != TOKEN_MONITOR_SCHEMA_VERSION:
        return None
    if int(payload.get("chart_days", 0) or 0) != chart_days:
        return None
    if int(payload.get("chart_future_days", 0) or 0) != chart_future_days:
        return None
    if str(payload.get("generated_on", "") or "") != date.today().isoformat():
        return None
    if payload.get("source_signature", {}) != signature:
        return None
    return payload


def _write_json_if_changed(path: Path, payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        current = path.read_text(encoding="utf-8", errors="ignore")
        if current == encoded:
            return
    path.write_text(encoded, encoding="utf-8")


def _provider_label(provider: str) -> str:
    return AUTOMATIC_PROVIDER_LABELS.get(provider, provider)


def _provider_color(provider: str) -> str:
    return PROVIDER_COLORS.get(provider, "#6b7280")


def _add_period_usage(period: dict[str, object], total_tokens: int) -> None:
    period["tokens"] = int(period.get("tokens", 0) or 0) + total_tokens
    period["runs"] = int(period.get("runs", 0) or 0) + 1


def _format_tokens(value: int) -> str:
    return f"{value:,}"


def _parse_timestamp(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _codex_usage_path(root: Path) -> Path:
    return token_monitor_root(root) / "codex_usage.json"


def _api_usage_events_path(root: Path) -> Path:
    return token_monitor_root(root) / "api_usage.jsonl"


def _daily_usage_path(root: Path) -> Path:
    return token_monitor_root(root) / "daily_usage.json"


def _latest_snapshot_path(root: Path) -> Path:
    return token_monitor_root(root) / "latest_snapshot.json"
