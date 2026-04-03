from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import logs_root, project_root
from .tags import load_tag_taxonomy


@dataclass(frozen=True)
class TagCandidate:
    tag: str
    count: int
    first_seen: str
    last_seen: str
    contexts: dict[str, int]


def candidate_log_path(root: Path | None = None) -> Path:
    project = root or project_root()
    taxonomy = load_tag_taxonomy(project)
    return project / taxonomy.candidate_log_path


def candidate_review_report_path(root: Path | None = None) -> Path:
    return logs_root(root) / "tag_candidates_review.md"


def load_tag_candidates(root: Path | None = None) -> list[TagCandidate]:
    path = candidate_log_path(root)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("candidates", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw, dict):
        return []
    items: list[TagCandidate] = []
    for tag, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        contexts = entry.get("contexts", {})
        items.append(
            TagCandidate(
                tag=str(tag),
                count=int(entry.get("count", 0) or 0),
                first_seen=str(entry.get("first_seen", "") or ""),
                last_seen=str(entry.get("last_seen", "") or ""),
                contexts={str(key): int(value or 0) for key, value in contexts.items()} if isinstance(contexts, dict) else {},
            )
        )
    items.sort(key=lambda item: (-item.count, item.tag))
    return items


def filter_tag_candidates(root: Path | None = None, *, min_count: int = 2, limit: int = 50) -> list[TagCandidate]:
    candidates = [item for item in load_tag_candidates(root) if item.count >= min_count]
    if limit > 0:
        return candidates[:limit]
    return candidates


def render_tag_candidates_report(root: Path | None = None, *, min_count: int = 2, limit: int = 50) -> str:
    path = candidate_log_path(root)
    candidates = filter_tag_candidates(root, min_count=min_count, limit=limit)
    lines = [
        "# 候选标签审阅",
        "",
        f"- 候选源文件：`{path}`",
        f"- 过滤条件：`count >= {min_count}`",
        f"- 报告条数上限：`{limit if limit > 0 else 'ALL'}`",
        "",
    ]
    if not path.exists():
        lines.extend(
            [
                "当前还没有候选标签记录。",
                "",
                "候选文件会在运行时遇到“未收录但被保留的新标签”后自动生成。",
            ]
        )
        return "\n".join(lines) + "\n"

    if not candidates:
        lines.extend(
            [
                "当前没有达到过滤条件的候选标签。",
                "",
                "可降低 `min_count` 再查看一次。",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "## 审阅建议",
            "",
            "- 优先看重复次数高、命名稳定、上下文集中且能归入现有层级体系的标签。",
            "- 如果只是旧命名变体或过长短语，优先加 alias，不要直接把原词吸收到 canonical 列表。",
            "- 如果标签只在 AI/交叉学科深读里出现，应先确认是否需要扩展该领域的常用词表。",
            "",
            "## 候选列表",
            "",
            "| 标签 | 次数 | 上下文 | 首次出现 | 最近出现 |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for item in candidates:
        contexts = ", ".join(f"{key}:{value}" for key, value in sorted(item.contexts.items())) or "-"
        lines.append(f"| `{item.tag}` | {item.count} | {contexts} | {item.first_seen or '-'} | {item.last_seen or '-'} |")
    lines.append("")
    return "\n".join(lines)


def write_tag_candidates_report(root: Path | None = None, *, min_count: int = 2, limit: int = 50) -> Path:
    path = candidate_review_report_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_tag_candidates_report(root, min_count=min_count, limit=limit), encoding="utf-8")
    return path
