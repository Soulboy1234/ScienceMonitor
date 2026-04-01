from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import (
    article_index_root,
    article_sub_index_root,
    article_summaries_root,
    data_root,
    deep_reads_root,
    manual_notes_root,
    obsidian_target as configured_obsidian_target,
    output_root,
    output_relative_path,
    project_root,
)


WIKILINK_RE = re.compile(r"(!)?\[\[(.+?)(?:\|([^\]]+))?\]\]")
NUMBERED_LINK_RE = re.compile(r"^(\d+)\.\s+(\[\[[^\]]+\]\])\s*$")
ORPHAN_NUMBER_RE = re.compile(r"^\d+\.\s*$")
DOI_URL_RE = re.compile(r"https://doi\.org/([^\s_)]+)", re.IGNORECASE)
OTHER_PLANET_TAG_RE = re.compile(r"(?<!\w)#其他行星/[^\s#]+")
ASSET_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".avi",
    ".mp4",
    ".mov",
    ".m4v",
    ".csv",
    ".tsv",
    ".json",
    ".txt",
}
PLANETARY_ROOT_PAGE = "6 - 其他行星"
PLANETARY_FOCUS_PAGES = {"7 - 太阳与日球层", "8 - 波粒相互作用", "9 - 高能粒子与辐射带"}
EARTH_SECTION_PREFIXES = ("1", "2", "3", "4")

INDEX_TREE: list[tuple[str, list]] = [
    ("1 - 空间环境", ["1.1 - 行星际磁场影响", "1.2 - 空间环境指数", "1.3 - 应用"]),
    (
        "2 - 热层电离层耦合系统",
        [
            "2.1 - 综述",
            "2.2 - 热层数据",
            "2.3 - 热层建模",
            "2.4 - 空间天气事件的影响",
            "2.5 - 太阳辐射影响",
            "2.6 - 磁暴",
            "2.7 - TAD与TID",
            "2.8 - 耀斑",
            "2.9 - EMA & ETA",
            ("2.10 - 经度结构", ["2.10.1 - 四波结构", "2.10.2 - 经度差异", "2.10.3 - X-Pattern"]),
            "2.11 - 赤道电场",
            "2.12 - 电动力学",
            "2.13 - 极尖区密度小尺度特征",
            "2.14 - 长期趋势",
            "2.15 - 赤道超旋",
            "2.16 - 极光",
            "2.17 - 南北半球差异",
            "2.18 - Day-to-Day",
            "2.19 - 全球同步响应",
            "2.20 - 极区粒子沉降",
            "2.21 - 伺服理论",
            "2.22 - 潮汐",
            "2.23 - 热层风",
            "2.24 - 极区对流",
            "2.25 - CIR",
            "2.26 - 热层中小尺度结构",
        ],
    ),
    ("3 - 临近空间", ["3.1 - 行星波"]),
    ("4 - 磁层", ["4.1 - 磁尾", "4.2 - 磁重联", "4.3 - 磁层-电离层-热层耦合", "4.4 - 磁层顶"]),
    ("5 - 图书", []),
    (
        PLANETARY_ROOT_PAGE,
        [
            "6.1 - 月球",
            "6.2 - 水星",
            "6.3 - 金星",
            ("6.4 - 火星", ["6.4.1 - 行星际环境的影响"]),
            "6.5 - 木星",
            "6.6 - 土星",
            "6.7 - 天王星",
            "6.8 - 海王星",
            "6.9 - 行星综合",
        ],
    ),
    ("7 - 太阳与日球层", []),
    ("8 - 波粒相互作用", []),
    ("9 - 高能粒子与辐射带", []),
    ("10 - 科学趣闻", []),
]

LEGACY_PAGE_RENAMES = {
    "6 - 火星": "6.4 - 火星",
    "6.1 - 行星际环境的影响": "6.4.1 - 行星际环境的影响",
    "7 - 科学趣闻": "10 - 科学趣闻",
    "太阳与日球层": "7 - 太阳与日球层",
    "波粒相互作用": "8 - 波粒相互作用",
    "高能粒子与辐射带": "9 - 高能粒子与辐射带",
    "行星空间环境": "6.9 - 行星综合",
}

PLANET_PAGE_MAP = {
    "月球": "6.1 - 月球",
    "水星": "6.2 - 水星",
    "金星": "6.3 - 金星",
    "火星": "6.4 - 火星",
    "木星": "6.5 - 木星",
    "土星": "6.6 - 土星",
    "天王星": "6.7 - 天王星",
    "海王星": "6.8 - 海王星",
    "行星综合": "6.9 - 行星综合",
}

PLANET_TAG_MAP = {planet: f"其他行星/{planet}" for planet in PLANET_PAGE_MAP}
PLANETARY_PAGE_NAMES = set(PLANET_PAGE_MAP.values()) | {"6.4.1 - 行星际环境的影响"}
DISPLAY_STATUS_SUFFIX_RE = re.compile(r"\s*-\s*(重要|Todo|TODO|待读|待读|待整理|可做)$")

PLANET_KEYWORDS = {
    "月球": ["研究星球/月球", " lunar ", " moon ", "月球", "danuri", "kplo", "chang’e", "chang'e"],
    "水星": ["研究星球/水星", " mercury ", " mercurian ", "水星"],
    "金星": ["研究星球/金星", " venus ", " venusian ", "金星"],
    "火星": ["研究星球/火星", " mars ", " martian ", "火星", "nozomi"],
    "木星": ["研究星球/木星", " jupiter ", " jovian ", "木星", "ganymede", "木卫三", "europa", "木卫二"],
    "土星": ["研究星球/土星", " saturn ", " saturnian ", "土星", "titan", "土卫六", "enceladus", "土卫二"],
    "天王星": ["研究星球/天王星", " uranus ", " uranian ", "天王星"],
    "海王星": ["研究星球/海王星", " neptune ", " neptunian ", "海王星"],
}

PLANETARY_GENERIC_KEYWORDS = ["研究星球/行星综合", "多行星", "multi-planet", "multi planet", "行星比较", "行星综合"]

KEYWORD_PAGE_RULES: list[tuple[str, list[str]]] = [
    ("9 - 高能粒子与辐射带", ["radiation belt", "辐射带", "solar energetic particle", "太阳高能粒子", "gcr", "energetic particle", "高能粒子", "俘获电子", "俘获质子"]),
    ("8 - 波粒相互作用", ["wave-particle", "波粒相互作用", "chorus", "whistler", "ulf wave", "electron conic"]),
    ("7 - 太阳与日球层", ["solar wind", "太阳风", "interplanetary", "行星际", "heliosphere", "日球层", "icme", "cme"]),
    ("2.20 - 极区粒子沉降", ["电子沉降", "粒子沉降", "electron precipitation", "particle precipitation", "nitric oxide", "no cooling"]),
    ("2.16 - 极光", ["极光", "aurora", "auroral oval", "pulsating aurora"]),
    ("2.24 - 极区对流", ["极区对流", "polar convection", "cross polar cap potential", "cpcp", "polar cap convection", "hmb"]),
    ("2.23 - 热层风", ["热层风", "thermospheric wind", "neutral wind", "zonal wind", "meridional wind", "vertical wind"]),
    ("2.22 - 潮汐", ["潮汐", "tide", "tidal"]),
    ("2.7 - TAD与TID", ["tad", "tid", "traveling atmospheric disturbance", "traveling ionospheric disturbance", "mstid"]),
    ("2.9 - EMA & ETA", ["equatorial ionization anomaly", "赤道电离异常", "equatorial mass density anomaly", "equatorial thermosphere anomaly", "赤道质量密度异常", "赤道热层异常", "喷泉", "fountain"]),
    ("2.10.3 - X-Pattern", ["x-pattern"]),
    ("2.10.2 - 经度差异", ["经度", "longitude", "longitudinal", "sector"]),
    ("2.11 - 赤道电场", ["赤道电场", "equatorial electric field", "vertical drift", "prompt penetration", "e×b drift"]),
    ("2.12 - 电动力学", ["电动力学", "electrodynamic", "electric field", "plasma drift", "fac", "field aligned current"]),
    ("2.17 - 南北半球差异", ["南北半球", "hemispheric", "north-south", "asymmetry"]),
    ("2.18 - Day-to-Day", ["day-to-day", "day to day", "quiet-time variability"]),
    ("2.25 - CIR", ["corotating", "cir", "high-speed stream", "coronal hole"]),
    ("2.6 - 磁暴", ["磁暴", "geomagnetic storm", "storm-time", "gannon storm", "superstorm"]),
    ("2.8 - 耀斑", ["solar flare", "耀斑", "soft x-ray flare"]),
    ("2.5 - 太阳辐射影响", ["solar irradiance", "euv", "solar radiation", "eclipse", "x-ray"]),
    ("4.2 - 磁重联", ["磁重联", "reconnection", "parallel electric field", "bbf"]),
    ("4.4 - 磁层顶", ["magnetopause", "磁层顶", "magnetosheath", "bow shock", "kelvin-helmholtz", "kh vortex"]),
    ("4.1 - 磁尾", ["magnetotail", "磁尾", "plasma sheet", "tail current sheet"]),
    ("4.3 - 磁层-电离层-热层耦合", ["磁层-电离层-热层耦合", "substorm current wedge", "field aligned current", "ionosphere-thermosphere coupling"]),
    ("3.1 - 行星波", ["planetary wave", "gravity wave", "secondary gravity wave", "ssw"]),
    ("1.2 - 空间环境指数", ["dst", "sym-h", "kp", "ae", "au", "al"]),
    ("1.3 - 应用", ["satellite drag", "轨道", "operational", "forecast", "prediction", "业务化"]),
    ("1.1 - 行星际磁场影响", ["imf", "solar wind", "interplanetary", "icme", "cme", "heliosphere"]),
]

TOPIC_FALLBACK_PAGES = {
    "行星际环境驱动": "1.1 - 行星际磁场影响",
    "空间天气": "2.4 - 空间天气事件的影响",
    "电离层": "2 - 热层电离层耦合系统",
    "热层": "2 - 热层电离层耦合系统",
    "低层大气波动上传": "3 - 临近空间",
    "磁层": "4 - 磁层",
    "磁层-电离层-热层耦合": "4.3 - 磁层-电离层-热层耦合",
    "太阳与日球层": "7 - 太阳与日球层",
    "波粒相互作用": "8 - 波粒相互作用",
    "高能粒子与辐射带": "9 - 高能粒子与辐射带",
    "行星空间环境": "6.9 - 行星综合",
}

PARENT_PAGE_RULES = {
    "2 - 热层电离层耦合系统": "2.",
    "4 - 磁层": "4.",
    "3 - 临近空间": "3.",
    PLANETARY_ROOT_PAGE: "6.",
    "6.4 - 火星": "6.4.",
}


@dataclass(frozen=True)
class LibrarySyncResult:
    repaired_files: int = 0
    repaired_links: int = 0
    indexed_notes: int = 0
    created_sub_indexes: int = 0


def sync_out_library(root: Path | None = None) -> LibrarySyncResult:
    project = root or project_root()
    created_sub_indexes = migrate_legacy_sub_index_files(project)
    created_sub_indexes += ensure_index_tree_files(project)
    render_index_file(project)
    ensure_parent_page_links(project)

    note_map = build_note_map(project)
    asset_map = build_asset_map(project)

    repaired_files = 0
    repaired_links = 0
    for path in iter_output_markdown_files(project):
        original = path.read_text(encoding="utf-8", errors="ignore")
        updated, replacements = repair_markdown_links(
            markdown=original,
            note_map=note_map,
            asset_map=asset_map,
            root=project,
            skip_asset_links=False,
        )
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            repaired_files += 1
        repaired_links += replacements

    for note_path in iter_library_note_paths(project):
        if normalize_other_planet_tag(note_path):
            repaired_files += 1

    for page_path in sorted(article_sub_index_root(project).glob("*.md")):
        remove_auto_links(page_path, project)

    remove_planet_links_from_earth_sections(project, note_map)
    remove_misplaced_note_links_from_planet_pages(project)

    indexed_notes = 0
    for note_path in sorted(iter_auto_note_paths(project)):
        page_names = infer_sub_index_pages(note_path, project)
        if not page_names:
            continue
        indexed_notes += 1
        for page_name in page_names:
            page_path, created = ensure_sub_index_page(page_name, project)
            if created:
                created_sub_indexes += 1
            upsert_note_link(page_path, note_path, project)

    for note_path in sorted(iter_manual_planet_note_paths(project)):
        for page_name in infer_sub_index_pages(note_path, project):
            page_path, created = ensure_sub_index_page(page_name, project)
            if created:
                created_sub_indexes += 1
            upsert_note_link(page_path, note_path, project)

    return LibrarySyncResult(
        repaired_files=repaired_files,
        repaired_links=repaired_links,
        indexed_notes=indexed_notes,
        created_sub_indexes=created_sub_indexes,
    )


def migrate_legacy_sub_index_files(root: Path) -> int:
    created = 0
    sub_index_dir = article_sub_index_root(root)
    sub_index_dir.mkdir(parents=True, exist_ok=True)
    for source_name, target_name in LEGACY_PAGE_RENAMES.items():
        source = sub_index_dir / f"{source_name}.md"
        target = sub_index_dir / f"{target_name}.md"
        if not source.exists():
            continue
        if not target.exists():
            source.rename(target)
            created += 1
            continue
        if source.read_text(encoding="utf-8", errors="ignore").strip() and not target.read_text(encoding="utf-8", errors="ignore").strip():
            target.write_text(source.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
        source.unlink()
    return created


def ensure_index_tree_files(root: Path) -> int:
    created = 0
    for page_name in all_tree_page_names():
        page_path = article_sub_index_root(root) / f"{page_name}.md"
        if page_path.exists():
            continue
        page_path.write_text("", encoding="utf-8")
        created += 1
    return created


def ensure_parent_page_links(root: Path) -> None:
    child_map = build_child_page_map()
    for page_name, child_pages in child_map.items():
        page_path = article_sub_index_root(root) / f"{page_name}.md"
        original = page_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "")
        child_lines = [f"- [[{sub_index_target(child)}|{child}]]" for child in child_pages]

        body_lines = []
        for line in original.splitlines():
            stripped = line.strip()
            if stripped in child_lines:
                continue
            if stripped.startswith("- [[article_index/sub_index/"):
                continue
            body_lines.append(line)
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        updated_lines = list(child_lines)
        if body_lines:
            updated_lines.append("")
            updated_lines.extend(body_lines)
        updated = "\n".join(updated_lines).rstrip() + "\n"
        if updated != original:
            page_path.write_text(updated, encoding="utf-8")


def render_index_file(root: Path) -> None:
    index_path = article_index_root(root) / "index.md"
    lines = render_index_tree(INDEX_TREE)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def render_index_tree(tree: list[tuple[str, list]], depth: int = 0) -> list[str]:
    lines: list[str] = []
    indent = "\t" * depth
    for page_name, children in tree:
        lines.append(f"{indent}- [[{sub_index_target(page_name)}|{page_name}]]")
        for child in children:
            if isinstance(child, tuple):
                lines.extend(render_index_tree([child], depth + 1))
            else:
                lines.append(f"{indent}\t- [[{sub_index_target(child)}|{child}]]")
    return lines


def build_child_page_map() -> dict[str, list[str]]:
    child_map: dict[str, list[str]] = {}
    for page_name, children in INDEX_TREE:
        child_map[page_name] = [child[0] if isinstance(child, tuple) else child for child in children]
        for child in children:
            if isinstance(child, tuple):
                child_map[child[0]] = list(child[1])
    return child_map


def all_tree_page_names() -> list[str]:
    names: list[str] = []
    for page_name, children in INDEX_TREE:
        names.append(page_name)
        for child in children:
            if isinstance(child, tuple):
                names.append(child[0])
                names.extend(child[1])
            else:
                names.append(child)
    return names


def build_note_map(root: Path) -> dict[str, Path]:
    note_map: dict[str, Path] = {}
    duplicates: set[str] = set()
    library_root = output_root(root)
    if not library_root.exists():
        return note_map

    def register(key: str, path: Path) -> None:
        if not key or key in duplicates:
            return
        existing = note_map.get(key)
        if existing and existing != path:
            note_map.pop(key, None)
            duplicates.add(key)
            return
        note_map[key] = path

    for path in library_root.rglob("*.md"):
        if ".venv" in path.parts:
            continue
        stem = path.stem
        register(stem, path)
        register(prefix_lookup_key(stem), path)
    return note_map


def build_asset_map(root: Path) -> dict[str, Path]:
    assets: dict[str, Path] = {}
    duplicates: set[str] = set()

    def register(key: str, path: Path) -> None:
        if not key or key in duplicates:
            return
        existing = assets.get(key)
        if existing and existing != path:
            assets.pop(key, None)
            duplicates.add(key)
            return
        assets[key] = path

    for path in output_root(root).rglob("*"):
        if not path.is_file() or path.suffix.lower() == ".md":
            continue
        register(path.name, path)
        register(normalize_asset_lookup_key(path.name), path)
    return assets


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


def repair_markdown_links(
    markdown: str,
    note_map: dict[str, Path],
    asset_map: dict[str, Path],
    root: Path,
    skip_asset_links: bool,
) -> tuple[str, int]:
    cleaned = markdown.replace("\x00", "")
    replacements = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements
        bang = match.group(1) or ""
        raw_target = match.group(2).strip()
        alias = match.group(3)
        target, anchor = split_anchor(raw_target)
        suffix = Path(target).suffix.lower()
        basename = Path(target).name
        stem = link_stem(target)

        if suffix not in ASSET_EXTENSIONS or suffix == ".md":
            canonical_path = note_map.get(stem) or note_map.get(prefix_lookup_key(stem))
            if not canonical_path:
                return match.group(0)
            canonical = obsidian_note_target(canonical_path, root) + anchor
            display_alias = build_display_alias(canonical, alias)
            if canonical == raw_target and display_alias == alias:
                return match.group(0)
            replacements += 1
            return format_wikilink(canonical, display_alias, bang=bang)

        if skip_asset_links or suffix not in ASSET_EXTENSIONS:
            return match.group(0)

        canonical_asset = asset_map.get(basename) or asset_map.get(normalize_asset_lookup_key(basename))
        if not canonical_asset:
            return match.group(0)
        canonical = obsidian_asset_target(canonical_asset, root) + anchor
        if canonical == raw_target and alias:
            return match.group(0)
        replacements += 1
        return format_wikilink(canonical, alias, bang=bang)

    return WIKILINK_RE.sub(replace, cleaned), replacements


def normalize_other_planet_tag(note_path: Path) -> bool:
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    planet = detect_other_planet(note_path.stem, text)
    desired_tag = f"#{PLANET_TAG_MAP[planet]}" if planet else None
    updated = OTHER_PLANET_TAG_RE.sub("", text)

    lines = updated.splitlines()
    for index, line in enumerate(lines):
        if "#" not in line:
            continue
        if not (line.startswith("- ") or line.startswith("- 标签：")):
            continue
        cleaned_line = re.sub(r"\s{2,}", " ", line).rstrip()
        if desired_tag and desired_tag not in cleaned_line.split():
            cleaned_line = cleaned_line.rstrip() + f" {desired_tag}"
        lines[index] = cleaned_line
        break

    updated = "\n".join(lines)
    updated = re.sub(r" +\n", "\n", updated).rstrip() + "\n"
    if updated == text:
        return False
    note_path.write_text(updated, encoding="utf-8")
    return True


def detect_other_planet(note_title: str, text: str) -> str | None:
    haystack = build_planet_detection_haystack(note_title, text)
    matches = []
    for planet, keywords in PLANET_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            matches.append(planet)
    matches = dedupe(matches)
    if len(matches) > 1:
        return "行星综合"
    if len(matches) == 1:
        return matches[0]
    if any(keyword.lower() in haystack for keyword in PLANETARY_GENERIC_KEYWORDS):
        return "行星综合"
    return None


def infer_sub_index_pages(note_path: Path, root: Path) -> list[str]:
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    planet = detect_other_planet(note_path.stem, text)
    if planet:
        return infer_planetary_pages(note_path.stem, text, planet)

    explicit = extract_directory_hints(text)
    if explicit:
        return explicit[:3]

    doi_topics = load_doi_topics(root)
    doi = extract_doi(text)
    topic_labels = doi_topics.get(doi, [])

    haystack = normalize_haystack(f"{note_path.stem}\n{text}")
    pages: list[str] = []
    for page_name, keywords in KEYWORD_PAGE_RULES:
        if any(keyword.lower() in haystack for keyword in keywords):
            pages.append(page_name)
    if not pages:
        for label in topic_labels:
            mapped = TOPIC_FALLBACK_PAGES.get(label)
            if mapped:
                pages.append(mapped)

    pages = prune_parent_pages(dedupe(pages))
    return pages[:3]


def infer_planetary_pages(note_title: str, text: str, planet: str) -> list[str]:
    haystack = normalize_haystack(f"{note_title}\n{text}")
    pages = [PLANET_PAGE_MAP[planet]]

    if planet == "火星" and any(keyword in haystack for keyword in ["interplanetary", "行星际", "solar wind", "太阳风"]):
        pages.append("6.4.1 - 行星际环境的影响")
    if any(keyword.lower() in haystack for keyword in ["radiation belt", "辐射带", "solar energetic particle", "太阳高能粒子", "gcr", "高能粒子"]):
        pages.append("9 - 高能粒子与辐射带")
    if any(keyword.lower() in haystack for keyword in ["wave-particle", "波粒相互作用", "chorus", "whistler", "ulf wave", "electron conic"]):
        pages.append("8 - 波粒相互作用")
    if any(keyword.lower() in haystack for keyword in ["solar wind", "太阳风", "interplanetary", "行星际", "heliosphere", "日球层", "icme", "cme"]):
        pages.append("7 - 太阳与日球层")
    if planet == "行星综合":
        pages.append("6.9 - 行星综合")

    return dedupe(pages)[:3]


def load_doi_topics(root: Path) -> dict[str, list[str]]:
    if hasattr(load_doi_topics, "_cache"):
        cached_root, cached_value = getattr(load_doi_topics, "_cache")
        if cached_root == root:
            return cached_value

    mapping: dict[str, list[str]] = {}
    db_path = data_root(root) / "science_monitor.db"
    if db_path.exists():
        connection = sqlite3.connect(db_path)
        try:
            rows = connection.execute("select doi, topic_labels from papers where doi is not null and doi != ''")
            for doi, topic_labels in rows:
                normalized = normalize_doi(doi)
                if normalized:
                    mapping[normalized] = [item for item in str(topic_labels or "").split("\n") if item]
        finally:
            connection.close()

    setattr(load_doi_topics, "_cache", (root, mapping))
    return mapping


def extract_directory_hints(text: str) -> list[str]:
    pages: list[str] = []
    for line in text.splitlines():
        if "目录归档建议" not in line:
            continue
        for match in WIKILINK_RE.finditer(line):
            target = match.group(2).strip()
            target, _ = split_anchor(target)
            pages.append(link_stem(target))
    return dedupe(pages)


def extract_doi(text: str) -> str:
    match = DOI_URL_RE.search(text)
    if not match:
        return ""
    return normalize_doi(match.group(1))


def ensure_sub_index_page(page_name: str, root: Path) -> tuple[Path, bool]:
    page_path = article_sub_index_root(root) / f"{page_name}.md"
    if page_path.exists():
        return page_path, False
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text("", encoding="utf-8")
    return page_path, True


def remove_auto_links(page_path: Path, root: Path) -> None:
    remove_matching_note_links(
        page_path,
        lambda target_path, _note_path, _note_text: "auto/article_summaries/" in target_path
        or "auto/deep_reads/" in target_path,
        library_root=output_root(root),
        numbered_only=True,
    )


def remove_planet_links_from_earth_sections(root: Path, note_map: dict[str, Path]) -> None:
    for page_path in sorted(article_sub_index_root(root).glob("*.md")):
        page_name = page_path.stem
        if not is_earth_specific_page(page_name):
            continue
        remove_matching_note_links(
            page_path,
            lambda _target_path, note_path, note_text: bool(note_path and detect_other_planet(note_path.stem, note_text)),
            library_root=output_root(root),
            numbered_only=True,
        )


def remove_misplaced_note_links_from_planet_pages(root: Path) -> None:
    for page_name in sorted(PLANETARY_PAGE_NAMES):
        page_path = article_sub_index_root(root) / f"{page_name}.md"
        if not page_path.exists():
            continue
        remove_matching_note_links(
            page_path,
            lambda _target_path, note_path, _note_text: bool(note_path and page_name not in infer_sub_index_pages(note_path, root)),
            library_root=output_root(root),
            numbered_only=True,
        )


def remove_matching_note_links(page_path: Path, predicate, library_root: Path, numbered_only: bool = False) -> None:
    original = page_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "")
    lines = original.splitlines()
    kept_lines: list[str] = []
    changed = False
    for line in lines:
        if numbered_only and not NUMBERED_LINK_RE.match(line.strip()):
            kept_lines.append(line)
            continue
        match = WIKILINK_RE.search(line)
        if not match:
            kept_lines.append(line)
            continue
        target = match.group(2).strip()
        target, _ = split_anchor(target)
        note_path = resolve_note_target_path(target, library_root=library_root)
        note_text = ""
        if note_path and note_path.exists():
            note_text = note_path.read_text(encoding="utf-8", errors="ignore")
        if predicate(target, note_path, note_text):
            changed = True
            continue
        kept_lines.append(line)
    if not changed:
        return
    page_path.write_text(renumber_link_blocks(kept_lines), encoding="utf-8")


def upsert_note_link(page_path: Path, note_path: Path, root: Path) -> bool:
    target = obsidian_note_target(note_path, root)
    label = prettify_display_label(note_path.stem)
    link = f"[[{target}|{label}]]"
    original = page_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "") if page_path.exists() else ""
    if link in original or f"[[{label}]]" in original or f"|{label}]]" in original:
        return False
    updated = insert_numbered_link(original, link)
    if updated != original:
        page_path.write_text(updated, encoding="utf-8")
        return True
    return False


def insert_numbered_link(markdown: str, link: str) -> str:
    stripped = markdown.rstrip()
    if not stripped:
        return f"1. {link}\n"

    lines = stripped.splitlines()
    numbered_indices = [index for index, line in enumerate(lines) if NUMBERED_LINK_RE.match(line.strip())]
    if not numbered_indices:
        separator = "\n\n" if stripped else ""
        return stripped + separator + f"1. {link}\n"

    if is_simple_numbered_page(lines):
        entries = [NUMBERED_LINK_RE.match(line.strip()).group(2) for line in lines if NUMBERED_LINK_RE.match(line.strip())]
        entries.append(link)
        entries = sorted(entries, key=lambda item: (extract_year_from_link(item), item))
        return "\n".join(f"{index}. {item}" for index, item in enumerate(entries, start=1)) + "\n"

    next_number = max(int(NUMBERED_LINK_RE.match(lines[index].strip()).group(1)) for index in numbered_indices) + 1
    insert_at = numbered_indices[-1] + 1
    lines.insert(insert_at, f"{next_number}. {link}")
    return "\n".join(lines) + "\n"


def is_simple_numbered_page(lines: list[str]) -> bool:
    meaningful = [line.strip() for line in lines if line.strip()]
    return bool(meaningful) and all(NUMBERED_LINK_RE.match(line) for line in meaningful)


def renumber_link_blocks(lines: list[str]) -> str:
    rewritten: list[str] = []
    block: list[str] = []
    for line in lines:
        match = NUMBERED_LINK_RE.match(line.strip())
        if match:
            block.append(match.group(2))
            continue
        if ORPHAN_NUMBER_RE.match(line.strip()):
            continue
        if block:
            rewritten.extend(f"{index}. {item}" for index, item in enumerate(block, start=1))
            block = []
        rewritten.append(line)
    if block:
        rewritten.extend(f"{index}. {item}" for index, item in enumerate(block, start=1))
    return "\n".join(rewritten).rstrip() + "\n"


def prune_parent_pages(page_names: list[str]) -> list[str]:
    refined = list(page_names)
    for parent, prefix in PARENT_PAGE_RULES.items():
        if parent in refined and any(item != parent and item.startswith(prefix) for item in refined):
            refined.remove(parent)
    return refined


def is_earth_specific_page(page_name: str) -> bool:
    return page_name.split(" - ", 1)[0].split(".", 1)[0] in EARTH_SECTION_PREFIXES


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


def build_display_alias(target: str, alias: str | None) -> str | None:
    if "/" not in target and alias is None:
        return None
    label = alias or link_stem(target)
    return prettify_display_label(label)


def prettify_display_label(label: str) -> str:
    cleaned = DISPLAY_STATUS_SUFFIX_RE.sub("", label.strip())
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def build_planet_detection_haystack(note_title: str, text: str) -> str:
    selected = [note_title]
    kept = 0
    for raw_line in text.replace("\x00", "").splitlines():
        line = raw_line.strip()
        if not line or line == "----":
            continue
        if line.startswith("记录时间戳"):
            break
        if "「补充信息」" in line:
            break
        line = OTHER_PLANET_TAG_RE.sub("", line)
        line = re.sub(r"\[\[[^\]]+\]\]", " ", line)
        selected.append(line)
        kept += 1
        if kept >= 4:
            break
    return normalize_haystack("\n".join(selected))


def normalize_haystack(text: str) -> str:
    compact = re.sub(r"\s+", " ", text or "")
    return f" {compact.lower()} "


def normalize_asset_lookup_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").lower()
    normalized = (
        normalized.replace("–", "-")
        .replace("—", "-")
        .replace("‐", "-")
        .replace("‑", "-")
        .replace("−", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("‘", "'")
        .replace("[r-qucik]", "[r-quick]")
        .replace("_withmarginnotes", "")
        .replace("withmarginnotes", "")
        .replace("[", "")
        .replace("]", "")
    )
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s+\.", ".", normalized)
    return normalized.strip()


def normalize_doi(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower().rstrip(").,;")


def extract_year(text: str) -> int:
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return int(match.group(0)) if match else 9999


def extract_year_from_link(link: str) -> int:
    match = WIKILINK_RE.search(link)
    if not match:
        return 9999
    alias = match.group(3) or link_stem(match.group(2))
    return extract_year(alias)


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item and item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def link_stem(target: str) -> str:
    name = Path(target).name
    return name[:-3] if name.lower().endswith(".md") else name


def prefix_lookup_key(stem: str) -> str:
    parts = stem.split(" - ", 2)
    if len(parts) < 3:
        return ""
    return f"prefix::{parts[0]} - {parts[1]}"


def resolve_note_target_path(target: str, library_root: Path) -> Path | None:
    candidate = library_root / target
    if target.lower().endswith(".md"):
        normalized = candidate
    else:
        normalized = Path(f"{candidate.as_posix()}.md")
    if normalized.exists():
        return normalized
    return None


def sub_index_target(page_name: str) -> str:
    return f"article_index/sub_index/{page_name}"


def is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.resolve().relative_to(other.resolve())
        return True
    except ValueError:
        return False
