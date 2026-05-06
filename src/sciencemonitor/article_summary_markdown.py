from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .config import can_delete_output_path, obsidian_target as configured_obsidian_target

if TYPE_CHECKING:
    from .models import ArticleSummaryResult


ARTICLE_SUMMARY_TEMPLATE_VAR_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
ARTICLE_SUMMARY_TEMPLATE_REQUIRED_MARKERS = (
    "- 「补充信息」",
    "- 「文中引用」",
    "- 「好句子」",
    "- 「关联报告」",
    "记录时间戳:",
)
ARTICLE_SUMMARY_TEMPLATE_REQUIRED_VARS = {
    "resource_line",
    "apa_citation",
    "body",
    "supplement",
    "references_block",
    "quotes_block",
    "related_reports_block",
    "timestamp_date",
    "timestamp_time",
}

DOI_URL_RE = re.compile(r"https://doi\.org/([^\s_]+)", re.IGNORECASE)
HASH_TAG_RE = re.compile(r"(?<!\w)#([^\s#]+)")
RELATED_REPORTS_HEADER = "- 「关联报告」"
OBSIDIAN_SAFE_TAG_CHAR_MAP = {
    "+": "＋",
    ".": "．",
    "&": "＆",
}
OBSIDIAN_SAFE_TAG_TRANSLATION = str.maketrans(OBSIDIAN_SAFE_TAG_CHAR_MAP)
OBSIDIAN_SAFE_TAG_REVERSE_TRANSLATION = str.maketrans({value: key for key, value in OBSIDIAN_SAFE_TAG_CHAR_MAP.items()})


def obsidian_target(path: Path, root: Path | None = None) -> str:
    return configured_obsidian_target(path, root=root, keep_suffix=False)


def obsidian_link(path: Path, label: str, root: Path | None = None) -> str:
    return f"[[{obsidian_target(path, root=root)}|{label}]]"


def sync_summary_report_links(
    summaries: list["ArticleSummaryResult"],
    report_path: Path,
    root: Path | None = None,
) -> None:
    report_label = report_path.stem if report_path.stem.endswith("周报") else f"{report_path.stem} 周报"
    report_link = obsidian_link(report_path, report_label, root=root)
    for summary in summaries:
        path = summary.output_path
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        updated = upsert_related_reports_section(original, [report_link])
        if updated != original:
            path.write_text(updated, encoding="utf-8")


def upsert_related_reports_section(markdown: str, report_links: list[str]) -> str:
    normalized = dedupe(report_links)
    if not normalized:
        return markdown

    existing_links = extract_related_report_links(markdown)
    all_links = dedupe(existing_links + normalized)
    block_lines = [RELATED_REPORTS_HEADER, build_numbered_block(all_links)]
    block = "\n".join(block_lines)

    pattern = re.compile(
        r"(?ms)^- 「关联报告」\n(?:\t\d+\.\s.*\n?)*"
    )
    if pattern.search(markdown):
        return pattern.sub(block, markdown, count=1)

    marker = "\n\n----\n记录时间戳:"
    if marker in markdown:
        return markdown.replace(marker, f"\n{block}{marker}", 1)
    return markdown.rstrip() + f"\n\n{block}\n"


def extract_related_report_links(markdown: str) -> list[str]:
    pattern = re.compile(r"(?ms)^- 「关联报告」\n((?:\t\d+\.\s.*\n?)*)")
    match = pattern.search(markdown)
    if not match:
        return []
    return [item.strip() for item in re.findall(r"\[\[[^\]]+\]\]", match.group(1))]


def extract_summary_doi(markdown: str) -> str:
    match = DOI_URL_RE.search(markdown)
    if not match:
        return ""
    return normalize_doi(match.group(1))


def index_existing_summary_files(output_dir: Path, *, root: Path | None = None) -> dict[str, Path]:
    grouped: dict[str, list[Path]] = {}
    if not output_dir.exists():
        return {}
    for path in output_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        doi = extract_summary_doi(text)
        if not doi:
            continue
        grouped.setdefault(doi, []).append(path)

    indexed: dict[str, Path] = {}
    for doi, candidates in grouped.items():
        canonical = max(candidates, key=lambda item: (item.stat().st_mtime_ns, item.name))
        indexed[doi] = canonical
        for duplicate in candidates:
            if duplicate == canonical:
                continue
            if can_delete_output_path(duplicate, root):
                duplicate.unlink(missing_ok=True)
    return indexed


def render_article_summary_markdown(
    template_text: str,
    *,
    note_title: str,
    resource_line: str,
    apa_citation: str,
    body: str,
    supplement: str,
    related_reports_block: str,
    now: datetime | None = None,
) -> str:
    current_time = now or datetime.now()
    return render_article_summary_template(
        template_text,
        {
            "note_title": note_title,
            "resource_line": resource_line,
            "apa_citation": apa_citation,
            "body": body,
            "supplement": supplement,
            "references_block": build_numbered_block([]),
            "quotes_block": build_numbered_block([]),
            "related_reports_block": related_reports_block,
            "timestamp_date": current_time.strftime("%Y-%m-%d"),
            "timestamp_time": current_time.strftime("%H:%M:%S"),
            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


def extract_line_value(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
        if line.startswith(f"- {prefix}"):
            return line[len(f"- {prefix}"):].strip()
    return ""


def extract_summary_tags(text: str) -> list[str]:
    for line in text.splitlines():
        if line.startswith("- ") and "#" in line:
            return [decode_obsidian_tag(item) for item in HASH_TAG_RE.findall(line)]
        if line.startswith("- 标签："):
            return [decode_obsidian_tag(item.lstrip("#")) for item in line.split() if item.startswith("#")]
    return []


def extract_summary_body(text: str) -> str:
    lines = text.splitlines()
    if "题目：" in text:
        return extract_section_text(text, "- 正文内容")
    citation_index = -1
    for index, line in enumerate(lines):
        if line.startswith("- _") and line.endswith("_"):
            citation_index = index
            break
    if citation_index == -1:
        return ""
    for follow in lines[citation_index + 1:]:
        stripped = follow.strip()
        if not stripped:
            continue
        if stripped.startswith("- 「"):
            break
        if stripped.startswith("- "):
            return stripped[2:].strip()
    for follow in lines:
        stripped = follow.strip()
        if not stripped or not stripped.startswith("- "):
            continue
        if stripped.startswith("- _"):
            continue
        if "[DOI](" in stripped or "](https://" in stripped or stripped.startswith("- [["):
            continue
        if stripped.startswith("- 「"):
            continue
        return stripped[2:].strip()
    return ""


def extract_section_text(text: str, header: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == header and index + 1 < len(lines):
            return lines[index + 1].strip().lstrip("1.").strip()
    return ""


def extract_numbered_line(text: str, header: str) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(header)}\n\t1\.\s*(.*?)(?:\n-\s「|\n\n----|\Z)")
    match = pattern.search(text)
    if not match:
        return ""
    value = match.group(1).strip()
    next_line = value.splitlines()[0].strip()
    return next_line


def load_article_summary_template(template_path: Path) -> str:
    template_text = template_path.read_text(encoding="utf-8")
    validate_article_summary_template(template_text, template_path)
    return template_text


def validate_article_summary_template(template_text: str, template_path: Path) -> None:
    variables = set(ARTICLE_SUMMARY_TEMPLATE_VAR_RE.findall(template_text))
    missing_vars = ARTICLE_SUMMARY_TEMPLATE_REQUIRED_VARS - variables
    if missing_vars:
        missing = ", ".join(sorted(missing_vars))
        raise ValueError(f"Article summary template missing required placeholders in {template_path}: {missing}")

    missing_markers = [marker for marker in ARTICLE_SUMMARY_TEMPLATE_REQUIRED_MARKERS if marker not in template_text]
    if missing_markers:
        missing = ", ".join(missing_markers)
        raise ValueError(f"Article summary template missing required section markers in {template_path}: {missing}")


def render_article_summary_template(template_text: str, context: dict[str, str]) -> str:
    missing = set(ARTICLE_SUMMARY_TEMPLATE_VAR_RE.findall(template_text)) - set(context)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Article summary render context missing placeholders: {missing_text}")

    rendered = template_text
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def build_numbered_block(items: list[str], empty_text: str = "暂留空。") -> str:
    values = [item for item in items if str(item).strip()]
    if not values:
        values = [empty_text]
    return "\n".join(f"\t{index}. {item}" for index, item in enumerate(values, start=1))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clean_source_text(text: str) -> str:
    lines = [clean_text(line) for line in str(text or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def normalize_doi(value: str) -> str:
    return clean_text(value).lower().rstrip(").,;")


def sanitize_filename(text: str) -> str:
    clean = re.sub(r"[\\/:*?\"<>|]+", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "untitled"


def encode_obsidian_tag(tag: str) -> str:
    compact = re.sub(r"\s+", "", str(tag or ""))
    return compact.translate(OBSIDIAN_SAFE_TAG_TRANSLATION)


def decode_obsidian_tag(tag: str) -> str:
    compact = re.sub(r"\s+", "", str(tag or ""))
    return compact.translate(OBSIDIAN_SAFE_TAG_REVERSE_TRANSLATION)


def format_tag(tag: str) -> str:
    return "#" + encode_obsidian_tag(tag)


def build_tag_line(tags: list[str]) -> str:
    return " ".join(format_tag(tag) for tag in tags)


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
