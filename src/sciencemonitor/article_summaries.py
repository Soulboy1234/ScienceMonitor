from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from .article_fetch import resolve_summary_source_material
from .config import obsidian_target as configured_obsidian_target
from .crossref import CrossrefClient
from .http import HTTPClient
from .llm import AnalysisEngine, ArticleAnalysis
from .tags import clean_tag_text, group_tags, infer_preferred_tags_from_text, normalize_tags
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

INVALID_OUTPUT_SNIPPETS = ("oops", "todo", "tbd", "placeholder")
PLACEHOLDER_TITLES = {"文献内容概括待补充", "相关研究"}
GENERIC_SENTENCE_FRAGMENTS = (
    "文章围绕相关空间物理问题",
    "利用相关数据分析了关键物理量的变化特征",
    "适合放入今日重点跟进列表",
    "与当前主题方向相关",
    "摘要显示，该研究给出了与上述问题相关的主要结果和解释",
)
ABSTRACT_ONLY_TAG = "信息来源/仅摘要"
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
ARTICLE_SUMMARY_REVIEW_MAX_PASSES = 3

TOPIC_TO_TAG = {
    "电离层": "电离层",
    "热层": "热层",
    "日地耦合": "日地耦合",
    "低层大气波动上传": "重力波/潮汐",
    "磁层-电离层-热层耦合": "磁层-电离层耦合",
    "行星际环境驱动": "太阳风/高速流",
    "空间天气": "空间天气",
    "行星空间环境": "其他行星/行星综合",
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
    return clean_tag_text(sanitize_generation_text(tag))


def sanitize_tags(
    tags: list[str],
    *,
    root: Path | None = None,
    max_tags: int = 14,
    context: str = "",
    record_candidates: bool = False,
) -> list[str]:
    return normalize_tags(
        tags,
        root=root,
        max_tags=max_tags,
        context=context,
        record_candidates=record_candidates,
    )


def prefer_more_specific_tags(tags: list[str]) -> list[str]:
    refined: list[str] = []
    for tag in tags:
        if any(other != tag and other.startswith(tag + "/") for other in tags):
            continue
        refined.append(tag)
    return refined


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
    *,
    root: Path | None = None,
    candidate_context: str = "",
) -> tuple[str, list[str], str, str, str, str]:
    cleaned_tags = sanitize_tags(tags, root=root, context=candidate_context, record_candidates=bool(root))
    if not cleaned_tags:
        cleaned_tags = sanitize_tags(get_focus_tags(row, analysis=None, root=root), root=root)

    cleaned_title = sanitize_generation_text(chinese_title)
    if is_placeholder_title(cleaned_title):
        cleaned_title = sanitize_generation_text(build_chinese_title(row, analysis=None, root=root))
    if is_placeholder_title(cleaned_title):
        cleaned_title = "标题与摘要信息待补充"

    cleaned_body = sanitize_generation_text(body)
    if is_generic_sentence(cleaned_body):
        cleaned_body = build_safe_body(row, cleaned_tags)

    cleaned_supplement = sanitize_generation_text(supplement)
    if not cleaned_supplement:
        cleaned_supplement = build_supplement_text(row, analysis=None, root=root)
    cleaned_supplement = normalize_summary_supplement(row, cleaned_supplement)

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


def resolve_summary_root(root: Path | None = None, template_path: Path | None = None) -> Path | None:
    if root is not None:
        return root
    if template_path is not None:
        if template_path.parent.name == "templates" and template_path.parent.parent.name == "config":
            return template_path.parent.parent.parent
        if template_path.parent.name == "config":
            return template_path.parent.parent
    return None


def generate_article_summaries(
    rows: list[Row],
    template_path: Path,
    output_dir: Path,
    analysis_engine: AnalysisEngine | None = None,
    root: Path | None = None,
    enable_live_fetch: bool = False,
    require_analysis: bool = True,
) -> list[Path]:
    return [
        item.output_path
        for item in generate_article_summary_results(
            rows=rows,
            template_path=template_path,
            output_dir=output_dir,
            analysis_engine=analysis_engine,
            root=root,
            enable_live_fetch=enable_live_fetch,
            require_analysis=require_analysis,
        )
    ]


def generate_article_summary_results(
    rows: list[Row],
    template_path: Path,
    output_dir: Path,
    analysis_engine: AnalysisEngine | None = None,
    root: Path | None = None,
    enable_live_fetch: bool = False,
    require_analysis: bool = True,
) -> list[ArticleSummaryResult]:
    project = resolve_summary_root(root=root, template_path=template_path)
    template_text = load_article_summary_template(template_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[ArticleSummaryResult] = []
    used_paths: set[Path] = set()
    existing_files = index_existing_summary_files(output_dir)
    http = HTTPClient(timeout=20) if enable_live_fetch else None
    crossref = CrossrefClient(http) if http is not None else None

    for index, row in enumerate(rows):
        existing = load_existing_summary_result(existing_files, row, template_text=template_text, root=project)
        if existing is not None:
            results.append(existing)
            used_paths.add(existing.output_path)
            continue

        effective_row = row
        source_material = None
        if http is not None and crossref is not None:
            local_pdf_path = _resolve_local_pdf_path(row)
            source_material = resolve_summary_source_material(
                doi=clean_text(row["doi"]),
                url=clean_text(row["url"]),
                title=display_title(row),
                journal=clean_text(row["source_name"] or row["journal_title"]),
                abstract=clean_text(row["abstract"]),
                authors=parse_authors(str(row["authors"] or "")),
                published_date=clean_text(row["published_date"]),
                http=http,
                crossref=crossref,
                local_pdf_path=local_pdf_path,
                project_root=project,
            )
            effective_row = apply_summary_source_material(row, source_material)

        analysis = resolve_article_analysis(
            effective_row,
            analysis_engine,
            index,
            raise_on_error=require_analysis,
        )
        if require_analysis and analysis is None and not get_override(effective_row):
            if analysis_engine is None:
                raise RuntimeError(
                    f"单篇总结已不再支持规则法。当前文章缺少 LLM 分析结果：{display_title(effective_row)}。"
                )
            raise RuntimeError(
                f"单篇总结生成需要 LLM 分析结果，但当前文章未得到有效结果：{display_title(effective_row)}。"
                f"请检查 provider 配置、模型可用性或额度，再重试。"
            )
        chinese_title = build_chinese_title(effective_row, analysis=analysis, root=project)
        tags = get_focus_tags(effective_row, analysis=analysis, root=project)
        if source_material is not None and source_material.abstract_only:
            tags = sanitize_tags(
                tags + [ABSTRACT_ONLY_TAG],
                root=project,
                context="article_summary",
                record_candidates=True,
            )
        body = build_body_paragraph(effective_row, analysis=analysis, root=project)
        supplement = build_supplement_text(effective_row, analysis=analysis, root=project)
        if source_material is not None and source_material.abstract_only:
            supplement = annotate_abstract_only_supplement(supplement)
        recommendation = build_recommendation(effective_row, analysis=analysis, root=project)
        one_sentence = build_one_sentence_summary(effective_row, analysis=analysis, root=project)
        chinese_title, tags, body, supplement, recommendation, one_sentence = validate_summary_fields(
            effective_row,
            chinese_title,
            tags,
            body,
            supplement,
            recommendation,
            one_sentence,
            root=project,
            candidate_context="article_summary",
        )
        note_title = build_note_title_from_chinese(effective_row, chinese_title)
        rendered = render_article_summary(
            effective_row,
            template_text=template_text,
            analysis=analysis,
            note_title=note_title,
            tags=tags,
            body=body,
            supplement=supplement,
            root=project,
        )
        rendered, review_issues = _run_article_summary_review_loop(
            effective_row,
            template_text=template_text,
            note_title=note_title,
            markdown=rendered,
            analysis=analysis,
            root=project,
        )
        if review_issues:
            raise ValueError("Article summary output failed review: " + "；".join(review_issues))
        tags = extract_summary_tags(rendered) or tags
        body = extract_summary_body(rendered) or body
        supplement = extract_numbered_line(rendered, "- 「补充信息」") or supplement
        target = unique_output_path(
            output_dir,
            build_filename_from_chinese(effective_row, chinese_title),
            row["fingerprint"],
            used_paths,
        )
        target.write_text(rendered, encoding="utf-8")
        used_paths.add(target)
        results.append(
            ArticleSummaryResult(
                row=effective_row,
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


def apply_summary_source_material(row: Row, source_material) -> dict:
    summary_text = clean_source_text(source_material.summary_text)
    if len(summary_text) > 18000:
        summary_text = summary_text[:18000].rsplit(" ", 1)[0].strip() + "\n..."
    result = dict(row)
    if source_material.title:
        result["title"] = source_material.title
    if source_material.url:
        result["url"] = source_material.url
    if source_material.doi:
        result["doi"] = source_material.doi
    if source_material.journal:
        result["source_name"] = source_material.journal
        result["journal_title"] = source_material.journal
    if source_material.authors:
        result["authors"] = "\n".join(source_material.authors)
    if source_material.published_date:
        result["published_date"] = source_material.published_date
    if summary_text:
        result["abstract"] = summary_text
    elif source_material.abstract:
        result["abstract"] = source_material.abstract
    result["summary_source_kind"] = source_material.source_kind
    if source_material.cache_path:
        result["source_text_cache_path"] = source_material.cache_path
    return result


def annotate_abstract_only_supplement(supplement: str) -> str:
    notice = "当前总结仅基于摘要和元数据生成，未获得全文，结论需按摘要级别理解。"
    clean_supplement = sanitize_generation_text(supplement)
    if notice in clean_supplement:
        return clean_supplement
    if not clean_supplement:
        return notice
    return f"{notice} {clean_supplement}"


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


def load_existing_summary_result(
    existing_files: dict[str, Path],
    row: Row,
    template_text: str,
    root: Path | None = None,
) -> ArticleSummaryResult | None:
    doi = normalize_doi(row["doi"])
    path = existing_files.get(doi)
    if path is None or not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    note_title = path.stem
    tags = extract_summary_tags(text)
    body = extract_summary_body(text)
    supplement = extract_numbered_line(text, "- 「补充信息」")
    chinese_title = note_title.split(" - ", 3)[-1] if " - " in note_title else build_chinese_title(row, root=root)
    recommendation = build_recommendation(row, root=root)
    one_sentence = build_one_sentence_summary(row, root=root)
    inferred_tags = infer_tags_from_text("\n".join(filter(None, [note_title, body, supplement])), root=root)
    merged_tags = dedupe(get_focus_tags(row, root=root) + inferred_tags + (tags or []))
    chinese_title, tags, body, supplement, recommendation, one_sentence = validate_summary_fields(
        row,
        chinese_title,
        merged_tags,
        body or build_body_paragraph(row, root=root),
        supplement or build_supplement_text(row, root=root),
        recommendation,
        one_sentence,
        root=root,
        candidate_context="article_summary_repair",
    )
    note_title = build_note_title_from_chinese(row, chinese_title)
    repaired = render_article_summary(
        row,
        template_text=template_text,
        note_title=note_title,
        tags=tags,
        body=body,
        supplement=supplement,
        root=root,
    )
    repaired = upsert_related_reports_section(repaired, extract_related_report_links(text))
    repaired, review_issues = _run_article_summary_review_loop(
        row,
        template_text=template_text,
        note_title=note_title,
        markdown=repaired,
        root=root,
    )
    if review_issues:
        raise ValueError("Article summary output failed review: " + "；".join(review_issues))
    tags = extract_summary_tags(repaired) or tags
    body = extract_summary_body(repaired) or body
    supplement = extract_numbered_line(repaired, "- 「补充信息」") or supplement
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
    template_text: str,
    analysis: ArticleAnalysis | None = None,
    note_title: str | None = None,
    tags: list[str] | None = None,
    body: str | None = None,
    supplement: str | None = None,
    report_links: list[str] | None = None,
    root: Path | None = None,
) -> str:
    now = datetime.now()
    resolved_note_title = note_title or build_note_title(row, analysis=analysis, root=root)
    resolved_tags = tags or get_focus_tags(row, analysis=analysis, root=root)
    resolved_body = body or build_body_paragraph(row, analysis=analysis, root=root)
    resolved_supplement = supplement or build_supplement_text(row, analysis=analysis, root=root)
    rendered = render_article_summary_template(
        template_text,
        {
            "note_title": resolved_note_title,
            "resource_line": build_resource_line(row, resolved_tags),
            "resource_link": build_resource_link(row),
            "tag_line": build_tag_line(resolved_tags),
            "apa_citation": build_apa_citation(row, analysis=analysis),
            "body": resolved_body,
            "supplement": resolved_supplement,
            "references_block": build_numbered_block([]),
            "quotes_block": build_numbered_block([]),
            "related_reports_block": build_numbered_block(report_links or []),
            "timestamp_date": now.strftime("%Y-%m-%d"),
            "timestamp_time": now.strftime("%H:%M:%S"),
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    return rendered


def _run_article_summary_review_loop(
    row: Row,
    *,
    template_text: str,
    note_title: str,
    markdown: str,
    analysis: ArticleAnalysis | None = None,
    root: Path | None = None,
) -> tuple[str, list[str]]:
    reviewed = markdown
    for _ in range(ARTICLE_SUMMARY_REVIEW_MAX_PASSES):
        fixed = _autofix_article_summary_markdown(
            row,
            template_text=template_text,
            note_title=note_title,
            markdown=reviewed,
            analysis=analysis,
            root=root,
        )
        issues = _validate_article_summary_markdown(fixed, row=row)
        if not issues:
            return fixed, []
        if fixed == reviewed:
            return fixed, issues
        reviewed = fixed
    return reviewed, _validate_article_summary_markdown(reviewed, row=row)


def _autofix_article_summary_markdown(
    row: Row,
    *,
    template_text: str,
    note_title: str,
    markdown: str,
    analysis: ArticleAnalysis | None = None,
    root: Path | None = None,
) -> str:
    tags = extract_summary_tags(markdown) or get_focus_tags(row, analysis=analysis, root=root)
    body = extract_summary_body(markdown) or build_body_paragraph(row, analysis=analysis, root=root)
    supplement = extract_numbered_line(markdown, "- 「补充信息」") or build_supplement_text(row, analysis=analysis, root=root)
    supplement = normalize_summary_supplement(row, supplement)
    source_kind = str(row.get("summary_source_kind", "") or "").strip().lower()
    if source_kind and source_kind not in FULL_TEXT_SOURCE_KINDS:
        tags = sanitize_tags(tags + [ABSTRACT_ONLY_TAG], root=root, context="article_summary_review")
        supplement = annotate_abstract_only_supplement(supplement)
    elif source_kind in FULL_TEXT_SOURCE_KINDS:
        tags = [tag for tag in tags if tag != ABSTRACT_ONLY_TAG]
    recommendation = build_recommendation(row, analysis=analysis, root=root)
    one_sentence = build_one_sentence_summary(row, analysis=analysis, root=root)
    chinese_title = note_title.split(" - ", 3)[-1] if " - " in note_title else note_title
    _, tags, body, supplement, _, _ = validate_summary_fields(
        row,
        chinese_title,
        tags,
        body,
        supplement,
        recommendation,
        one_sentence,
        root=root,
        candidate_context="article_summary_review",
    )
    fixed = render_article_summary(
        row,
        template_text=template_text,
        analysis=analysis,
        note_title=note_title,
        tags=tags,
        body=body,
        supplement=supplement,
        report_links=extract_related_report_links(markdown),
        root=root,
    )
    return fixed


def _validate_article_summary_markdown(markdown: str, *, row: Row) -> list[str]:
    issues: list[str] = []
    for marker in ARTICLE_SUMMARY_TEMPLATE_REQUIRED_MARKERS:
        if marker not in markdown:
            issues.append(f"缺少单篇总结模板要求的区块：{marker}")
    if "{{" in markdown or "}}" in markdown:
        issues.append("单篇总结正文仍包含未替换的模板占位符")
    tags = extract_summary_tags(markdown)
    body = extract_summary_body(markdown)
    supplement = extract_numbered_line(markdown, "- 「补充信息」")
    if not body:
        issues.append("单篇总结缺少正文概括")
    elif is_generic_sentence(body):
        issues.append("单篇总结正文仍然过于空泛")
    if "结果片段" in supplement:
        issues.append("单篇总结补充信息仍包含“结果片段”旧表述")
    source_kind = str(row.get("summary_source_kind", "") or "").strip().lower()
    if source_kind and source_kind not in FULL_TEXT_SOURCE_KINDS:
        if ABSTRACT_ONLY_TAG not in tags:
            issues.append("摘要级单篇总结缺少“信息来源/仅摘要”标签")
        if "当前总结仅基于摘要和元数据生成" not in supplement:
            issues.append("摘要级单篇总结缺少摘要来源说明")
    if source_kind in FULL_TEXT_SOURCE_KINDS and ABSTRACT_ONLY_TAG in tags:
        issues.append("全文级单篇总结不应保留“信息来源/仅摘要”标签")
    return issues


def build_note_title(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    return build_note_title_from_chinese(row, build_chinese_title(row, analysis=analysis, root=root))


def build_note_title_from_chinese(row: Row, chinese_title: str) -> str:
    first_author = first_author_label(row["authors"])
    year = str(row["published_date"])[:4]
    journal = abbreviate_journal_name(row["source_name"])
    return f"{first_author} {year} - {journal} - {sanitize_generation_text(chinese_title)}"


TAG_GROUP_IDS = (
    "research_object",
    "event_driver",
    "index_control",
    "instrument_data",
    "model_method",
    "result_feature",
    "application_impact",
    "status",
)


def _empty_tag_groups() -> dict[str, list[str]]:
    return {key: [] for key in TAG_GROUP_IDS}


def _tag_phrase_for_sentence(tag: str) -> str:
    parts = [item for item in tag.split("/") if item]
    if not parts:
        return tag
    if parts[0] in {"仪器", "指数", "模型", "建模", "特征", "应用", "状态"} and len(parts) > 1:
        return "/".join(parts[1:])
    if parts[0] == "其他行星" and len(parts) > 1:
        return parts[-1]
    return tag


def _tag_phrase_for_title(tag: str) -> str:
    parts = [item for item in tag.split("/") if item]
    if not parts:
        return tag
    if parts[0] in {"仪器", "指数", "模型", "建模", "特征", "应用", "状态"} and len(parts) > 1:
        return "".join(parts[1:])
    if parts[0] == "其他行星" and len(parts) > 1:
        return parts[-1]
    return "".join(parts)


def _tag_text(tags: list[str], *, title_mode: bool = False) -> str:
    if not tags:
        return ""
    formatter = _tag_phrase_for_title if title_mode else _tag_phrase_for_sentence
    return "、".join(formatter(tag) for tag in tags)


def _prefer_deeper_tags(tags: list[str]) -> list[str]:
    ranked = [(tag.count("/"), index, tag) for index, tag in enumerate(tags)]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked]


def build_chinese_title(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "chinese_title" in override:
        return override["chinese_title"]
    if analysis:
        return analysis.chinese_title

    grouped = get_focus_tags_by_group(row, root=root)
    research_tags = _prefer_deeper_tags(grouped["research_object"])
    driver_tags = grouped["event_driver"]
    if driver_tags and research_tags:
        return f"{_tag_phrase_for_title(driver_tags[0])}背景下{_tag_phrase_for_title(research_tags[0])}特征研究"
    if research_tags:
        return f"{_tag_phrase_for_title(research_tags[0])}特征研究"
    if driver_tags:
        return f"{_tag_phrase_for_title(driver_tags[0])}相关研究"
    return "文献内容概括待补充"


def get_focus_tags(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> list[str]:
    override = get_override(row)
    if override and "tags" in override:
        return sanitize_tags(list(override["tags"]), root=root)
    if analysis:
        inferred = infer_preferred_tags_from_text(
            title_text=display_title(row),
            extra_text="\n".join(filter(None, [clean_text(row["notes"]), "\n".join(topic_labels(row))])),
            root=root,
        )
        source_inferred = infer_preferred_tags_from_text(
            body_text=clean_text(row["abstract"]),
            root=root,
        )
        source_grouped = group_tags(source_inferred, root=root)
        body_driver_tags = source_grouped.get("event_driver", [])
        return sanitize_tags(list(analysis.tags) + inferred + body_driver_tags, root=root)

    grouped = get_focus_tags_by_group(row, root=root)
    tags = (
        grouped["research_object"][:2]
        + grouped["event_driver"][:2]
        + grouped["index_control"][:1]
        + grouped["instrument_data"][:3]
        + grouped["model_method"][:2]
        + grouped["result_feature"][:2]
        + grouped["application_impact"][:1]
        + grouped["status"][:1]
    )
    if not tags:
        tags = fallback_tags_from_topics(row, root=root)
    return sanitize_tags(dedupe(tags), root=root)


def get_focus_tags_by_group(row: Row, root: Path | None = None) -> dict[str, list[str]]:
    inferred = infer_preferred_tags_from_text(
        title_text=display_title(row),
        body_text=clean_text(row["abstract"]),
        extra_text="\n".join(filter(None, [clean_text(row["notes"]), "\n".join(topic_labels(row))])),
        root=root,
    )
    if not inferred:
        inferred = fallback_tags_from_topics(row, root=root)

    groups = _empty_tag_groups()
    grouped = group_tags(inferred, root=root)
    for key in TAG_GROUP_IDS:
        groups[key] = grouped.get(key, [])
    return groups


def infer_tags_from_text(text: str, root: Path | None = None) -> list[str]:
    return infer_preferred_tags_from_text(
        title_text=text,
        body_text=text,
        root=root,
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


def build_body_paragraph(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "body" in override:
        return override["body"]
    if analysis:
        return analysis.body

    grouped = get_focus_tags_by_group(row, root=root)
    science_text = _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2] + grouped["event_driver"][:1]) or "相关空间物理问题"
    instrument_text = _tag_text(grouped["instrument_data"][:3] + grouped["model_method"][:1]) or "题目和摘要提到的相关观测或模拟资料"
    physical_text = _tag_text(grouped["result_feature"][:2] + grouped["application_impact"][:1]) or _tag_text(grouped["research_object"][:2]) or "关键物理过程"
    method_text = infer_method(row)
    conclusion_text = infer_conclusion(row)
    return (
        f"这篇文章主要关注{science_text}。作者使用{instrument_text}，通过{method_text}分析{physical_text}的变化特征。"
        f"{conclusion_text}"
    )


def build_supplement_text(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "supplement" in override:
        return override["supplement"]
    if analysis:
        return normalize_summary_supplement(row, analysis.supplement)

    grouped = get_focus_tags_by_group(row, root=root)
    science_text = _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2] + grouped["event_driver"][:1]) or "该研究主题"
    physical_text = _tag_text(grouped["result_feature"][:2] + grouped["application_impact"][:1]) or _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2]) or "相关物理量"
    return f"后续可继续关注{science_text}与{physical_text}之间的联系，以及是否有更多观测或模型结果支持当前结论。"


FULL_TEXT_SOURCE_KINDS = {"html_full_text", "local_pdf_full_text"}


def normalize_summary_supplement(row: Row, supplement: str) -> str:
    clean_supplement = sanitize_generation_text(supplement)
    clean_supplement = clean_supplement.replace("结果片段", "相关内容")
    clean_supplement = clean_supplement.replace("关键章节", "相关内容")
    source_kind = str(row.get("summary_source_kind", "") or "").strip().lower()
    if source_kind not in FULL_TEXT_SOURCE_KINDS:
        return clean_supplement

    normalized_prefix = (
        "程序已读取并缓存全文；当前单篇总结为控制额度，基于从全文抽取的摘要、方法、结果和结论证据整理稿生成。"
    )
    if not clean_supplement:
        return normalized_prefix
    if normalized_prefix in clean_supplement:
        return clean_supplement

    cleaned_remainder = re.sub(
        r"当前材料虽来自全文整理稿，但所给节选主要覆盖[^。]*。\s*",
        "",
        clean_supplement,
    ).strip()
    cleaned_remainder = re.sub(
        r"来源文本为全文整理稿，但当前提供给我的证据[^。]*。\s*",
        "",
        cleaned_remainder,
    ).strip()
    cleaned_remainder = cleaned_remainder.replace("结果片段", "结果证据句")
    cleaned_remainder = cleaned_remainder.replace("关键章节", "证据整理稿")
    if not cleaned_remainder:
        return normalized_prefix
    return f"{normalized_prefix} {cleaned_remainder}"


def build_recommendation(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "recommendation" in override:
        return override["recommendation"]
    if analysis:
        return analysis.recommendation

    grouped = get_focus_tags_by_group(row, root=root)
    science_text = _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2] + grouped["event_driver"][:1]) or "当前主题"
    return f"这篇文章与{science_text}方向相关，适合放入今日重点跟进列表。"


def build_one_sentence_summary(row: Row, analysis: ArticleAnalysis | None = None, root: Path | None = None) -> str:
    override = get_override(row)
    if override and "one_sentence" in override:
        return override["one_sentence"]
    if analysis:
        return analysis.one_sentence

    grouped = get_focus_tags_by_group(row, root=root)
    science_text = _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2] + grouped["event_driver"][:1]) or "相关空间物理问题"
    instrument_text = _tag_text(grouped["instrument_data"][:2]) or "相关数据"
    physical_text = _tag_text(grouped["result_feature"][:2] + grouped["application_impact"][:1]) or _tag_text(_prefer_deeper_tags(grouped["research_object"])[:2]) or "关键物理量"
    return f"文章围绕{science_text}，利用{instrument_text}分析了{physical_text}的变化特征。"


def infer_method(row: Row) -> str:
    text = normalize_haystack(row)
    methods: list[str] = []
    if any(keyword in text for keyword in ["observation", "observations", "measured", "measurement", "satellite", "radar"]):
        methods.append("观测分析")
    if any(keyword in text for keyword in ["deep learning", "machine learning", "neural network", "resnet", "机器学习", "深度学习"]):
        methods.append("机器学习建模")
    if any(
        keyword in text
        for keyword in [
            "first-principles",
            "first principles",
            "physics-based",
            "general circulation model",
            "mhd model",
            "gitm",
            "tie-gcm",
            "waccm-x",
            "ctipe",
            "swmf",
            "sami2",
            "sami3",
            "gaia",
            "bats-r-us",
        ]
    ):
        methods.append("理论数值模式")
    if any(keyword in text for keyword in ["empirical model", "hasdm", "nrlmsise", "msis", "hwm", "jb2008", "iri"]):
        methods.append("经验模型对比")
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


def fallback_tags_from_topics(row: Row, root: Path | None = None) -> list[str]:
    tags: list[str] = []
    for label in topic_labels(row):
        mapped = TOPIC_TO_TAG.get(label)
        if mapped:
            tags.append(mapped)
    return sanitize_tags(tags, root=root)


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


def _resolve_local_pdf_path(row: Row) -> Path | None:
    if "local_pdf_path" not in row.keys():
        return None
    raw = clean_text(row["local_pdf_path"])
    if not raw:
        return None
    return Path(raw).expanduser()


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


def build_tag_line(tags: list[str]) -> str:
    return " ".join(format_tag(tag) for tag in tags)


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


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clean_source_text(text: str) -> str:
    lines = [clean_text(line) for line in str(text or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


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


def load_article_summary_template(template_path: Path) -> str:
    template_text = template_path.read_text(encoding="utf-8")
    validate_article_summary_template(template_text, template_path)
    return template_text


def validate_article_summary_template(template_text: str, template_path: Path) -> None:
    missing_markers = [marker for marker in ARTICLE_SUMMARY_TEMPLATE_REQUIRED_MARKERS if marker not in template_text]
    if missing_markers:
        joined = "、".join(missing_markers)
        raise ValueError(f"Article summary template missing required markers in {template_path}: {joined}")

    found_vars = set(ARTICLE_SUMMARY_TEMPLATE_VAR_RE.findall(template_text))
    missing_vars = sorted(ARTICLE_SUMMARY_TEMPLATE_REQUIRED_VARS - found_vars)
    if missing_vars:
        joined = ", ".join(missing_vars)
        raise ValueError(f"Article summary template missing required placeholders in {template_path}: {joined}")


def render_article_summary_template(template_text: str, context: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise ValueError(f"Article summary template placeholder has no context value: {key}")
        return str(context[key])

    rendered = ARTICLE_SUMMARY_TEMPLATE_VAR_RE.sub(replace, template_text)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def build_numbered_block(items: list[str], empty_text: str = "暂留空。") -> str:
    normalized = dedupe(items)
    if not normalized:
        return f"\t1. {empty_text}"
    return "\n".join(f"\t{index}. {item}" for index, item in enumerate(normalized, start=1))


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
    *,
    raise_on_error: bool = False,
) -> ArticleAnalysis | None:
    if analysis_engine is None or get_override(row):
        return None
    try:
        return analysis_engine.analyze_article(row, index=index)
    except Exception:
        if raise_on_error:
            raise
        return None
