from __future__ import annotations

import json
import re
from pathlib import Path

from .article_summary_meta import abbreviate_journal_name
from .article_summary_text import GPT_SUMMARY_TAG
from .config import (
    article_summaries_root,
    chatgpt_web_manual_requests_root,
    chatgpt_web_manual_responses_root,
    deep_reads_root,
    load_sources,
)
from .token_monitor import load_token_usage_snapshot


def count_markdown_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len(list(directory.glob("*.md")))


def count_json_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len(list(directory.glob("*.json")))


def latest_markdown_file(directory: Path) -> str:
    if not directory.exists():
        return ""
    paths = [path for path in directory.glob("*.md") if path.is_file()]
    if not paths:
        return ""
    latest = max(paths, key=lambda path: path.stat().st_mtime)
    return str(latest)


def latest_manual_result_file(project: Path) -> str:
    roots = [article_summaries_root(project), deep_reads_root(project)]
    tagged = _markdown_files_containing(roots, f"#{GPT_SUMMARY_TAG}")
    if tagged:
        return str(max(tagged, key=lambda path: path.stat().st_mtime))

    doi_markers = _manual_imported_doi_markers(project)
    if not doi_markers:
        return ""
    matched: list[Path] = []
    for path in _markdown_files_from_roots(roots):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue
        if any(marker in text for marker in doi_markers):
            matched.append(path)
    if not matched:
        return ""
    return str(max(matched, key=lambda path: path.stat().st_mtime))


def load_monitored_journal_labels(project: Path) -> list[str]:
    return sorted({abbreviate_journal_name(source.journal_title) for source in load_sources(project / "config" / "sources.json")})


def load_monitored_journal_groups(project: Path) -> list[dict[str, object]]:
    tier_order = {"core": 0, "related": 1, "watchlist": 2}
    tier_labels = {"core": "核心监测", "related": "相关扩展", "watchlist": "观察列表"}
    grouped: dict[str, list[str]] = {"core": [], "related": [], "watchlist": []}
    sources = sorted(
        load_sources(project / "config" / "sources.json"),
        key=lambda source: (tier_order.get(source.tier, 99), source.priority, abbreviate_journal_name(source.journal_title)),
    )
    for source in sources:
        grouped.setdefault(source.tier, [])
        grouped[source.tier].append(abbreviate_journal_name(source.journal_title))
    return [
        {"label": tier_labels.get(tier, tier), "items": items}
        for tier, items in grouped.items()
        if items
    ]


def detect_token_usage(project: Path) -> dict[str, object]:
    snapshot = load_token_usage_snapshot(project)
    return {
        "summary_text": str(snapshot.get("summary_text", "") or "今天 0（0次） / 本周 0（0次） / 本月 0（0次）"),
        "periods": snapshot.get("periods", {}),
        "chart": snapshot.get("chart", {}),
        "providers": snapshot.get("providers", {}),
    }


def count_manual_files(project: Path) -> int:
    requests = chatgpt_web_manual_requests_root(project)
    responses = chatgpt_web_manual_responses_root(project)
    request_files = len(list(requests.glob("*/prompt.md"))) if requests.exists() else 0
    response_files = len(list(responses.glob("*.json"))) if responses.exists() else 0
    return request_files + response_files


def load_latest_maintenance_status(project: Path) -> dict[str, str]:
    latest_path = project / "log" / "maintenance" / "latest.md"
    if not latest_path.exists():
        return {"overall": "unknown", "path": "", "doctor": "", "pytest": "", "harness": "", "entropy": ""}
    text = latest_path.read_text(encoding="utf-8", errors="ignore")

    def _extract(name: str) -> str:
        match = re.search(rf"^- {re.escape(name)}=(\w+)", text, flags=re.MULTILINE)
        return match.group(1) if match else ""

    return {
        "overall": _extract("overall") or "unknown",
        "path": str(latest_path),
        "doctor": _extract("doctor") or "",
        "pytest": _extract("pytest") or "",
        "harness": _extract("harness") or "",
        "entropy": _extract("entropy") or "",
    }


def _markdown_files_containing(roots: list[Path], needle: str) -> list[Path]:
    matched: list[Path] = []
    for path in _markdown_files_from_roots(roots):
        try:
            if needle in path.read_text(encoding="utf-8", errors="ignore"):
                matched.append(path)
        except Exception:
            continue
    return matched


def _markdown_files_from_roots(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(path for path in root.glob("*.md") if path.is_file())
    return files


def _manual_imported_doi_markers(project: Path) -> set[str]:
    markers: set[str] = set()
    requests_root = chatgpt_web_manual_requests_root(project)
    if not requests_root.exists():
        return markers
    for metadata_path in requests_root.glob("*/metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(metadata, dict) or not str(metadata.get("last_imported_at", "") or "").strip():
            continue
        hints = metadata.get("resource_hints", {})
        if not isinstance(hints, dict):
            continue
        doi = str(hints.get("doi", "") or "").strip().lower().rstrip(").,;")
        if doi:
            markers.add(doi)
    return markers
