from __future__ import annotations

from pathlib import Path
from sqlite3 import Row

from .article_fetch import resolve_summary_source_material
from .article_summary_markdown import (
    ARTICLE_SUMMARY_TEMPLATE_REQUIRED_MARKERS,
    build_numbered_block,
    clean_source_text,
    clean_text,
    dedupe,
    extract_numbered_line,
    extract_related_report_links,
    extract_summary_body,
    extract_summary_tags,
    index_existing_summary_files,
    load_article_summary_template,
    normalize_doi,
    render_article_summary_markdown,
    upsert_related_reports_section,
)
from .article_summary_meta import build_resource_line, resolve_local_pdf_path, unique_output_path
from .article_summary_text import (
    ABSTRACT_ONLY_TAG,
    FULL_TEXT_SOURCE_KINDS,
    build_apa_citation,
    build_body_paragraph,
    build_chinese_title,
    build_filename_from_chinese,
    build_note_title,
    build_note_title_from_chinese,
    build_one_sentence_summary,
    build_recommendation,
    build_supplement_text,
    display_title,
    get_focus_tags,
    get_override,
    infer_tags_from_text,
    is_generic_sentence,
    normalize_summary_supplement,
    parse_authors,
    sanitize_generation_text,
    sanitize_tags,
    validate_summary_fields,
)
from .crossref import CrossrefClient
from .http import HTTPClient
from .llm import AnalysisEngine, ArticleAnalysis
from .models import ArticleSummaryResult

ARTICLE_SUMMARY_REVIEW_MAX_PASSES = 3


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
            local_pdf_path = resolve_local_pdf_path(row)
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
    resolved_note_title = note_title or build_note_title(row, analysis=analysis, root=root)
    resolved_tags = tags or get_focus_tags(row, analysis=analysis, root=root)
    resolved_body = body or build_body_paragraph(row, analysis=analysis, root=root)
    resolved_supplement = supplement or build_supplement_text(row, analysis=analysis, root=root)
    return render_article_summary_markdown(
        template_text,
        note_title=resolved_note_title,
        resource_line=build_resource_line(row, resolved_tags),
        apa_citation=build_apa_citation(row, analysis=analysis),
        body=resolved_body,
        supplement=resolved_supplement,
        related_reports_block=build_numbered_block(report_links or []),
    )


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
