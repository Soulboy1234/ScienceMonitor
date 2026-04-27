from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from .article_fetch import (
    build_candidate_article_urls,
    extract_pdf_scientific_text,
    fetch_article_page_snapshot,
    load_article_source_cache,
    prepare_scientific_source_text,
    write_article_source_cache,
)
from .article_summary_markdown import (
    build_tag_line,
    extract_related_report_links,
    extract_summary_tags,
    normalize_doi,
    obsidian_link,
    obsidian_target,
    sanitize_filename,
)
from .article_summary_meta import (
    abbreviate_journal_name,
    build_doi_url,
    first_author_label,
    format_authors_apa,
    parse_authors,
)
from .article_summary_text import GPT_SUMMARY_TAG
from .article_index import sync_out_library
from .config import (
    article_summaries_root,
    article_sub_index_root,
    deep_reads_pdf_root,
    deep_reads_root,
    load_runtime_config,
    output_root,
    project_root,
    templates_root,
)
from .crossref import CrossrefClient
from .deep_read_markdown import (
    _load_deep_read_template,
    _normalize_contribution_text,
    _normalize_deep_read_text,
    _normalize_goal_text,
    _normalize_key_results_text,
    _normalize_one_sentence_overview,
    _normalize_relation_to_my_work_text,
    _normalize_structured_deep_read_text,
    _render_deep_read_template,
    _run_deep_read_review_loop,
    _validate_deep_read_markdown,
)
from .http import HTTPClient
from .chatgpt_web_manual import ManualResponsePending
from .llm import AnalysisEngine, DeepReadAnalysis
from .storage import Storage
from .tag_review import review_generated_tags
from .tags import infer_preferred_tags_from_text, normalize_tags
from .tag_governance import refresh_pending_tag_files
from .utils import clean_abstract_text, clean_title_text

DEEP_READ_EXCLUDED_SUMMARY_TAG_PREFIXES = ("信息来源/",)


@dataclass(frozen=True)
class DeepReadResult:
    success: bool
    message: str
    output_path: Path | None = None
    pdf_output_path: Path | None = None
    source_kind: str = ""


@dataclass(frozen=True)
class FullTextResolution:
    success: bool
    source_kind: str
    full_text: str = ""
    pdf_path: Path | None = None
    source_url: str = ""
    message: str = ""


def run_deep_read(
    root: Path | None,
    storage: Storage,
    doi: str = "",
    title: str = "",
    pdf_path: str = "",
    journal: str = "",
    url: str = "",
    output_dir_override: Path | None = None,
    pdf_dir_override: Path | None = None,
    sync_library: bool = True,
    related_summary_override: Path | None = None,
    runtime_override: dict | None = None,
) -> DeepReadResult:
    project = root or project_root()
    runtime = runtime_override or load_runtime_config(project)
    if not runtime.get("features", {}).get("weekly_report_enabled", True):
        # no-op; weekly report toggle should not block deep reads
        pass

    analysis_engine = AnalysisEngine(project)
    if not analysis_engine.deep_read_enabled():
        return DeepReadResult(False, "当前分析后端不可用，深度解读无法继续。请先在设置里切换到可用的 LLM 后端。")
    if not analysis_engine.provider_status().get("provider_supported", False):
        return DeepReadResult(False, "当前 analysis provider 不再受支持。请切换到 codex_local、openai_api、openrouter_api、ollama_api 或人工中转。")

    metadata = _resolve_metadata(storage, doi=doi, title=title, journal=journal, url=url)
    if not metadata.get("title"):
        return DeepReadResult(False, "深度解读需要至少提供 DOI 或题目，且最好能在数据库或 Crossref 中找到论文元数据。")

    explicit_pdf = Path(pdf_path).expanduser() if pdf_path else None
    if analysis_engine.provider == "chatgpt_web_manual":
        resolution = FullTextResolution(
            success=True,
            source_kind="chatgpt_web_manual_search",
            full_text="",
            pdf_path=explicit_pdf if explicit_pdf and explicit_pdf.exists() else None,
            source_url=str(metadata.get("url", "") or url or ""),
        )
    else:
        resolution = _resolve_full_text(
            project,
            metadata=metadata,
            explicit_pdf=explicit_pdf,
            runtime=runtime,
        )
        if not resolution.success:
            return DeepReadResult(False, resolution.message, source_kind=resolution.source_kind)

    related_summary = related_summary_override or _find_related_summary(project, metadata.get("doi", ""))
    related_summary_payload = _summary_payload(related_summary) if related_summary else None
    manual_context = {
        "request_kind": "deep_read",
        "title": clean_title_text(str(metadata.get("title", "") or "")) or str(metadata.get("doi", "") or "deep_read"),
        "request_label": _manual_deep_read_label(metadata, explicit_pdf),
        "resource_hints": {
            "title": str(metadata.get("title", "") or ""),
            "doi": str(metadata.get("doi", "") or ""),
            "url": str(metadata.get("url", "") or url or ""),
            "journal": str(metadata.get("journal", "") or ""),
            "published_date": str(metadata.get("published_date", "") or ""),
            "authors": str(metadata.get("authors", "") or ""),
        },
        "pdf_hint_path": str(explicit_pdf) if explicit_pdf else "",
    }
    try:
        analysis = analysis_engine.analyze_deep_read(
            metadata,
            resolution.full_text,
            related_summary_payload,
            manual_context=manual_context,
        )
    except ManualResponsePending as exc:
        return DeepReadResult(False, str(exc), source_kind=resolution.source_kind)
    if analysis is None:
        return DeepReadResult(False, "深度解读分析未生成结果。请检查当前 provider、额度或输入文本长度。", source_kind=resolution.source_kind)
    analysis = _normalize_deep_read_analysis(
        project,
        analysis,
        metadata_title=str(metadata.get("title", "") or ""),
        full_text=resolution.full_text,
        related_summary=related_summary,
    )

    output_dir = output_dir_override or deep_reads_root(project)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = pdf_dir_override or deep_reads_pdf_root(project)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    linked_pdf_path = None
    if resolution.pdf_path and resolution.pdf_path.exists():
        target_pdf_name = sanitize_filename(resolution.pdf_path.name)
        linked_pdf_path = pdf_dir / target_pdf_name
        if resolution.pdf_path.resolve() != linked_pdf_path.resolve():
            shutil.copy2(resolution.pdf_path, linked_pdf_path)
        else:
            linked_pdf_path = resolution.pdf_path

    template_text = _load_deep_read_template(templates_root(project) / "deep_reading_report_template.md")
    note_path = _build_deep_read_output_path(project, output_dir, metadata, analysis, related_summary)
    markdown = _render_deep_read_markdown(
        project=project,
        template_text=template_text,
        metadata=metadata,
        analysis=analysis,
        related_summary=related_summary,
        note_path=note_path,
        pdf_path=linked_pdf_path,
        source_kind=resolution.source_kind,
        source_url=resolution.source_url,
        knowledge_position_text=_build_knowledge_position_text(project, note_path, sync_library=False),
    )
    markdown, review_issues = _run_deep_read_review_loop(markdown, tags=analysis.tags)
    validation_issues = review_issues + _validate_deep_read_markdown(
        markdown,
        is_output_note=_is_note_under_output_root(project, note_path),
    )
    if validation_issues:
        return DeepReadResult(
            False,
            "深度解读生成结果未通过模板校验：" + "；".join(validation_issues),
            source_kind=resolution.source_kind,
        )
    note_path.write_text(markdown, encoding="utf-8")
    refresh_pending_tag_files(project)
    if sync_library:
        sync_out_library(project)
        resolved_knowledge_position = _build_knowledge_position_text(project, note_path, sync_library=True)
        updated_markdown = _render_deep_read_markdown(
            project=project,
            template_text=template_text,
            metadata=metadata,
            analysis=analysis,
            related_summary=related_summary,
            note_path=note_path,
            pdf_path=linked_pdf_path,
            source_kind=resolution.source_kind,
            source_url=resolution.source_url,
            knowledge_position_text=resolved_knowledge_position,
        )
        updated_markdown, review_issues = _run_deep_read_review_loop(updated_markdown, tags=analysis.tags)
        validation_issues = review_issues + _validate_deep_read_markdown(
            updated_markdown,
            is_output_note=_is_note_under_output_root(project, note_path),
        )
        if validation_issues:
            return DeepReadResult(
                False,
                "深度解读生成结果未通过模板校验：" + "；".join(validation_issues),
                source_kind=resolution.source_kind,
            )
        if updated_markdown != markdown:
            note_path.write_text(updated_markdown, encoding="utf-8")
    return DeepReadResult(
        success=True,
        message="ok",
        output_path=note_path,
        pdf_output_path=linked_pdf_path,
        source_kind=resolution.source_kind,
    )


def _resolve_metadata(
    storage: Storage,
    doi: str,
    title: str,
    journal: str,
    url: str,
) -> dict[str, object]:
    row: Row | None = None
    cleaned_doi = normalize_doi(doi)
    cleaned_title = clean_title_text(title)
    if cleaned_doi:
        row = storage.get_paper_by_doi(cleaned_doi)
    if row is None and cleaned_title:
        row = storage.search_paper_by_title(cleaned_title)
    if row is not None:
        return {
            "doi": row["doi"],
            "title": row["title"],
            "journal": row["source_name"],
            "url": row["url"],
            "authors": row["authors"],
            "published_date": row["published_date"],
            "raw_authors": row["authors"],
        }

    if cleaned_doi:
        looked_up = _search_crossref_by_doi(cleaned_doi)
        if looked_up:
            return looked_up

    if cleaned_title:
        looked_up = _search_crossref_by_title(cleaned_title)
        if looked_up:
            return looked_up

    return {
        "doi": cleaned_doi,
        "title": cleaned_title,
        "journal": journal.strip(),
        "url": url.strip(),
        "authors": "",
        "published_date": "",
        "raw_authors": "",
    }


def _manual_deep_read_label(metadata: dict[str, object], explicit_pdf: Path | None) -> str:
    candidates = [
        explicit_pdf.stem if explicit_pdf else "",
        str(metadata.get("doi", "") or ""),
        str(metadata.get("title", "") or ""),
    ]
    for value in candidates:
        clean = sanitize_filename(str(value or "")).replace(" ", "_").strip("._")
        if clean:
            return clean[:64]
    return "deep_read"


def _search_crossref_by_doi(doi: str) -> dict[str, object] | None:
    client = CrossrefClient(HTTPClient())
    try:
        return _crossref_payload_to_metadata(client.lookup_work_by_doi(doi))
    except Exception:
        return None


def _search_crossref_by_title(title: str) -> dict[str, object] | None:
    client = CrossrefClient(HTTPClient())
    try:
        return _crossref_payload_to_metadata(client.lookup_work_by_title(title))
    except Exception:
        return None


def _crossref_payload_to_metadata(payload: dict | None) -> dict[str, object] | None:
    if not payload:
        return None
    authors = [str(item).strip() for item in payload.get("authors", []) if str(item).strip()]
    return {
        "doi": str(payload.get("doi", "") or ""),
        "title": clean_title_text(str(payload.get("title", "") or "")),
        "journal": str(payload.get("journal", "") or ""),
        "url": str(payload.get("url", "") or ""),
        "authors": "\n".join(authors),
        "published_date": str(payload.get("published_date", "") or ""),
        "raw_authors": "\n".join(authors),
        "pdf_urls": list(payload.get("pdf_urls", []) or []),
    }


def _resolve_full_text(
    project: Path,
    metadata: dict[str, str],
    explicit_pdf: Path | None,
    runtime: dict,
) -> FullTextResolution:
    if explicit_pdf:
        if not explicit_pdf.exists():
            return FullTextResolution(False, "provided_pdf", message=f"提供的 PDF 不存在：{explicit_pdf}")
        extracted = _extract_pdf_text(project, explicit_pdf, runtime)
        if extracted:
            write_article_source_cache(
                project,
                doi=metadata.get("doi", ""),
                title=metadata.get("title", ""),
                journal=metadata.get("journal", ""),
                source_kind="provided_pdf",
                source_url=str(explicit_pdf),
                pdf_path=str(explicit_pdf),
                scientific_text=extracted,
                summary_packet="",
            )
            return FullTextResolution(True, "provided_pdf", full_text=extracted, pdf_path=explicit_pdf, source_url=str(explicit_pdf))
        return FullTextResolution(False, "provided_pdf", message="提供的 PDF 未能提取出足够文本，请确认 PDF 可读。")

    cached = load_article_source_cache(project, doi=metadata.get("doi", ""), title=metadata.get("title", ""))
    if cached and str(cached.get("scientific_text", "")).strip():
        cached_pdf = Path(str(cached.get("pdf_path", "") or "")).expanduser() if str(cached.get("pdf_path", "") or "").strip() else None
        if cached_pdf is not None and not cached_pdf.exists():
            cached_pdf = None
        return FullTextResolution(
            True,
            str(cached.get("source_kind", "cached_full_text") or "cached_full_text"),
            full_text=str(cached.get("scientific_text", "")).strip(),
            pdf_path=cached_pdf,
            source_url=str(cached.get("source_url", "") or ""),
        )

    if not runtime.get("deep_read", {}).get("search_full_text_when_pdf_missing", True):
        return FullTextResolution(False, "missing_pdf", message="当前配置禁止在缺少 PDF 时自动搜索全文。请提供文章 PDF。")

    http = HTTPClient(timeout=20)
    crossref_meta = _search_crossref_by_doi(metadata.get("doi", "")) if metadata.get("doi") else None
    snapshot = fetch_article_page_snapshot(
        http,
        build_candidate_article_urls(
            metadata.get("doi", ""),
            metadata.get("url", ""),
            extra_urls=[str((crossref_meta or {}).get("url", "") or "")],
        ),
    )
    pdf_urls = list((crossref_meta or {}).get("pdf_urls", []) or [])
    for item in snapshot.pdf_urls:
        if item not in pdf_urls:
            pdf_urls.append(item)
    for pdf_url in pdf_urls:
        downloaded = _download_pdf(http, pdf_url, project)
        if downloaded is None:
            continue
        extracted = _extract_pdf_text(project, downloaded, runtime)
        if extracted:
            write_article_source_cache(
                project,
                doi=metadata.get("doi", ""),
                title=metadata.get("title", ""),
                journal=metadata.get("journal", ""),
                source_kind="downloaded_pdf",
                source_url=pdf_url,
                pdf_path=str(downloaded),
                scientific_text=extracted,
                summary_packet="",
            )
            return FullTextResolution(True, "downloaded_pdf", full_text=extracted, pdf_path=downloaded, source_url=pdf_url)
    if snapshot.is_full_text:
        scientific_text = prepare_scientific_source_text(snapshot.full_text)
        if scientific_text:
            write_article_source_cache(
                project,
                doi=metadata.get("doi", ""),
                title=metadata.get("title", ""),
                journal=metadata.get("journal", ""),
                source_kind="html_full_text",
                source_url=snapshot.source_url,
                pdf_path="",
                scientific_text=scientific_text,
                summary_packet="",
            )
        return FullTextResolution(
            True,
            "html_full_text",
            full_text=scientific_text or snapshot.full_text,
            pdf_path=None,
            source_url=snapshot.source_url,
        )

    return FullTextResolution(
        False,
        "search_failed",
        message="深度解读失败：未提供 PDF，且程序未能根据 DOI/题目获取到可用于深度解读的全文。请提供文章 PDF。",
    )


def _download_pdf(http: HTTPClient, pdf_url: str, project: Path) -> Path | None:
    try:
        raw = http.get_bytes(pdf_url, headers={"Accept": "application/pdf,*/*"})
    except Exception:
        return None
    if not raw.startswith(b"%PDF"):
        return None
    tmp_dir = project / "tmp" / "downloaded_pdf"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(pdf_url.rsplit("/", 1)[-1] or "downloaded.pdf")
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    path = tmp_dir / filename
    path.write_bytes(raw)
    return path


def _extract_pdf_text(project: Path, pdf_path: Path, runtime: dict) -> str:
    extracted = extract_pdf_scientific_text(pdf_path, project_root=project)
    if extracted:
        return extracted
    pdftotext_bin = shutil.which("pdftotext") or str(project / ".venv" / "bin" / "pdftotext")
    page_limit = int(runtime.get("deep_read", {}).get("pdf_page_limit", 40) or 40)
    command = [pdftotext_bin, "-nopgbrk", "-f", "1"]
    if page_limit > 0:
        command.extend(["-l", str(page_limit)])
    command.extend([str(pdf_path), "-"])
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    return clean_abstract_text(result.stdout)


def _find_related_summary(project: Path, doi: str) -> Path | None:
    if not doi:
        return None
    normalized = normalize_doi(doi)
    for note in article_summaries_root(project).glob("*.md"):
        try:
            text = note.read_text(encoding="utf-8")
        except Exception:
            continue
        if normalize_doi(normalized) and normalize_doi(normalized) in normalize_doi(text):
            return note
        doi_link = build_doi_url(doi, "")
        if doi_link and doi_link in text:
            return note
    return None


def _summary_payload(summary_path: Path) -> dict[str, str]:
    text = summary_path.read_text(encoding="utf-8")
    title = summary_path.stem
    tags = []
    for line in text.splitlines():
        if line.startswith("- ") and "#" in line:
            tags = [item for item in line.split() if item.startswith("#")]
            break
    one_sentence = ""
    for line in text.splitlines():
        if line.startswith("- 正文内容"):
            continue
        if "一句话" in line:
            one_sentence = line.strip()
            break
    return {
        "path": str(summary_path),
        "chinese_title": title,
        "tags": " ".join(tags),
        "one_sentence": one_sentence,
    }


def _build_deep_read_output_path(
    project: Path,
    output_dir: Path,
    metadata: dict[str, str],
    analysis: DeepReadAnalysis,
    related_summary: Path | None,
) -> Path:
    if related_summary:
        base = sanitize_filename(related_summary.stem)
        filename = f"{base} 深度解读.md"
    else:
        first_author = first_author_label(metadata.get("raw_authors", "") or metadata.get("authors", ""))
        year = (metadata.get("published_date", "") or "Unknown")[:4]
        journal = sanitize_filename(abbreviate_journal_name(metadata.get("journal", "") or "Unknown"))
        chinese = sanitize_filename(clean_title_text(analysis.chinese_title))[:72].rstrip()
        filename = f"{first_author} {year} - {journal} - {chinese} 深度解读.md"
    return output_dir / filename


def _render_deep_read_markdown(
    project: Path,
    template_text: str,
    metadata: dict[str, str],
    analysis: DeepReadAnalysis,
    related_summary: Path | None,
    note_path: Path,
    pdf_path: Path | None,
    source_kind: str,
    source_url: str,
    knowledge_position_text: str,
) -> str:
    report_links = extract_related_report_links(related_summary.read_text(encoding="utf-8")) if related_summary and related_summary.exists() else []
    links = []
    if pdf_path:
        links.append(_render_note_resource_link(project, note_path=note_path, target_path=pdf_path, label="PDF"))
    else:
        doi_url = build_doi_url(metadata.get("doi", ""), source_url or metadata.get("url", ""))
        if doi_url:
            links.append(f"[DOI]({doi_url})")
    if related_summary:
        links.append(_render_note_resource_link(project, note_path=note_path, target_path=related_summary, label="单篇总结"))
    if report_links:
        links.extend(report_links[:1])
    output_tags = list(analysis.tags)
    if source_kind == "chatgpt_web_manual_search" and GPT_SUMMARY_TAG not in output_tags:
        output_tags.append(GPT_SUMMARY_TAG)
    tag_text = build_tag_line(output_tags)
    authors = parse_authors(metadata.get("raw_authors", "") or metadata.get("authors", ""))
    authors_text = format_authors_apa(authors) if authors else "Unknown"
    year = (metadata.get("published_date", "") or "Unknown")[:4]
    doi_url = build_doi_url(metadata.get("doi", ""), source_url or metadata.get("url", ""))
    apa = f"{authors_text} ({year}). {clean_title_text(metadata.get('title', ''))}. {metadata.get('journal', '')}. {doi_url}".strip()
    return _render_deep_read_template(
        template_text,
        {
            "entry_line": f"- {' '.join(links)} {tag_text}".rstrip(),
            "apa_citation": apa,
            "title": clean_title_text(metadata.get("title", "")),
            "authors": metadata.get("authors", "").replace(chr(10), ", "),
            "journal": metadata.get("journal", ""),
            "year": year,
            "paper_type": analysis.paper_type or "研究论文",
            "one_sentence_overview": analysis.one_sentence_overview,
            "why": analysis.why,
            "how": analysis.how,
            "key_results": analysis.key_results,
            "contribution": analysis.contribution,
            "limitations": analysis.limitations,
            "reproducibility": analysis.reproducibility,
            "relation": analysis.relation,
            "final_conclusion": analysis.final_conclusion,
            "relation_to_my_work": analysis.relation_to_my_work,
            "follow_up_questions": analysis.follow_up_questions,
            "needs_manual_review": analysis.needs_manual_review,
            "knowledge_position": knowledge_position_text,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
    )


def _render_note_resource_link(project: Path, *, note_path: Path, target_path: Path, label: str) -> str:
    note_is_output = _is_note_under_output_root(project, note_path)
    target_is_output = _is_note_under_output_root(project, target_path)
    if note_is_output and target_is_output:
        return obsidian_link(target_path, label, root=project)
    relative = os.path.relpath(target_path.resolve(), note_path.parent.resolve())
    return f"[{label}]({Path(relative).as_posix()})"


def _normalize_deep_read_analysis(
    project: Path,
    analysis: DeepReadAnalysis,
    *,
    metadata_title: str,
    full_text: str,
    related_summary: Path | None = None,
) -> DeepReadAnalysis:
    summary_tags = _load_related_summary_tags(related_summary)
    inferred_tags = _infer_additional_deep_read_tags(
        project,
        metadata_title=metadata_title,
        full_text=full_text,
    )
    merged_tags = list(analysis.tags)
    for tag in summary_tags:
        if tag not in merged_tags:
            merged_tags.append(tag)
    for tag in inferred_tags:
        if tag.startswith("仪器/") and tag not in merged_tags:
            merged_tags.append(tag)
    merged_tags = _filter_deep_read_source_status_tags(merged_tags)
    related_summary_tag_evidence = "related_summary_tags: " + " ".join(summary_tags) if summary_tags else ""
    normalized_tags = _filter_deep_read_tags(
        project,
        metadata_title=metadata_title,
        full_text=full_text,
        tags=review_generated_tags(
            merged_tags,
            root=project,
            max_tags=10,
            context="deep_read",
            record_candidates=True,
            title_text=metadata_title,
            body_text=full_text,
            extra_text=related_summary_tag_evidence,
        ),
    )
    return replace(
        analysis,
        chinese_title=clean_title_text(analysis.chinese_title),
        tags=normalized_tags,
        paper_type=_normalize_deep_read_text(analysis.paper_type),
        one_sentence_overview=_normalize_one_sentence_overview(analysis.one_sentence_overview),
        why=_normalize_goal_text(analysis.why, tags=normalized_tags),
        how=_normalize_structured_deep_read_text(analysis.how),
        key_results=_normalize_key_results_text(analysis.key_results),
        contribution=_normalize_contribution_text(analysis.contribution),
        limitations=_normalize_structured_deep_read_text(analysis.limitations),
        reproducibility=_normalize_structured_deep_read_text(analysis.reproducibility),
        relation=_normalize_structured_deep_read_text(analysis.relation),
        final_conclusion=_normalize_structured_deep_read_text(analysis.final_conclusion),
        relation_to_my_work=_normalize_relation_to_my_work_text(analysis.relation_to_my_work, tags=normalized_tags),
        follow_up_questions=_normalize_structured_deep_read_text(analysis.follow_up_questions),
        needs_manual_review=_normalize_structured_deep_read_text(analysis.needs_manual_review),
        knowledge_position=_normalize_structured_deep_read_text(analysis.knowledge_position),
    )


def _load_related_summary_tags(summary_path: Path | None) -> list[str]:
    if summary_path is None or not summary_path.exists():
        return []
    try:
        text = summary_path.read_text(encoding="utf-8")
    except Exception:
        return []
    return extract_summary_tags(text)


def _filter_deep_read_source_status_tags(tags: list[str]) -> list[str]:
    return [
        tag
        for tag in tags
        if not any(tag.startswith(prefix) for prefix in DEEP_READ_EXCLUDED_SUMMARY_TAG_PREFIXES)
    ]


def _infer_additional_deep_read_tags(project: Path, *, metadata_title: str, full_text: str) -> list[str]:
    inferred_tags = normalize_tags(
        infer_preferred_tags_from_text(
            title_text=metadata_title,
            body_text=full_text,
            root=project,
            max_tags=50,
        ),
        root=project,
        max_tags=50,
        context="deep_read_inferred",
    )
    extra: list[str] = []
    if "仪器/极光图像" in inferred_tags:
        extra.append("仪器/极光图像")
    return extra


def _filter_deep_read_tags(project: Path, metadata_title: str, full_text: str, tags: list[str]) -> list[str]:
    if not tags:
        return tags
    generic_research_tags = {"热层", "电离层", "磁层"}
    inferred = set(
        normalize_tags(
            infer_preferred_tags_from_text(
                title_text=metadata_title,
                body_text=full_text,
                root=project,
                max_tags=10,
            ),
            root=project,
            max_tags=10,
            context="deep_read_inferred",
        )
    )
    specific_research_tags = [tag for tag in tags if "/" in tag]
    if not inferred or not specific_research_tags:
        return tags
    filtered: list[str] = []
    for tag in tags:
        if tag in generic_research_tags and tag not in inferred:
            continue
        filtered.append(tag)
    return filtered or tags


def _build_knowledge_position_text(project: Path, note_path: Path, *, sync_library: bool) -> str:
    if not _is_note_under_output_root(project, note_path):
        return "当前为评测输出，未写入 output_root，未生成 article_index 索引链接。"
    if not sync_library:
        return "当前笔记写入生产输出目录后，会在同步 article_index 后回填索引链接。"
    links = _find_article_index_links_for_note(project, note_path)
    if not links:
        return "已写入 output_root，但当前尚未发现 article_index 索引链接。"
    return "\n".join(f"{index}. {link}" for index, link in enumerate(links, start=1))


def _is_note_under_output_root(project: Path, note_path: Path) -> bool:
    try:
        note_path.resolve().relative_to(output_root(project).resolve())
        return True
    except ValueError:
        return False


def _find_article_index_links_for_note(project: Path, note_path: Path) -> list[str]:
    target = obsidian_target(note_path, root=project)
    links: list[str] = []
    for page_path in sorted(article_sub_index_root(project).glob("*.md")):
        try:
            text = page_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if f"[[{target}|" in text or f"[[{target}]]" in text:
            links.append(obsidian_link(page_path, page_path.stem, root=project))
    deduped: list[str] = []
    seen: set[str] = set()
    for link in links:
        if link not in seen:
            deduped.append(link)
            seen.add(link)
    return deduped
