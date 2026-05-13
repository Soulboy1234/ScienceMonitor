from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from sqlite3 import Row
from typing import Callable

from .article_fetch import (
    PDF_TEXT_EXTRACTOR_VERSION,
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
MAX_PDF_DOWNLOAD_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class DeepReadResult:
    success: bool
    message: str
    output_path: Path | None = None
    pdf_output_path: Path | None = None
    source_kind: str = ""


@dataclass(frozen=True)
class DeepReadBatchItem:
    pdf_path: Path
    result: DeepReadResult


@dataclass(frozen=True)
class DeepReadBatchResult:
    folder_path: Path
    total: int
    items: list[DeepReadBatchItem]

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.items if item.result.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for item in self.items if not item.result.success)

    @property
    def successful_outputs(self) -> list[Path]:
        return [item.result.output_path for item in self.items if item.result.success and item.result.output_path is not None]

    @property
    def failed_items(self) -> list[DeepReadBatchItem]:
        return [item for item in self.items if not item.result.success]


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
    progress_callback: Callable[[dict], None] | None = None,
) -> DeepReadResult:
    project = root or project_root()
    _emit_deep_read_progress(progress_callback, stage="metadata", message="正在解析论文信息。")
    runtime = runtime_override or load_runtime_config(project)
    if not runtime.get("features", {}).get("weekly_report_enabled", True):
        # no-op; weekly report toggle should not block deep reads
        pass

    analysis_engine = AnalysisEngine(project)
    if not analysis_engine.deep_read_enabled():
        return DeepReadResult(False, "当前分析后端不可用，深度解读无法继续。请先在设置里切换到可用的 LLM 后端。")
    if not analysis_engine.provider_status().get("provider_supported", False):
        return DeepReadResult(False, "当前 analysis provider 不再受支持。请切换到 codex_local、openai_api、openrouter_api、ollama_api 或人工中转。")

    explicit_pdf = Path(pdf_path).expanduser() if pdf_path else None
    metadata = _resolve_metadata(storage, doi=doi, title=title, journal=journal, url=url, explicit_pdf=explicit_pdf)
    if not metadata.get("title"):
        return DeepReadResult(False, "深度解读需要至少提供 DOI 或题目，且最好能在数据库或 Crossref 中找到论文元数据。")

    if analysis_engine.provider == "chatgpt_web_manual":
        _emit_deep_read_progress(progress_callback, stage="analysis", message="正在生成人工中转深度解读请求。")
        resolution = FullTextResolution(
            success=True,
            source_kind="chatgpt_web_manual_search",
            full_text="",
            pdf_path=explicit_pdf if explicit_pdf and explicit_pdf.exists() else None,
            source_url=str(metadata.get("url", "") or url or ""),
        )
    else:
        _emit_deep_read_progress(progress_callback, stage="full_text", message="正在读取 PDF 或定位网页全文。")
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
        _emit_deep_read_progress(progress_callback, stage="analysis", message="正在调用当前 LLM 后端生成深度解读。")
        analysis = analysis_engine.analyze_deep_read(
            metadata,
            resolution.full_text,
            related_summary_payload,
            manual_context=manual_context,
            progress_callback=progress_callback,
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

    _emit_deep_read_progress(progress_callback, stage="render", message="正在准备输出文件和 PDF 链接。")
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
    _emit_deep_read_progress(progress_callback, stage="review", message="正在审核深度解读格式和标签。")
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
        _emit_deep_read_progress(progress_callback, stage="sync", message="正在同步输出索引。")
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


def run_deep_read_folder(
    root: Path | None,
    storage: Storage,
    folder_path: str | Path,
    *,
    recursive: bool = False,
    runtime_override: dict | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> DeepReadBatchResult:
    project = root or project_root()
    folder = Path(folder_path).expanduser()
    _emit_deep_read_progress(progress_callback, stage="batch_scanning", folder_path=str(folder))
    if not folder.exists():
        raise ValueError(f"PDF 文件夹不存在：{folder}")
    if not folder.is_dir():
        raise ValueError(f"给定路径不是文件夹：{folder}")

    pdf_files = list_deep_read_pdf_files(folder, recursive=recursive)
    _emit_deep_read_progress(progress_callback, stage="batch_scanning", total=len(pdf_files), completed=0)
    items: list[DeepReadBatchItem] = []
    success_count = 0
    failure_count = 0
    for index, pdf_file in enumerate(pdf_files, start=1):
        _emit_deep_read_progress(
            progress_callback,
            stage="batch_item_start",
            total=len(pdf_files),
            completed=index - 1,
            current_index=index,
            current_pdf=pdf_file.name,
        )
        try:
            result = run_deep_read(
                root=project,
                storage=storage,
                title=pdf_file.stem,
                pdf_path=str(pdf_file),
                runtime_override=runtime_override,
                progress_callback=(
                    lambda payload, *, _index=index, _total=len(pdf_files), _pdf=pdf_file: _emit_deep_read_progress(
                        progress_callback,
                        **{
                            **payload,
                            "total": _total,
                            "completed": _index - 1,
                            "current_index": _index,
                            "current_pdf": _pdf.name,
                        },
                    )
                ),
            )
        except Exception as exc:
            result = DeepReadResult(False, f"批量深度解读失败：{exc}")
        if result.success:
            success_count += 1
        else:
            failure_count += 1
        items.append(DeepReadBatchItem(pdf_path=pdf_file, result=result))
        _emit_deep_read_progress(
            progress_callback,
            stage="batch_item_done",
            total=len(pdf_files),
            completed=index,
            current_index=index,
            current_pdf=pdf_file.name,
            success_count=success_count,
            failure_count=failure_count,
            output_path=str(result.output_path) if result.output_path else "",
            source_kind=result.source_kind,
            message=_format_deep_read_batch_item_done_message(pdf_file, result, success_count, failure_count),
            last_failed_pdf=pdf_file.name if not result.success else "",
            last_failure_message=result.message if not result.success else "",
        )
    return DeepReadBatchResult(folder_path=folder, total=len(pdf_files), items=items)


def _format_deep_read_batch_item_done_message(
    pdf_file: Path,
    result: DeepReadResult,
    success_count: int,
    failure_count: int,
) -> str:
    if result.success:
        return f"已完成 {pdf_file.name}；当前成功 {success_count} 篇，失败 {failure_count} 篇。"
    return f"{pdf_file.name} 失败：{result.message} 当前成功 {success_count} 篇，失败 {failure_count} 篇。"


def list_deep_read_pdf_files(folder_path: str | Path, *, recursive: bool = False) -> list[Path]:
    folder = Path(folder_path).expanduser()
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    pdf_files = [
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() == ".pdf"
    ]
    return sorted(pdf_files, key=lambda path: str(path).lower())


def _emit_deep_read_progress(callback: Callable[[dict], None] | None, **payload: object) -> None:
    if callback is None:
        return
    callback(dict(payload))


def _resolve_metadata(
    storage: Storage,
    doi: str,
    title: str,
    journal: str,
    url: str,
    explicit_pdf: Path | None = None,
) -> dict[str, object]:
    row: Row | None = None
    cleaned_doi = normalize_doi(doi)
    cleaned_title = clean_title_text(title)
    pdf_metadata = _read_pdf_metadata(explicit_pdf)
    pdf_doi = normalize_doi(str(pdf_metadata.get("doi", "") or ""))
    pdf_title = clean_title_text(str(pdf_metadata.get("title", "") or ""))
    if cleaned_doi and pdf_doi and cleaned_doi != pdf_doi:
        raise ValueError(f"PDF 内嵌 DOI（{pdf_doi}）与输入 DOI（{cleaned_doi}）不一致，请确认后重试。")

    lookup_doi = cleaned_doi or pdf_doi
    lookup_title = _best_metadata_title(cleaned_title, pdf_title)
    if lookup_doi:
        row = storage.get_paper_by_doi(lookup_doi)
    if row is None and lookup_title and not _is_weak_metadata_title(lookup_title):
        row = storage.search_paper_by_title(lookup_title)
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

    if lookup_doi:
        looked_up = _search_crossref_by_doi(lookup_doi)
        if looked_up:
            return looked_up

    if lookup_title and not _is_weak_metadata_title(lookup_title):
        looked_up = _search_crossref_by_title(lookup_title)
        if looked_up and _metadata_title_matches_query(lookup_title, str(looked_up.get("title", "") or "")):
            return looked_up

    return {
        "doi": lookup_doi,
        "title": lookup_title or cleaned_title or pdf_title,
        "journal": journal.strip(),
        "url": url.strip(),
        "authors": "",
        "published_date": "",
        "raw_authors": "",
    }


def _read_pdf_metadata(pdf_path: Path | None) -> dict[str, str]:
    if pdf_path is None or not pdf_path.exists():
        return {}
    try:
        from pypdf import PdfReader
    except Exception:
        return {}
    try:
        reader = PdfReader(str(pdf_path))
        raw_metadata = reader.metadata or {}
    except Exception:
        return {}
    values: dict[str, str] = {}
    for key, value in dict(raw_metadata).items():
        clean_key = str(key or "").lstrip("/").strip().lower()
        clean_value = str(value or "").strip()
        if clean_key and clean_value:
            values[clean_key] = clean_value
    doi = (
        values.get("wps-articledoi")
        or values.get("articledoi")
        or values.get("doi")
        or values.get("dc.identifier")
        or ""
    )
    title = values.get("title", "")
    return {
        "doi": normalize_doi(doi),
        "title": clean_title_text(title),
    }


def _best_metadata_title(user_title: str, pdf_title: str) -> str:
    if pdf_title and (not user_title or _is_weak_metadata_title(user_title)):
        return pdf_title
    return user_title or pdf_title


def _is_weak_metadata_title(title: str) -> bool:
    clean = clean_title_text(title)
    if not clean:
        return True
    compact = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", clean)
    if len(compact) <= 4:
        return True
    normalized = re.sub(r"[\s._:-]+", "", clean).upper()
    if normalized in {"JGR", "JGRSP", "GRL", "EPS", "EOS", "SW", "AGU"}:
        return True
    words = re.findall(r"[A-Za-z]+", clean)
    if words and len(words) <= 2 and all(word.upper() == word for word in words):
        return True
    return False


def _metadata_title_matches_query(query: str, candidate: str) -> bool:
    clean_query = clean_title_text(query).lower()
    clean_candidate = clean_title_text(candidate).lower()
    if not clean_query or not clean_candidate:
        return False
    if clean_query in clean_candidate or clean_candidate in clean_query:
        return True
    query_tokens = _metadata_title_tokens(clean_query)
    candidate_tokens = _metadata_title_tokens(clean_candidate)
    if not query_tokens or not candidate_tokens:
        return False
    overlap = len(query_tokens & candidate_tokens)
    return overlap / max(min(len(query_tokens), len(candidate_tokens)), 1) >= 0.55


def _metadata_title_tokens(title: str) -> set[str]:
    stopwords = {"a", "an", "the", "of", "and", "or", "in", "on", "for", "to", "with", "by", "sp", "jgr", "grl"}
    return {
        token
        for token in re.findall(r"[a-z0-9]{2,}", title.lower())
        if token not in stopwords and not token.isdigit()
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
            pdf_page_limit = _runtime_pdf_page_limit(runtime)
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
                pdf_page_limit=pdf_page_limit,
            )
            return FullTextResolution(True, "provided_pdf", full_text=extracted, pdf_path=explicit_pdf, source_url=str(explicit_pdf))
        return FullTextResolution(False, "provided_pdf", message="提供的 PDF 未能提取出足够文本，请确认 PDF 可读。")

    cached = load_article_source_cache(project, doi=metadata.get("doi", ""), title=metadata.get("title", ""))
    if cached and str(cached.get("scientific_text", "")).strip() and _cached_source_matches_runtime(cached, runtime):
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
            pdf_page_limit = _runtime_pdf_page_limit(runtime)
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
                pdf_page_limit=pdf_page_limit,
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
        raw = http.get_bytes(pdf_url, headers={"Accept": "application/pdf,*/*"}, max_bytes=MAX_PDF_DOWNLOAD_BYTES)
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
    page_limit = _runtime_pdf_page_limit(runtime)
    extracted = extract_pdf_scientific_text(pdf_path, project_root=project, page_limit=page_limit)
    if extracted:
        return extracted
    pdftotext_bin = shutil.which("pdftotext") or str(project / ".venv" / "bin" / "pdftotext")
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


def _runtime_pdf_page_limit(runtime: dict) -> int:
    try:
        value = int(runtime.get("deep_read", {}).get("pdf_page_limit", 40))
    except (TypeError, ValueError):
        return 40
    return max(value, 0)


def _cached_source_matches_runtime(cached: dict, runtime: dict) -> bool:
    source_kind = str(cached.get("source_kind", "") or "")
    if source_kind not in {"provided_pdf", "downloaded_pdf", "local_pdf_full_text"}:
        return True
    if str(cached.get("text_extractor_version", "") or "") != PDF_TEXT_EXTRACTOR_VERSION:
        return False
    if "pdf_page_limit" not in cached:
        return False
    try:
        cached_limit = int(cached.get("pdf_page_limit"))
    except (TypeError, ValueError):
        return False
    return cached_limit == _runtime_pdf_page_limit(runtime)


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
        links.append(_render_pdf_resource_link(note_path=note_path, pdf_path=pdf_path))
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


def _render_pdf_resource_link(*, note_path: Path, pdf_path: Path) -> str:
    relative = Path(os.path.relpath(pdf_path.resolve(), note_path.parent.resolve())).as_posix()
    return f"[PDF](<{relative}>)"


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
        if tag not in merged_tags:
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
            max_tags=14,
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
    inferred_candidates = infer_preferred_tags_from_text(
        title_text=metadata_title,
        body_text=full_text,
        root=project,
        max_tags=50,
    )
    inferred_tags = review_generated_tags(
        inferred_candidates,
        root=project,
        max_tags=50,
        context="deep_read_inferred",
        title_text=metadata_title,
        body_text=full_text,
        record_candidates=False,
    )
    extra: list[str] = []
    for tag in inferred_tags:
        if tag.startswith(("仪器/", "数据/", "模型/", "方法/")) and tag not in extra:
            extra.append(tag)
    evidence_text = f"{metadata_title}\n{full_text}"
    signal_rules = (
        (r"\bsubstorms?\b|亚暴", "事件/亚暴"),
        (r"\baurora\w*\b|极光", "对象/极区/极光"),
        (r"field[-\s]?aligned current|FACs?\b|场向电流|电流体系|current\s*lines?|currentlines?|电流线", "对象/磁层/电流体系"),
        (r"solar wind.{0,3}magnetosphere|solarwind.{0,3}magnetosphere|S[-–—]M dynamo|太阳风[-－—]磁层|太阳风耦合", "对象/磁层/太阳风耦合"),
        (r"magnetic reconnection|磁重联", "事件/磁重联"),
    )
    for pattern, tag in signal_rules:
        if re.search(pattern, evidence_text, flags=re.IGNORECASE) and tag not in extra:
            extra.append(tag)
    return extra


def _filter_deep_read_tags(project: Path, metadata_title: str, full_text: str, tags: list[str]) -> list[str]:
    if not tags:
        return tags
    candidate_tags = [tag for tag in tags if not _is_virtual_deep_read_object_tag(tag)]
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
    specific_research_tags = [tag for tag in candidate_tags if "/" in tag]
    if not inferred or not specific_research_tags:
        return candidate_tags
    filtered: list[str] = []
    for tag in candidate_tags:
        if tag in generic_research_tags and tag not in inferred:
            continue
        filtered.append(tag)
    return filtered


def _is_virtual_deep_read_object_tag(tag: str) -> bool:
    clean = str(tag or "").strip()
    if clean == "对象/动力学过程":
        return True
    return clean.startswith(
        (
            "对象/物理机制",
            "对象/能量转换",
            "对象/过程",
            "对象/机制",
        )
    )


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
