from __future__ import annotations

import re
from pathlib import Path
from sqlite3 import Row

from .article_summary_markdown import build_tag_line, clean_text, normalize_doi, sanitize_filename
from .utils import clean_title_text


SPECIAL_PAPER_OVERRIDES = {
    "10.1029/2025ja034386": {
        "summary_title": "2025年新年磁暴期间漠河热层风异常与极区对流边界演化",
        "chinese_title": "2025年新年磁暴期间漠河热层风异常与极区对流边界演化",
        "tags": ["热层/风场", "极区/对流边界", "磁暴", "仪器/FPI", "仪器/SuperDARN", "仪器/极光图像", "特征/等离子体对流", "特征/极光强度"],
        "body": (
            "这篇文章关注的问题是：2025年新年磁暴期间，漠河上空出现的异常热层风，是否与极区对流及其边界位置变化直接相关，"
            "以及这种高纬扰动为什么会明显影响东亚扇区。作者主要使用了漠河 FPI 的热层风观测、极光图像以及 SuperDARN 的"
            "极区对流观测，开展了一个多仪器联合的风暴个例分析。文章的主要结果是：午夜前较强的西向热层风，以及午夜后快速出现"
            "又迅速回落的东向热层风，都与极区对流边界相对漠河位置的变化密切对应；观测还捕捉到了热层风和极区对流连续演化的完整过程。"
            "作者进一步指出，强地磁活动叠加北磁极持续向西伯利亚漂移，可能促成了极区扰动区向东亚更低纬区域扩展。"
        ),
        "supplement": "这篇文章后续值得继续关注极区对流边界、热层风响应、北磁极漂移以及东亚扇区高纬热层扰动之间的联系。",
        "recommendation": "这篇文章和你关注的热层、磁暴和高纬扰动过程高度相关，建议作为今天优先细读的样本。",
        "apa_citation": (
            "Li, W., Liu, L., Zhang, J., Zhao, X., Dai, J., Zhang, R., Yang, Y., Liu, B., Chen, Y., & Le, H. (2026). "
            "Unusual disturbed thermospheric wind caused by polar convection at Mohe during 2025 New Year storm. "
            "Journal of Geophysical Research: Space Physics, 131(3), e2025JA034386. https://doi.org/10.1029/2025JA034386"
        ),
        "one_sentence": "文章利用 FPI、SuperDARN 和极光图像揭示了 2025 年新年磁暴期间漠河热层风异常与极区对流边界变化的对应关系。",
    }
}

JOURNAL_ABBREVIATIONS = {
    "JGR: Space Physics": "JGR.SP",
    "Journal of Geophysical Research: Space Physics": "JGR.SP",
    "Space Weather": "SW",
    "Journal of Space Weather and Space Climate": "JSWSC",
    "Annales Geophysicae": "Ann. Geophys.",
    "Journal of Atmospheric and Solar-Terrestrial Physics": "JASTP",
    "Earth, Planets and Space": "EPS",
    "Chinese Journal of Space Science": "CJSS",
    "Solar Physics": "Sol. Phys.",
    "Geophysical Research Letters": "GRL",
    "JGR: Atmospheres": "JGR.A",
    "Advances in Space Research": "ASR",
    "Planetary and Space Science": "P&SS",
    "Atmospheric Chemistry and Physics": "ACP",
    "Radio Science": "RS",
    "Nature": "Nature",
    "Science": "Science",
    "Nature Geoscience": "Nat. Geosci.",
    "Nature Communications": "Nat. Commun.",
    "Communications Earth & Environment": "Commun. Earth Environ.",
    "Nature Astronomy": "Nat. Astron.",
    "Science Advances": "Sci. Adv.",
    "The Astrophysical Journal": "ApJ",
    "The Astrophysical Journal Letters": "ApJL",
    "Astronomy & Astrophysics": "A&A",
}


def format_authors_apa(authors: list[str]) -> str:
    if not authors:
        return "Unknown"

    formatted = [format_single_author_apa(author) for author in authors]
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]}, & {formatted[1]}"
    return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"


def format_single_author_apa(author: str) -> str:
    parts = preferred_author_tokens(author)
    if not parts:
        return author
    family = parts[-1].rstrip(",")
    initials: list[str] = []
    for part in parts[:-1]:
        subparts = [item for item in re.split(r"[-]+", part) if item]
        if len(subparts) > 1:
            initials.append("-".join(f"{item[0].upper()}." for item in subparts))
        else:
            initials.append(f"{part[0].upper()}.")
    initials_text = " ".join(initials)
    return f"{family}, {initials_text}".strip()


def sentence_case_title(title: str) -> str:
    text = clean_title_text(title)
    if not text:
        return text
    return text[0].upper() + text[1:].lower()


def build_doi_url(doi: str, fallback_url: str) -> str:
    cleaned = clean_text(doi)
    if cleaned:
        return f"https://doi.org/{cleaned.upper() if cleaned.lower().startswith('10.1029/') else cleaned}"
    return fallback_url or ""


def parse_authors(raw: str) -> list[str]:
    return [item.strip() for item in raw.split("\n") if item.strip()]


def first_author_label(raw_authors: str) -> str:
    authors = parse_authors(raw_authors)
    if not authors:
        return "Unknown"
    first = authors[0]
    parts = preferred_author_tokens(first)
    return parts[-1] if parts else first


def preferred_author_tokens(author: str) -> list[str]:
    parts = [part.strip() for part in author.strip().split() if part.strip()]
    latin_parts = [part for part in parts if re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", part)]
    return latin_parts or parts


def topic_labels(row: Row) -> list[str]:
    return [item for item in row["topic_labels"].split("\n") if item]


def resolve_local_pdf_path(row: Row) -> Path | None:
    if "local_pdf_path" not in row.keys():
        return None
    raw = clean_text(row["local_pdf_path"])
    if not raw:
        return None
    return Path(raw).expanduser()


def build_filename_from_chinese(
    row: Row,
    chinese_title: str,
    *,
    sanitize_generation_text,
) -> str:
    first_author = first_author_label(row["authors"])
    year = str(row["published_date"])[:4]
    journal = sanitize_filename(abbreviate_journal_name(row["source_name"]))
    title = sanitize_filename(sanitize_generation_text(chinese_title))[:72].rstrip()
    return f"{first_author} {year} - {journal} - {title}.md"


def build_filename(
    row: Row,
    chinese_title: str,
    *,
    sanitize_generation_text,
) -> str:
    return build_filename_from_chinese(row, chinese_title, sanitize_generation_text=sanitize_generation_text)


def unique_output_path(output_dir: Path, filename: str, fingerprint: str, used_paths: set[Path]) -> Path:
    base = output_dir / filename
    if base not in used_paths:
        return base

    stem = base.stem
    suffix = base.suffix
    short = fingerprint[:8] if fingerprint else "dup"
    candidate = output_dir / f"{stem} - {short}{suffix}"
    if candidate not in used_paths:
        return candidate

    index = 2
    while True:
        indexed = output_dir / f"{stem} - {short}-{index}{suffix}"
        if indexed not in used_paths:
            return indexed
        index += 1


def build_resource_link(row: Row) -> str:
    doi_url = build_doi_url(row["doi"], row["url"])
    return f"[DOI]({doi_url})" if doi_url else "PDF待补充"


def build_resource_line(row: Row, tags: list[str]) -> str:
    return f"- {build_resource_link(row)} {build_tag_line(tags)}".rstrip()


def display_title(row: Row) -> str:
    return clean_title_text(row["title"])


def abbreviate_journal_name(name: str) -> str:
    clean_name = clean_text(name)
    return JOURNAL_ABBREVIATIONS.get(clean_name, clean_name)


def get_override(row: Row) -> dict | None:
    if _row_flag(row, "disable_special_overrides", default=False):
        return None
    return SPECIAL_PAPER_OVERRIDES.get(normalize_doi(row["doi"]))


def _row_flag(row: Row, key: str, default: bool = False) -> bool:
    try:
        value = row[key]
    except Exception:
        value = row.get(key, default) if isinstance(row, dict) else default
    return bool(value)
