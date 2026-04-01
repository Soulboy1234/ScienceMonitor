from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from .config import obsidian_target as configured_obsidian_target
from .llm import AnalysisEngine, ArticleAnalysis
from .utils import clean_title_text


SPECIAL_PAPER_OVERRIDES = {
    "10.1029/2025ja034386": {
        "summary_title": "2025年新年磁暴期间漠河热层风异常与极区对流边界演化",
        "chinese_title": "2025年新年磁暴期间漠河热层风异常与极区对流边界演化",
        "tags": ["磁暴", "极区对流/边界", "FPI", "SuperDARN", "极光图像", "热层/风", "等离子体对流", "极光强度"],
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

INVALID_OUTPUT_SNIPPETS = ("oops", "todo", "tbd", "placeholder")
PLACEHOLDER_TITLES = {"文献内容概括待补充", "相关研究"}
GENERIC_SENTENCE_FRAGMENTS = (
    "文章围绕相关空间物理问题",
    "利用相关数据分析了关键物理量的变化特征",
    "适合放入今日重点跟进列表",
    "与当前主题方向相关",
    "摘要显示，该研究给出了与上述问题相关的主要结果和解释",
)

TAG_ALIAS_MAP = {
    "热层风": "热层/风",
    "热层密度": "热层/密度",
    "中性密度": "热层/密度",
    "热层成分": "热层/成分",
    "热层温度": "热层/温度",
    "地球": "研究星球/地球",
    "月球": "研究星球/月球",
    "火星": "研究星球/火星",
    "金星": "研究星球/金星",
    "水星": "研究星球/水星",
    "木星": "研究星球/木星",
    "土星": "研究星球/土星",
    "天王星": "研究星球/天王星",
    "海王星": "研究星球/海王星",
}

OTHER_PLANET_TAG_ALIASES = {
    "研究星球/月球": "其他行星/月球",
    "研究星球/水星": "其他行星/水星",
    "研究星球/金星": "其他行星/金星",
    "研究星球/火星": "其他行星/火星",
    "研究星球/木星": "其他行星/木星",
    "研究星球/土星": "其他行星/土星",
    "研究星球/天王星": "其他行星/天王星",
    "研究星球/海王星": "其他行星/海王星",
    "木卫三/极光": "其他行星/木星",
    "木卫三/大气": "其他行星/木星",
    "土卫六": "其他行星/土星",
    "行星大气/天王星": "其他行星/天王星",
}


SCIENCE_TAG_RULES = [
    ("磁暴", ["geomagnetic storm", "superstorm", "magnetic storm", "storm-time", "storm time", "substorm"]),
    ("极区对流/边界", ["polar convection", "convection boundary", "polar cap", "auroral oval"]),
    ("电离层", ["ionosphere", "ionospheric", "plasma bubble", "equatorial plasma bubble", "tec", "total electron content"]),
    ("热层", ["thermosphere", "thermospheric", "upper atmosphere", "neutral density", "exobase"]),
    ("日地耦合", ["solar wind", "interplanetary", "magnetopause", "magnetosheath", "imf", "reconnection"]),
    ("空间天气", ["space weather", "forecast"]),
    ("重力波/潮汐", ["gravity wave", "gravity waves", "planetary wave", "planetary waves", "tide", "tidal"]),
    ("行星空间环境", ["mars", "martian", "venus", "mercury", "jovian", "saturn", "planetary"]),
]

RESEARCH_BODY_TAG_RULES = [
    ("研究星球/地球", [" earth ", "earth", "earth's", "terrestrial", "地球"]),
    ("研究星球/月球", [" moon ", "moon", "lunar", "月球"]),
    ("研究星球/火星", [" mars ", "mars", "martian", "火星"]),
    ("研究星球/金星", [" venus ", "venus", "venusian", "金星"]),
    ("研究星球/水星", [" mercury ", "mercury", "mercurian", "水星"]),
    ("研究星球/木星", [" jupiter ", "jupiter", "jovian", "木星"]),
    ("研究星球/土星", [" saturn ", "saturn", "saturnian", "土星"]),
    ("研究星球/天王星", [" uranus ", "uranus", "uranian", "天王星"]),
    ("研究星球/海王星", [" neptune ", "neptune", "neptunian", "海王星"]),
]

INSTRUMENT_DATA_TAG_RULES = [
    ("FPI", ["fabry-perot", "fabry perot", "fpi"]),
    ("SuperDARN", ["superdarn"]),
    ("GNSS", ["gnss", "beidou", "gps", "galileo"]),
    ("MMS", ["magnetospheric multi-scale", "mms"]),
    ("DMSP", ["dmsp"]),
    ("ICON", [" icon ", "icon satellite", "observed by icon"]),
    ("Van Allen Probes", ["van allen probes", "van allen"]),
    ("NICER", ["nicer"]),
    ("磁强计", ["magnetometer", "magnetometers"]),
    ("电离层测高仪", ["ionosonde", "ionosonde doppler"]),
    ("雷达", ["radar", "radars"]),
    ("极光图像", ["auroral image", "auroral images", "auroral photograph", "auroral photographs", "aurora", "auroral"]),
    ("再分析资料", ["reanalysis", "era5"]),
    ("模式模拟", ["simulation", "simulations", "model", "modeling", "sami2", "m-gitm", "swmf", "bats-r-us", "gitm", "waccm-x"]),
]

PHYSICAL_TAG_RULES = [
    ("TEC", ["total electron content", " tec ", "tec ", " tec"]),
    ("热层/风", ["thermospheric wind", "thermospheric winds", "neutral wind", "neutral winds", "meridional wind", "zonal wind", "热层风", "中性风", "经向风", "纬向风"]),
    ("热层/密度", ["thermospheric mass density", "thermospheric density", "neutral density", "mass density", "air density", "热层密度", "中性密度", "外逸层", "卫星阻力", "drag environment", "satellite drag", "drag of leo satellites", "leo satellite drag"]),
    ("热层/成分", ["o/n2", "composition", "neutral composition", "thermospheric composition", "nitric oxide", "atomic oxygen", "热层成分", "一氧化氮", "成分变化", "no production"]),
    ("热层/温度", ["thermospheric temperature", "neutral temperature", "exospheric temperature", "热层温度", "中性温度"]),
    ("等离子体对流", ["plasma convection", "convection", "drift"]),
    ("极光强度", ["auroral emission", "auroral emissions", "continuum emission", "aurora", "auroral"]),
    ("电子温度", ["electron temperature"]),
    ("电子密度", ["electron density"]),
    ("等离子体密度", ["plasma density", "density peak", "density bulge"]),
    ("相对论电子", ["relativistic electron", "mev electron", "mev electrons", "radiation belt"]),
    ("重力波", ["gravity wave", "gravity waves", "secondary gravity wave"]),
]

TOPIC_TO_TAG = {
    "电离层": "电离层",
    "热层": "热层",
    "日地耦合": "日地耦合",
    "低层大气波动上传": "重力波/潮汐",
    "磁层-电离层-热层耦合": "磁层-电离层-热层耦合",
    "行星际环境驱动": "日地耦合",
    "空间天气": "空间天气",
    "行星空间环境": "行星空间环境",
}

JOURNAL_ABBREVIATIONS = {
    "JGR: Space Physics": "JGR.SP",
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


@dataclass(frozen=True)
class ArticleSummaryResult:
    row: Row
    analysis: ArticleAnalysis | None
    output_path: Path
    note_title: str
    chinese_title: str
    tags: list[str]
    body: str
    supplement: str
    recommendation: str
    one_sentence: str
    rendered_markdown: str


def sanitize_generation_text(text: str) -> str:
    cleaned = clean_title_text(str(text or ""))
    cleaned = re.sub(r"(?i)\boops\b.*$", "", cleaned).strip()
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"([。；])\1+", r"\1", cleaned)
    return cleaned.strip()


def sanitize_tag(tag: str) -> str:
    cleaned = sanitize_generation_text(tag).lstrip("#")
    cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9/+\-_.&]+", "", cleaned)
    cleaned = cleaned.strip("./-_")
    return TAG_ALIAS_MAP.get(cleaned, cleaned)


def sanitize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen_research_body = False
    for tag in tags:
        cleaned = sanitize_tag(tag)
        if not cleaned:
            continue
        if any(snippet in cleaned.lower() for snippet in INVALID_OUTPUT_SNIPPETS):
            continue
        if cleaned.startswith("研究星球/"):
            if seen_research_body:
                continue
            seen_research_body = True
        if cleaned not in normalized:
            normalized.append(cleaned)
    normalized = append_other_planet_tags(normalized)
    return prefer_more_specific_tags(normalized)[:14]


def prefer_more_specific_tags(tags: list[str]) -> list[str]:
    refined: list[str] = []
    for tag in tags:
        if any(other != tag and other.startswith(tag + "/") for other in tags):
            continue
        refined.append(tag)
    return refined


def append_other_planet_tags(tags: list[str]) -> list[str]:
    enriched = list(tags)
    for tag in tags:
        extra = OTHER_PLANET_TAG_ALIASES.get(tag)
        if extra and extra not in enriched:
            enriched.append(extra)
    return enriched


def is_placeholder_title(text: str) -> bool:
    cleaned = sanitize_generation_text(text)
    return not cleaned or cleaned in PLACEHOLDER_TITLES


def is_generic_sentence(text: str) -> bool:
    cleaned = sanitize_generation_text(text)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if any(snippet in lowered for snippet in INVALID_OUTPUT_SNIPPETS):
        return True
    return any(fragment in cleaned for fragment in GENERIC_SENTENCE_FRAGMENTS)


def build_safe_one_sentence(row: Row, tags: list[str]) -> str:
    focus = "、".join(tags[:2]) if tags else "空间物理"
    return f"该文主要涉及{focus}，建议结合原标题和摘要确认其最核心的结论与方法。"


def build_safe_recommendation(row: Row, tags: list[str]) -> str:
    focus = "、".join(tags[:2]) if tags else "当前监控主题"
    return f"如果你在跟踪{focus}，这篇文章值得先看摘要、数据来源和方法部分。"


def build_safe_body(row: Row, tags: list[str]) -> str:
    focus = "、".join(tags[:3]) if tags else "相关空间物理问题"
    return f"这篇文章的标题和摘要信息不足以支持更细的中文概括。根据现有元数据，它主要涉及{focus}，建议后续结合全文继续确认具体数据、方法和结论。"


def validate_summary_fields(
    row: Row,
    chinese_title: str,
    tags: list[str],
    body: str,
    supplement: str,
    recommendation: str,
    one_sentence: str,
) -> tuple[str, list[str], str, str, str, str]:
    cleaned_tags = sanitize_tags(tags)
    if not cleaned_tags:
        cleaned_tags = sanitize_tags(get_focus_tags(row, analysis=None))

    cleaned_title = sanitize_generation_text(chinese_title)
    if is_placeholder_title(cleaned_title):
        cleaned_title = sanitize_generation_text(build_chinese_title(row, analysis=None))
    if is_placeholder_title(cleaned_title):
        cleaned_title = "标题与摘要信息待补充"

    cleaned_body = sanitize_generation_text(body)
    if is_generic_sentence(cleaned_body):
        cleaned_body = build_safe_body(row, cleaned_tags)

    cleaned_supplement = sanitize_generation_text(supplement)
    if not cleaned_supplement:
        cleaned_supplement = build_supplement_text(row, analysis=None)

    cleaned_recommendation = sanitize_generation_text(recommendation)
    if is_generic_sentence(cleaned_recommendation):
        cleaned_recommendation = build_safe_recommendation(row, cleaned_tags)

    cleaned_one_sentence = sanitize_generation_text(one_sentence)
    if is_generic_sentence(cleaned_one_sentence):
        cleaned_one_sentence = build_safe_one_sentence(row, cleaned_tags)

    return (
        cleaned_title,
        cleaned_tags,
        cleaned_body,
        cleaned_supplement,
        cleaned_recommendation,
        cleaned_one_sentence,
    )


def article_summary_quality_score(summary: ArticleSummaryResult) -> int:
    score = 0
    if not is_placeholder_title(summary.chinese_title):
        score += 1
    if len(sanitize_tags(summary.tags)) >= 3:
        score += 1
    if not is_generic_sentence(summary.body):
        score += 1
    if not is_generic_sentence(summary.one_sentence):
        score += 1
    return score


DOI_URL_RE = re.compile(r"https://doi\.org/([^\s_]+)", re.IGNORECASE)
HASH_TAG_RE = re.compile(r"(?<!\w)#([^\s#]+)")
RELATED_REPORTS_HEADER = "- 「关联报告」"


def generate_article_summaries(
    rows: list[Row],
    template_path: Path,
    output_dir: Path,
    analysis_engine: AnalysisEngine | None = None,
) -> list[Path]:
    return [
        item.output_path
        for item in generate_article_summary_results(
            rows=rows,
            template_path=template_path,
            output_dir=output_dir,
            analysis_engine=analysis_engine,
        )
    ]


def generate_article_summary_results(
    rows: list[Row],
    template_path: Path,
    output_dir: Path,
    analysis_engine: AnalysisEngine | None = None,
) -> list[ArticleSummaryResult]:
    _ = template_path.read_text(encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[ArticleSummaryResult] = []
    used_paths: set[Path] = set()
    existing_files = index_existing_summary_files(output_dir)

    for index, row in enumerate(rows):
        existing = load_existing_summary_result(existing_files, row)
        if existing is not None:
            results.append(existing)
            used_paths.add(existing.output_path)
            continue

        analysis = resolve_article_analysis(row, analysis_engine, index)
        chinese_title = build_chinese_title(row, analysis=analysis)
        tags = get_focus_tags(row, analysis=analysis)
        body = build_body_paragraph(row, analysis=analysis)
        supplement = build_supplement_text(row, analysis=analysis)
        recommendation = build_recommendation(row, analysis=analysis)
        one_sentence = build_one_sentence_summary(row, analysis=analysis)
        chinese_title, tags, body, supplement, recommendation, one_sentence = validate_summary_fields(
            row,
            chinese_title,
            tags,
            body,
            supplement,
            recommendation,
            one_sentence,
        )
        note_title = build_note_title_from_chinese(row, chinese_title)
        rendered = render_article_summary(
            row,
            analysis=analysis,
            note_title=note_title,
            tags=tags,
            body=body,
            supplement=supplement,
        )
        target = unique_output_path(output_dir, build_filename_from_chinese(row, chinese_title), row["fingerprint"], used_paths)
        target.write_text(rendered, encoding="utf-8")
        used_paths.add(target)
        results.append(
            ArticleSummaryResult(
                row=row,
                analysis=analysis,
                output_path=target,
                note_title=note_title,
                chinese_title=chinese_title,
                tags=tags,
                body=body,
                supplement=supplement,
                recommendation=recommendation,
                one_sentence=one_sentence,
                rendered_markdown=rendered,
            )
        )

    return results


def obsidian_target(path: Path, root: Path | None = None) -> str:
    return configured_obsidian_target(path, root=root, keep_suffix=False)


def obsidian_link(path: Path, label: str, root: Path | None = None) -> str:
    return f"[[{obsidian_target(path, root=root)}|{label}]]"


def sync_summary_report_links(
    summaries: list[ArticleSummaryResult],
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
    block_lines = [RELATED_REPORTS_HEADER]
    block_lines.extend(f"\t{index}. {link}" for index, link in enumerate(all_links, start=1))
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


def index_existing_summary_files(output_dir: Path) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    if not output_dir.exists():
        return indexed
    for path in output_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        match = DOI_URL_RE.search(text)
        if not match:
            continue
        doi = normalize_doi(match.group(1))
        if doi and doi not in indexed:
            indexed[doi] = path
    return indexed


def load_existing_summary_result(existing_files: dict[str, Path], row: Row) -> ArticleSummaryResult | None:
    doi = normalize_doi(row["doi"])
    path = existing_files.get(doi)
    if path is None or not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    note_title = path.stem
    tags = extract_summary_tags(text)
    body = extract_summary_body(text)
    supplement = extract_numbered_line(text, "- 「补充信息」")
    chinese_title = note_title.split(" - ", 3)[-1] if " - " in note_title else build_chinese_title(row)
    recommendation = build_recommendation(row)
    one_sentence = build_one_sentence_summary(row)
    inferred_tags = infer_tags_from_text("\n".join(filter(None, [note_title, body, supplement])))
    merged_tags = dedupe(get_focus_tags(row) + inferred_tags + (tags or []))
    chinese_title, tags, body, supplement, recommendation, one_sentence = validate_summary_fields(
        row,
        chinese_title,
        merged_tags,
        body or build_body_paragraph(row),
        supplement or build_supplement_text(row),
        recommendation,
        one_sentence,
    )
    note_title = build_note_title_from_chinese(row, chinese_title)
    repaired = render_article_summary(
        row,
        note_title=note_title,
        tags=tags,
        body=body,
        supplement=supplement,
    )
    repaired = upsert_related_reports_section(repaired, extract_related_report_links(text))
    if repaired != text:
        path.write_text(repaired, encoding="utf-8")
        text = repaired

    return ArticleSummaryResult(
        row=row,
        analysis=None,
        output_path=path,
        note_title=note_title,
        chinese_title=chinese_title,
        tags=tags,
        body=body,
        supplement=supplement,
        recommendation=recommendation,
        one_sentence=one_sentence,
        rendered_markdown=text,
    )


def render_article_summary(
    row: Row,
    analysis: ArticleAnalysis | None = None,
    note_title: str | None = None,
    tags: list[str] | None = None,
    body: str | None = None,
    supplement: str | None = None,
) -> str:
    now = datetime.now()
    resolved_note_title = note_title or build_note_title(row, analysis=analysis)
    resolved_tags = tags or get_focus_tags(row, analysis=analysis)
    resolved_body = body or build_body_paragraph(row, analysis=analysis)
    resolved_supplement = supplement or build_supplement_text(row, analysis=analysis)
    lines = [
        "----",
        build_resource_line(row, resolved_tags),
        f"- _{build_apa_citation(row, analysis=analysis)}_",
        f"- {resolved_body}",
        "- 「补充信息」",
        f"\t1. {resolved_supplement}",
        "- 「文中引用」",
        "\t1. 暂留空。",
        "- 「好句子」",
        "\t1. 暂留空。",
        "",
        "",
        "----",
        f"记录时间戳: {now.strftime('%Y-%m-%d')} {now.strftime('%H:%M:%S')}",
    ]
    return "\n".join(lines) + "\n"


def build_note_title(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    return build_note_title_from_chinese(row, build_chinese_title(row, analysis=analysis))


def build_note_title_from_chinese(row: Row, chinese_title: str) -> str:
    first_author = first_author_label(row["authors"])
    year = str(row["published_date"])[:4]
    journal = abbreviate_journal_name(row["source_name"])
    return f"{first_author} {year} - {journal} - {sanitize_generation_text(chinese_title)}"


def build_chinese_title(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    override = get_override(row)
    if override and "chinese_title" in override:
        return override["chinese_title"]
    if analysis:
        return analysis.chinese_title

    science_tags = get_focus_tags_by_group(row)["science"]
    physical_tags = get_focus_tags_by_group(row)["physical"]
    if science_tags and physical_tags:
        return f"{science_tags[0]}背景下{physical_tags[0]}特征研究"
    if physical_tags:
        return f"{physical_tags[0]}特征研究"
    if science_tags:
        return f"{science_tags[0]}相关研究"
    return "文献内容概括待补充"


def get_focus_tags(row: Row, analysis: ArticleAnalysis | None = None) -> list[str]:
    override = get_override(row)
    if override and "tags" in override:
        return list(override["tags"])
    if analysis:
        return dedupe(list(analysis.tags))

    grouped = get_focus_tags_by_group(row)
    tags = grouped["science"][:2] + grouped["body"][:1] + grouped["instrument"][:3] + grouped["physical"][:3]
    if not tags:
        tags = fallback_tags_from_topics(row)
    return dedupe(tags)


def get_focus_tags_by_group(row: Row) -> dict[str, list[str]]:
    title_haystack = f" {display_title(row).lower()} "
    haystack = normalize_haystack(row)
    science = match_rules(haystack, SCIENCE_TAG_RULES)
    body = match_rules(title_haystack, RESEARCH_BODY_TAG_RULES)
    if not body:
        body = match_rules(haystack, RESEARCH_BODY_TAG_RULES)
    instrument = match_rules(haystack, INSTRUMENT_DATA_TAG_RULES)
    physical = match_rules(haystack, PHYSICAL_TAG_RULES)

    if not science:
        science = fallback_tags_from_topics(row)

    return {
        "science": dedupe(science),
        "body": dedupe(body),
        "instrument": dedupe(instrument),
        "physical": dedupe(physical),
    }


def infer_tags_from_text(text: str) -> list[str]:
    haystack = f" {clean_text(text).lower()} "
    return dedupe(
        match_rules(haystack, SCIENCE_TAG_RULES)
        + match_rules(haystack, RESEARCH_BODY_TAG_RULES)
        + match_rules(haystack, INSTRUMENT_DATA_TAG_RULES)
        + match_rules(haystack, PHYSICAL_TAG_RULES)
    )


def build_apa_citation(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    override = get_override(row)
    if override and "apa_citation" in override:
        return override["apa_citation"]

    authors = parse_authors(row["authors"])
    authors_text = format_authors_apa(authors)
    year = str(row["published_date"])[:4]
    title = sentence_case_title(row["title"])
    journal = row["source_name"]
    doi_url = build_doi_url(row["doi"], row["url"])
    return f"{authors_text} ({year}). {title}. {journal}. {doi_url}"


def build_body_paragraph(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    override = get_override(row)
    if override and "body" in override:
        return override["body"]
    if analysis:
        return analysis.body

    grouped = get_focus_tags_by_group(row)
    science_text = "、".join(grouped["science"][:2]) if grouped["science"] else "相关空间物理问题"
    instrument_text = "、".join(grouped["instrument"][:3]) if grouped["instrument"] else "题目和摘要提到的相关观测或模拟资料"
    physical_text = "、".join(grouped["physical"][:3]) if grouped["physical"] else "关键物理过程"
    method_text = infer_method(row)
    conclusion_text = infer_conclusion(row)
    return (
        f"这篇文章主要关注{science_text}。作者使用{instrument_text}，通过{method_text}分析{physical_text}的变化特征。"
        f"{conclusion_text}"
    )


def build_supplement_text(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    override = get_override(row)
    if override and "supplement" in override:
        return override["supplement"]
    if analysis:
        return analysis.supplement

    grouped = get_focus_tags_by_group(row)
    science_text = "、".join(grouped["science"][:2]) if grouped["science"] else "该研究主题"
    physical_text = "、".join(grouped["physical"][:2]) if grouped["physical"] else "相关物理量"
    return f"后续可继续关注{science_text}与{physical_text}之间的联系，以及是否有更多观测或模型结果支持当前结论。"


def build_recommendation(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    override = get_override(row)
    if override and "recommendation" in override:
        return override["recommendation"]
    if analysis:
        return analysis.recommendation

    grouped = get_focus_tags_by_group(row)
    science_text = "、".join(grouped["science"][:2]) if grouped["science"] else "当前主题"
    return f"这篇文章与{science_text}方向相关，适合放入今日重点跟进列表。"


def build_one_sentence_summary(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    override = get_override(row)
    if override and "one_sentence" in override:
        return override["one_sentence"]
    if analysis:
        return analysis.one_sentence

    grouped = get_focus_tags_by_group(row)
    science_text = "、".join(grouped["science"][:2]) if grouped["science"] else "相关空间物理问题"
    instrument_text = "、".join(grouped["instrument"][:2]) if grouped["instrument"] else "相关数据"
    physical_text = "、".join(grouped["physical"][:2]) if grouped["physical"] else "关键物理量"
    return f"文章围绕{science_text}，利用{instrument_text}分析了{physical_text}的变化特征。"


def infer_method(row: Row) -> str:
    text = normalize_haystack(row)
    methods: list[str] = []
    if any(keyword in text for keyword in ["observation", "observations", "measured", "measurement", "satellite", "radar"]):
        methods.append("观测分析")
    if any(keyword in text for keyword in ["simulation", "simulations", "model", "modeling", "reanalysis"]):
        methods.append("数值模拟或模式对比")
    if any(keyword in text for keyword in ["statistical", "statistics", "global", "climatology", "trend"]):
        methods.append("统计分析")
    if any(keyword in text for keyword in ["case study", "event", "storm", "substorm"]):
        methods.append("个例研究")
    if not methods:
        methods.append("标题和摘要信息提炼")
    return "、".join(dedupe(methods))


def infer_conclusion(row: Row) -> str:
    abstract = clean_text(row["abstract"])
    if not abstract:
        return "摘要信息有限，建议结合全文进一步确认具体结论。"

    title = display_title(row).lower()
    if "response" in title or "responses" in title:
        return "摘要显示，该研究重点比较了不同条件下的响应差异，并给出了对应的物理解释。"
    if "observation" in title or "observations" in title:
        return "摘要显示，该研究报道了新的观测结果，并对相关过程给出了现象学解释。"
    if "effects" in title:
        return "摘要显示，该研究评估了不同驱动条件的影响，并讨论了可能的控制机制。"
    if "investigation" in title or "study" in title:
        return "摘要显示，该研究系统分析了相关现象，并总结了关键特征和可能成因。"
    return "摘要显示，该研究给出了与上述问题相关的主要结果和解释，值得结合全文继续细读。"


def normalize_haystack(row: Row) -> str:
    return f" {display_title(row).lower()} {clean_text(row['abstract']).lower()} "


def match_rules(haystack: str, rules: list[tuple[str, list[str]]]) -> list[str]:
    matched: list[str] = []
    for label, keywords in rules:
        if any(keyword.lower() in haystack for keyword in keywords):
            matched.append(label)
    return matched


def fallback_tags_from_topics(row: Row) -> list[str]:
    tags: list[str] = []
    for label in topic_labels(row):
        mapped = TOPIC_TO_TAG.get(label)
        if mapped:
            tags.append(mapped)
    return tags


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


def build_filename(row: Row, analysis: ArticleAnalysis | None = None) -> str:
    return build_filename_from_chinese(row, build_chinese_title(row, analysis=analysis))


def build_filename_from_chinese(row: Row, chinese_title: str) -> str:
    first_author = first_author_label(row["authors"])
    year = str(row["published_date"])[:4]
    journal = sanitize_filename(abbreviate_journal_name(row["source_name"]))
    title = sanitize_filename(sanitize_generation_text(chinese_title))[:72].rstrip()
    return f"{first_author} {year} - {journal} - {title}.md"


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


def sanitize_filename(text: str) -> str:
    clean = re.sub(r"[\\/:*?\"<>|]+", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "untitled"


def format_tag(tag: str) -> str:
    return "#" + re.sub(r"\s+", "", tag)


def build_resource_line(row: Row, tags: list[str]) -> str:
    doi_url = build_doi_url(row["doi"], row["url"])
    resource_link = f"[DOI]({doi_url})" if doi_url else "PDF待补充"
    return f"- {resource_link} {' '.join(format_tag(tag) for tag in tags)}".rstrip()


def display_title(row: Row) -> str:
    return clean_title_text(row["title"])


def abbreviate_journal_name(name: str) -> str:
    clean_name = clean_text(name)
    return JOURNAL_ABBREVIATIONS.get(clean_name, clean_name)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_doi(value: str) -> str:
    return clean_text(value).lower().rstrip(").,;")


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
            return [item for item in HASH_TAG_RE.findall(line)]
        if line.startswith("- 标签："):
            return [item.lstrip("#") for item in line.split() if item.startswith("#")]
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
    return ""


def extract_section_text(text: str, header: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == header and index + 1 < len(lines):
            return lines[index + 1].strip().lstrip("1.").strip()
    return ""


def extract_numbered_line(text: str, header: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == header:
            for follow in lines[index + 1:]:
                stripped = follow.strip()
                if not stripped:
                    continue
                if stripped.startswith("- "):
                    break
                if stripped.startswith("1."):
                    return stripped[2:].strip()
    return ""


def get_override(row: Row) -> dict | None:
    return SPECIAL_PAPER_OVERRIDES.get(normalize_doi(row["doi"]))


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def resolve_article_analysis(
    row: Row,
    analysis_engine: AnalysisEngine | None,
    index: int,
) -> ArticleAnalysis | None:
    if analysis_engine is None or get_override(row):
        return None
    try:
        return analysis_engine.analyze_article(row, index=index)
    except Exception:
        return None
