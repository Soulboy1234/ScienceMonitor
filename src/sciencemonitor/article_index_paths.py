from __future__ import annotations

from pathlib import Path

from .article_index_rules import detect_other_planet
from .config import (
    article_summaries_root,
    deep_reads_root,
    manual_notes_root,
    obsidian_target as configured_obsidian_target,
    output_root,
)


def iter_output_markdown_files(root: Path) -> list[Path]:
    return sorted(output_root(root).rglob("*.md"))


def iter_auto_note_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for folder in (article_summaries_root(root), deep_reads_root(root)):
        if folder.exists():
            paths.extend(sorted(folder.glob("*.md")))
    return paths


def iter_library_note_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for folder in (manual_notes_root(root), article_summaries_root(root), deep_reads_root(root)):
        if folder.exists():
            paths.extend(sorted(folder.glob("*.md")))
    return paths


def iter_manual_planet_note_paths(root: Path) -> list[Path]:
    result: list[Path] = []
    folder = manual_notes_root(root)
    if not folder.exists():
        return result
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if detect_other_planet(path.stem, text):
            result.append(path)
    return result


def obsidian_note_target(path: Path, root: Path) -> str:
    return configured_obsidian_target(path, root=root, keep_suffix=False)


def obsidian_asset_target(path: Path, root: Path) -> str:
    return configured_obsidian_target(path, root=root, keep_suffix=True)


def split_anchor(target: str) -> tuple[str, str]:
    if "#" not in target:
        return target, ""
    base, anchor = target.split("#", 1)
    return base, f"#{anchor}"


def format_wikilink(target: str, alias: str | None, bang: str = "") -> str:
    if alias:
        return f"{bang}[[{target}|{alias}]]"
    return f"{bang}[[{target}]]"


def prefix_lookup_key(stem: str) -> str:
    parts = stem.split(" - ", 2)
    if len(parts) < 3:
        return ""
    return f"prefix::{parts[0]} - {parts[1]}"


def resolve_note_target_path(target: str, library_root: Path) -> Path | None:
    raw_target = Path(target)
    if raw_target.is_absolute():
        return None
    root = library_root.resolve()
    candidate = library_root / raw_target
    normalized = candidate if target.lower().endswith(".md") else Path(f"{candidate.as_posix()}.md")
    try:
        resolved = normalized.resolve()
        resolved.relative_to(root)
    except ValueError:
        return None
    if resolved.exists():
        return resolved
    return None


def sub_index_target(page_name: str) -> str:
    return f"article_index/sub_index/{page_name}"


def is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.resolve().relative_to(other.resolve())
        return True
    except ValueError:
        return False
