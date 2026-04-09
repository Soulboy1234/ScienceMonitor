from __future__ import annotations

import re
from pathlib import Path
from html import escape

try:
    import markdown as _markdown_lib
except Exception:  # pragma: no cover - optional dependency
    _markdown_lib = None


_WIKILINK_PATTERN = re.compile(r"(!)?\[\[([^\]]+)\]\]")


def render_obsidian_markdown_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return render_obsidian_markdown(text)


def render_obsidian_markdown(text: str) -> str:
    normalized = _normalize_obsidian_markdown(text)
    if _markdown_lib is not None:
        return _markdown_lib.markdown(
            normalized,
            extensions=[
                "extra",
                "fenced_code",
                "sane_lists",
                "tables",
                "nl2br",
            ],
        )
    return _render_minimal_markdown(normalized)


def _normalize_obsidian_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _strip_frontmatter(text)
    text = _WIKILINK_PATTERN.sub(_replace_wikilink, text)
    return text


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return text
    return parts[1].lstrip()


def _replace_wikilink(match: re.Match[str]) -> str:
    is_embed = bool(match.group(1))
    body = match.group(2).strip()
    if "|" in body:
        target, label = body.split("|", 1)
        display = label.strip() or target.strip()
    else:
        display = body
    display = display.replace("#", " > ")
    if is_embed:
        return f"`{display}`"
    return display


def _render_minimal_markdown(text: str) -> str:
    lines = text.splitlines()
    html_lines: list[str] = []
    paragraph: list[str] = []
    list_items: list[tuple[str, str]] = []
    in_code_block = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            html_lines.append(f"<p>{_render_inline(' '.join(part.strip() for part in paragraph if part.strip()))}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if not list_items:
            return
        current_kind = list_items[0][0]
        tag = "ol" if current_kind == "ol" else "ul"
        html_lines.append(f"<{tag}>")
        for _, value in list_items:
            html_lines.append(f"<li>{_render_inline(value)}</li>")
        html_lines.append(f"</{tag}>")
        list_items = []

    def flush_code() -> None:
        nonlocal code_lines
        html_lines.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
        code_lines = []

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code_block:
                flush_code()
            in_code_block = not in_code_block
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            html_lines.append(f"<h{level}>{_render_inline(heading_match.group(2))}</h{level}>")
            continue

        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        unordered_match = re.match(r"^[-*]\s+(.*)$", stripped)
        if ordered_match or unordered_match:
            flush_paragraph()
            kind = "ol" if ordered_match else "ul"
            value = ordered_match.group(1) if ordered_match else unordered_match.group(1)
            if list_items and list_items[0][0] != kind:
                flush_list()
            list_items.append((kind, value))
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            flush_list()
            html_lines.append(f"<blockquote><p>{_render_inline(stripped.lstrip('> ').strip())}</p></blockquote>")
            continue

        paragraph.append(stripped)

    if in_code_block:
        flush_code()
    flush_paragraph()
    flush_list()
    return "\n".join(html_lines)


def _render_inline(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"`([^`]+)`", lambda match: f"<code>{escape(match.group(1))}</code>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: f'<a href="{escape(match.group(2), quote=True)}" target="_blank" rel="noreferrer">{match.group(1)}</a>',
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    return escaped
