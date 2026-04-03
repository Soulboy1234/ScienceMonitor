from __future__ import annotations

import json
import os
import re
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
from .article_summaries import (
    abbreviate_journal_name,
    build_doi_url,
    extract_related_report_links,
    extract_summary_tags,
    first_author_label,
    format_authors_apa,
    normalize_doi,
    obsidian_link,
    obsidian_target,
    parse_authors,
    sanitize_filename,
)
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
from .http import HTTPClient
from .llm import AnalysisEngine, DeepReadAnalysis
from .storage import Storage
from .tags import infer_preferred_tags_from_text, normalize_tags
from .utils import clean_abstract_text, clean_title_text


DEEP_READ_TEMPLATE_VAR_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
REQUIRED_DEEP_READ_HEADINGS = [
    "# 论文深度阅读报告",
    "## 论文信息",
    "### 一句话总述",
    "## 论文详解",
    "### 为什么做",
    "### 如何做",
    "### 关键结果",
    "### 新意与贡献",
    "### 局限性",
    "### 可复现性",
    "### 与已有工作的关系",
    "## 总结",
    "### 最终结论",
    "### 补充信息",
]
DEEP_READ_TEMPLATE_REQUIRED_VARS = {
    "entry_line",
    "apa_citation",
    "title",
    "authors",
    "journal",
    "year",
    "paper_type",
    "one_sentence_overview",
    "why",
    "how",
    "key_results",
    "contribution",
    "limitations",
    "reproducibility",
    "relation",
    "final_conclusion",
    "relation_to_my_work",
    "follow_up_questions",
    "needs_manual_review",
    "knowledge_position",
    "timestamp",
}

LEGACY_DEEP_READ_PATTERNS = [
    (r"^文件名：", "正文顶部不应包含文件名行"),
    (r"^##\s+Research question$", "不应继续使用旧版英文标题 Research question"),
    (r"^##\s+Paper type$", "不应继续使用旧版英文标题 Paper type"),
    (r"^##\s+Core claims$", "不应继续使用旧版英文标题 Core claims"),
    (r"^##\s+Method summary$", "不应继续使用旧版英文标题 Method summary"),
    (r"^##\s+Evidence assessment$", "不应继续使用旧版英文标题 Evidence assessment"),
    (r"^##\s+Reproducibility$", "不应继续使用旧版英文标题 Reproducibility"),
    (r"^##\s+Limitations and Hidden Assumptions$", "不应继续使用旧版英文标题 Limitations and Hidden Assumptions"),
    (r"^##\s+Related Work and Novelty$", "不应继续使用旧版英文标题 Related Work and Novelty"),
    (r"^##\s+Practical Takeaway$", "不应继续使用旧版英文标题 Practical Takeaway"),
    (r"^##\s+Confidence Level$", "不应继续使用旧版英文标题 Confidence Level"),
    (r"^##\s+标签（Tags）$", "不应继续使用旧版标签章节"),
    (r"目录归档建议", "不应继续输出目录归档建议区块"),
    (r"证据范围", "不应继续把证据范围作为正式报告区块"),
]
DEEP_READ_REVIEW_MAX_PASSES = 3

DEEP_READ_TEXT_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bday-to-day thermosphere variability\b", "热层日际变化"),
    (r"\brecurrent geomagnetic disturbances\b", "重复性地磁扰动"),
    (r"\bablation experiments?\b", "消融实验"),
    (r"\bablation\b", "消融"),
    (r"\bcontrolled simulations?\b", "受控实验"),
    (r"\bbenchmark(?:ing)?\b", "基线对照"),
    (r"\bback-of-envelope\b", "量级估算"),
    (r"\bdirect causal evidence\b", "直接因果证据"),
    (r"\boperational\b", "业务化"),
    (r"\bpaper type\b", "论文类型"),
    (r"\bresearch question\b", "研究问题"),
    (r"\bcore claims?\b", "核心主张"),
    (r"\bmethod summary\b", "方法概述"),
    (r"\bsupporting evidence\b", "支撑证据"),
    (r"\bevidence quality\b", "证据强度"),
    (r"\bverdict\b", "判断"),
    (r"\bdata or sample\b", "数据或样本"),
    (r"\bscope claim\b", "外推结论"),
    (r"\bsecondary claims?\b", "次要结论"),
    (r"\bprimary claim\b", "核心结论"),
    (r"\bcomparator\b", "对照"),
    (r"\bevaluation target\b", "评估目标"),
    (r"\bthermosphere-ionosphere dynamical coupling\b", "热层-电离层动力耦合"),
    (r"\bthermospheric wind uplift\b", "热层风抬升"),
    (r"\bdownward plasma transport\b", "向下等离子体输运"),
    (r"\btopside ionosphere\b", "顶侧电离层"),
    (r"\bconjugate hemisphere\b", "共轭半球"),
    (r"\bsummer-to-winter\b", "夏半球到冬半球"),
    (r"\bnear sunset\b", "接近日落"),
    (r"\baround midnight\b", "接近午夜"),
    (r"\boccurrence rate\b", "发生率"),
    (r"\blocal time\b", "地方时"),
    (r"\bduration\b", "持续时间"),
    (r"\bmajor mechanism\b", "主要机制"),
    (r"\bplasma source\b", "等离子体来源"),
    (r"\bfull text\b", "全文"),
    (r"\bthermospheric mass density\b", "热层质量密度"),
    (r"\bthermospheric density\b", "热层密度"),
    (r"\bsatellite drag\b", "卫星阻力"),
    (r"\bdrag environment\b", "阻力环境"),
    (r"\bthis paper\b", "这篇文章"),
    (r"\bthis study\b", "这项研究"),
]


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
) -> DeepReadResult:
    project = root or project_root()
    runtime = load_runtime_config(project)
    if not runtime.get("features", {}).get("weekly_report_enabled", True):
        # no-op; weekly report toggle should not block deep reads
        pass

    analysis_engine = AnalysisEngine(project)
    if not analysis_engine.deep_read_enabled():
        return DeepReadResult(False, "深度解读功能当前已关闭。请在配置界面或 PROJECT_CONFIG.md 中开启后再运行。")
    if not analysis_engine.provider_status().get("provider_supported", False):
        return DeepReadResult(False, "当前 analysis provider 不再受支持。请切换到 codex_local 或 openai_api。")

    metadata = _resolve_metadata(storage, doi=doi, title=title, journal=journal, url=url)
    if not metadata.get("title"):
        return DeepReadResult(False, "深度解读需要至少提供 DOI 或题目，且最好能在数据库或 Crossref 中找到论文元数据。")

    resolution = _resolve_full_text(
        project,
        metadata=metadata,
        explicit_pdf=Path(pdf_path).expanduser() if pdf_path else None,
        runtime=runtime,
    )
    if not resolution.success:
        return DeepReadResult(False, resolution.message, source_kind=resolution.source_kind)

    related_summary = related_summary_override or _find_related_summary(project, metadata.get("doi", ""))
    related_summary_payload = _summary_payload(related_summary) if related_summary else None
    analysis = analysis_engine.analyze_deep_read(metadata, resolution.full_text, related_summary_payload)
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
    markdown, review_issues = _run_deep_read_review_loop(
        project,
        markdown,
        note_path=note_path,
        tags=analysis.tags,
    )
    validation_issues = review_issues + _validate_deep_read_markdown(markdown, project=project, note_path=note_path)
    if validation_issues:
        return DeepReadResult(
            False,
            "深度解读生成结果未通过模板校验：" + "；".join(validation_issues),
            source_kind=resolution.source_kind,
        )
    note_path.write_text(markdown, encoding="utf-8")
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
        updated_markdown, review_issues = _run_deep_read_review_loop(
            project,
            updated_markdown,
            note_path=note_path,
            tags=analysis.tags,
        )
        validation_issues = review_issues + _validate_deep_read_markdown(
            updated_markdown,
            project=project,
            note_path=note_path,
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
    try:
        result = subprocess.run(
            [pdftotext_bin, "-nopgbrk", "-f", "1", "-l", str(page_limit), str(pdf_path), "-"],
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
    tag_text = " ".join("#" + tag.replace(" ", "") for tag in analysis.tags)
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
    normalized_tags = _filter_deep_read_tags(
        project,
        metadata_title=metadata_title,
        full_text=full_text,
        tags=normalize_tags(
            merged_tags,
            root=project,
            max_tags=10,
            context="deep_read",
            record_candidates=True,
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


def _normalize_deep_read_text(value: str) -> str:
    text = (value or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"([A-Za-z\u4e00-\u9fff])\s*\n-\s*([A-Za-z0-9\u4e00-\u9fff])", r"\1-\2", text)
    text = re.sub(r"(?<=\d)\s*\n\s*(?=\d)", "", text)
    text = re.sub(r"([A-Za-z]{2,})\s*\n\s*([A-Za-z]{2,})", r"\1 \2", text)
    text = re.sub(r"[ \t]+", " ", text)
    for pattern, replacement in DEEP_READ_TEXT_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.replace("消融 实验", "消融实验")
    text = text.replace("这个文章", "这篇文章")
    text = text.replace("This paper", "这篇文章")
    text = text.replace("This study", "这项研究")
    text = text.replace("‘", "“").replace("’", "”")
    text = re.sub(r"'([^'\n]{1,80})'", r"“\1”", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_one_sentence_overview(value: str) -> str:
    text = _normalize_deep_read_text(value)
    if text.startswith("这篇文章真正想回答的，不是") and "而是" in text:
        after = text.split("而是", 1)[1].strip()
        after = re.sub(r"^(更[^：]{0,10}[：:])", "", after)
        after = after.lstrip("：:，, ")
        text = f"这篇文章的目标是{after}"
    elif text.startswith("这篇文章想回答的，不是") and "而是" in text:
        after = text.split("而是", 1)[1].strip()
        after = after.lstrip("：:，, ")
        text = f"这篇文章的目标是{after}"
    elif text.startswith("这个文章真正想回答的，不是") and "而是" in text:
        after = text.split("而是", 1)[1].strip()
        after = after.lstrip("：:，, ")
        text = f"这篇文章的目标是{after}"
    elif re.match(r"^这篇文章[^。！？\n]{0,80}不是[^。！？\n]{0,120}而是", text):
        text = re.sub(r"^这篇文章[^。！？\n]{0,80}?而是", "这篇文章的目标是", text, count=1)
    text = text.replace("这篇文章的目标是更尖锐的一步：", "这篇文章的目标是")
    text = text.replace("这篇文章的目标是更进一步：", "这篇文章的目标是")
    if text and not re.match(r"^(这篇文章|作者)", text):
        text = f"这篇文章的目标是{text}"
    return text.strip()


def _normalize_goal_text(value: str, *, tags: list[str]) -> str:
    text = _normalize_structured_deep_read_text(value)
    if text:
        first_line, separator, remainder = text.partition("\n")
        normalized_first_line = first_line.strip()
        normalized_first_line = re.sub(r"^(作者研究的目标是|这篇文章的目标是)\s*", "", normalized_first_line)
        direct_target_match = re.search(
            r"(?:作者真正要解决的是|真正要解决的是|要解决的问题是)[:：]?\s*(.+)$",
            normalized_first_line,
        )
        if direct_target_match:
            normalized_first_line = f"作者要解决的问题是：{direct_target_match.group(1).strip()}"
        elif re.search(r"不是", normalized_first_line) and "而是" in normalized_first_line:
            after = normalized_first_line.split("而是", 1)[1].strip().lstrip("：:，, ")
            normalized_first_line = f"作者要解决的问题是：{after}"
        elif normalized_first_line and not normalized_first_line.startswith("作者要解决的问题是"):
            normalized_first_line = f"作者要解决的问题是：{normalized_first_line.lstrip('：:，, ')}"
        normalized_first_line = re.sub(
            r"^作者要解决的问题是：(?:作者|这篇文章)(?:希望|想|试图)?回答(?:的)?(?:问题)?[:：]?\s*",
            "作者要解决的问题是：",
            normalized_first_line,
        )
        text = normalized_first_line if not separator else f"{normalized_first_line}\n{remainder.strip()}"
    if not _supports_downstream_application(tags):
        text = _drop_downstream_sentences(text)
    return text.strip()


def _normalize_key_results_text(value: str) -> str:
    text = _normalize_structured_deep_read_text(value)
    lines = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        heading_candidate = re.sub(r"^#+\s*", "", stripped)
        if re.fullmatch(r"(硬结论|次级结论|合理推论|需进一步研究讨论的结论)[:：]?", heading_candidate):
            label = heading_candidate.rstrip("：:")
            lines.append(f"#### {label}")
            continue
        lines.append(stripped)
    return "\n".join(line for line in lines if line).strip()


def _normalize_contribution_text(value: str) -> str:
    text = _normalize_structured_deep_read_text(value)
    if "不是" in text and "而是" in text and re.match(r"^(这篇文章|文章|作者)[^。！？\n]{0,100}", text):
        after = text.split("而是", 1)[1].strip().lstrip("：:，, ")
        text = f"这篇文章的新意与贡献在于{after}"
    return text.strip()


def _normalize_structured_deep_read_text(value: str) -> str:
    text = _normalize_deep_read_text(value)
    for index, chinese in enumerate("一二三四五六七八九十", start=1):
        text = re.sub(rf"(?:(?<=^)|(?<=[。；]))\s*第{chinese}[，、]\s*", f"\n{index}. ", text)
    text = text.replace("合理解释：", "合理推论：")
    text = text.replace("合理解释:", "合理推论：")
    text = text.replace("需要进一步讨论/证明：", "需进一步研究讨论的结论：")
    text = text.replace("需要进一步讨论/证明:", "需进一步研究讨论的结论：")
    text = text.replace("仍需保留的部分：", "需进一步研究讨论的结论：")
    text = text.replace("仍需保留的部分:", "需进一步研究讨论的结论：")
    text = re.sub(r"(?<=[。；])(?=(?:硬结论|次级结论|合理推论|需进一步研究讨论的结论)[:：])", "\n", text)
    text = re.sub(r"(?<=[。！？；：])(?=(?:\d+[.．、)](?:\s+|$)))", "\n", text)
    text = re.sub(r"([。；：])\s+(?=(?:\d+[.．、)]|[-*])\s+)", r"\1\n", text)
    text = re.sub(r"(?:(?<=^)|(?<=\n))(\d+[.．、)])(?=\S)", r"\1 ", text)
    text = re.sub(
        r"(?<=[。！？；])(?=(?:整体看|总体看))",
        "\n",
        text,
    )
    lines = [line.rstrip() for line in text.splitlines()]
    normalized_lines: list[str] = []
    previous_was_list = False
    for line in lines:
        stripped = line.strip()
        is_list_item = bool(re.match(r"^(?:\d+[.．、)]\s+|[-*]\s+)", stripped))
        if not stripped:
            continue
        if not is_list_item and previous_was_list and normalized_lines and normalized_lines[-1] != "":
            normalized_lines.append("")
        normalized_lines.append(stripped)
        previous_was_list = is_list_item
    text = "\n".join(normalized_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_relation_to_my_work_text(value: str, *, tags: list[str]) -> str:
    text = _normalize_structured_deep_read_text(value)
    if _supports_downstream_application(tags):
        return text
    numbered_items = _extract_numbered_items(text)
    kept_items = [item for item in numbered_items if not _contains_downstream_keywords(item)]
    kept_paragraphs = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and not re.match(r"^\d+[.、)]\s+", line.strip())
        and not _contains_downstream_keywords(line.strip())
        and not re.search(r"([一二三四五六七八九十两\d]+个)?重要方向", line.strip())
    ]
    closing = "这项工作更适合作为边界区动力学个例和机制对照，不宜直接外推到业务化或定量应用。"
    lead_block = ""
    if kept_items:
        intro = "\n".join(kept_paragraphs) if kept_paragraphs else "它和当前主线的直接关系主要体现在以下几点。"
        lead_block = f"{intro}\n{_render_numbered_items(kept_items)}"
    elif kept_paragraphs:
        lead_block = "\n\n".join(kept_paragraphs)
    else:
        lead_block = _default_relation_to_my_work_lead(tags)
    if lead_block.rstrip() == closing:
        return lead_block.strip()
    return f"{lead_block.strip()}\n\n{closing}".strip()


def _supports_downstream_application(tags: list[str]) -> bool:
    return any(
        tag in {"热层/密度", "卫星影响", "业务化预报"}
        or tag.startswith("应用/")
        for tag in tags
    )


def _drop_downstream_sentences(text: str) -> str:
    downstream_keywords = (
        "热层密度",
        "卫星阻力",
        "业务化",
        "风险评估",
        "轨道维持",
        "轨道环境",
        "姿轨控",
        "再入预报",
        "星座任务",
        "工程影响",
    )
    lines = text.splitlines()
    kept_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if kept_lines and kept_lines[-1] != "":
                kept_lines.append("")
            continue
        prefix_match = re.match(r"^(\d+[.．、)]\s+|[-*]\s+)", stripped)
        prefix = prefix_match.group(1) if prefix_match else ""
        body = stripped[len(prefix):] if prefix else stripped
        pieces = re.split(r"(?<=[。！？])\s*", body)
        kept_pieces = [piece.strip() for piece in pieces if piece.strip() and not any(keyword in piece for keyword in downstream_keywords)]
        if not kept_pieces:
            continue
        rebuilt = "".join(kept_pieces).strip()
        if prefix:
            rebuilt = prefix + rebuilt
        kept_lines.append(rebuilt)
    while kept_lines and kept_lines[-1] == "":
        kept_lines.pop()
    if not kept_lines:
        return text
    return "\n".join(kept_lines)


def _contains_downstream_keywords(text: str) -> bool:
    downstream_keywords = (
        "热层密度",
        "密度模型",
        "卫星阻力",
        "阻力预报",
        "业务化",
        "风险评估",
        "轨道维持",
        "轨道环境",
        "姿轨控",
        "再入预报",
        "星座任务",
        "工程影响",
    )
    return any(keyword in text for keyword in downstream_keywords)


def _extract_numbered_items(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if re.match(r"^\d+[.、)]\s+", stripped):
            if current:
                items.append(" ".join(current).strip())
            current = [re.sub(r"^\d+[.、)]\s+", "", stripped, count=1).strip()]
            continue
        if current:
            current.append(stripped)
    if current:
        items.append(" ".join(current).strip())
    return items


def _render_numbered_items(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def _default_relation_to_my_work_lead(tags: list[str]) -> str:
    if "热层/风场" in tags and any(tag.startswith("极区/") for tag in tags):
        return "它和当前主线的直接关系在于：这是一篇东亚中纬边界区受极区过程直接控制的高质量个例，可用于后续热层风异常事件筛选和机制对照。"
    if "热层/密度" in tags:
        return "它和当前主线的直接关系在于：可作为热层密度异常识别与驱动归因的参考个例。"
    return "它与当前主线是间接相关的，可作为相关机制背景和个例对照。"


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


def _validate_deep_read_markdown(markdown: str, *, project: Path | None = None, note_path: Path | None = None) -> list[str]:
    issues: list[str] = []
    lines = markdown.splitlines()
    if lines and lines[0].startswith("文件名："):
        issues.append("正文顶部不应包含文件名行")
    for heading in REQUIRED_DEEP_READ_HEADINGS:
        if heading not in markdown:
            issues.append(f"缺少模板要求的区块：{heading}")
    for pattern, message in LEGACY_DEEP_READ_PATTERNS:
        if re.search(pattern, markdown, flags=re.MULTILINE):
            issues.append(message)
    if re.search(r"### 一句话总述\s*\n[^\n]*不是[^\n]*而是", markdown):
        issues.append("一句话总述仍包含“不是……而是……”式开头")
    if re.search(r"### 为什么做\s*\n[^\n]*不是[^\n]*而是", markdown):
        issues.append("“为什么做”仍包含“不是……而是……”式表述")
    if note_path is not None and project is not None and not _is_note_under_output_root(project, note_path):
        if re.search(r"\[\[log/real_case_eval/.*\|(PDF|单篇总结)\]\]", markdown):
            issues.append("评测输出仍使用了生产态 Obsidian 链接")
    return issues


def _run_deep_read_review_loop(
    project: Path,
    markdown: str,
    *,
    note_path: Path,
    tags: list[str],
) -> tuple[str, list[str]]:
    reviewed = markdown
    for _ in range(DEEP_READ_REVIEW_MAX_PASSES):
        fixed = _autofix_deep_read_markdown(project, reviewed, note_path=note_path, tags=tags)
        issues = _audit_deep_read_markdown(fixed, tags=tags)
        if not issues:
            return fixed, []
        if fixed == reviewed:
            return fixed, issues
        reviewed = fixed
    return reviewed, _audit_deep_read_markdown(reviewed, tags=tags)


def _autofix_deep_read_markdown(
    project: Path,
    markdown: str,
    *,
    note_path: Path,
    tags: list[str],
) -> str:
    fixed = markdown
    fixed = _rewrite_section_body(fixed, "### 一句话总述", _normalize_one_sentence_overview)
    fixed = _rewrite_section_body(fixed, "### 为什么做", lambda body: _normalize_goal_text(body, tags=tags))
    fixed = _rewrite_section_body(fixed, "### 如何做", _normalize_structured_deep_read_text)
    fixed = _rewrite_section_body(
        fixed,
        "### 关键结果",
        _normalize_key_results_text,
        next_heading="### 新意与贡献",
    )
    fixed = _rewrite_section_body(fixed, "### 新意与贡献", _normalize_contribution_text)
    fixed = _rewrite_section_body(fixed, "### 局限性", _normalize_structured_deep_read_text)
    fixed = _rewrite_section_body(fixed, "### 可复现性", _normalize_structured_deep_read_text)
    fixed = _rewrite_section_body(fixed, "### 与已有工作的关系", _normalize_structured_deep_read_text)
    fixed = _rewrite_section_body(fixed, "### 最终结论", _normalize_structured_deep_read_text)
    fixed = _rewrite_bullet_value(
        fixed,
        "- 和我已有工作的关系：",
        lambda body: _normalize_relation_to_my_work_text(body, tags=tags),
    )
    fixed = _rewrite_bullet_value(fixed, "- 后续值得追踪的问题：", _normalize_structured_deep_read_text)
    fixed = _rewrite_bullet_value(fixed, "- 需要人工复核的点：", _normalize_structured_deep_read_text)
    fixed = _rewrite_bullet_value(fixed, "- Obsidian 索引挂接：", lambda body: body.strip())
    return fixed.strip() + "\n"


def _audit_deep_read_markdown(markdown: str, *, tags: list[str]) -> list[str]:
    issues: list[str] = []
    why = _extract_section_body(markdown, "### 为什么做")
    if why:
        if "不是" in why and "而是" in why:
            issues.append("“为什么做”仍包含“不是……而是……”式表述")
        if re.search(r"[。；：](?=\d+[.．、)])", why):
            issues.append("“为什么做”中的编号列表未换行")
        if not why.startswith("作者要解决的问题是："):
            issues.append("“为什么做”没有用直接问题陈述开头")
    key_results = _extract_section_body(markdown, "### 关键结果", next_heading="### 新意与贡献")
    if key_results and re.search(r"(?m)^###\s+(硬结论|次级结论|合理推论|需进一步研究讨论的结论)\s*$", key_results):
        issues.append("“关键结果”中的次级标题层级仍然过高")
    return issues


def _extract_section_body(markdown: str, heading: str, *, next_heading: str | None = None) -> str:
    if next_heading:
        pattern = re.compile(rf"(?ms)^{re.escape(heading)}\n(.*?)(?=^{re.escape(next_heading)}\n|^----\s*$|\Z)")
    else:
        pattern = re.compile(rf"(?ms)^{re.escape(heading)}\n(.*?)(?=^###\s|^##\s|^----\s*$|\Z)")
    match = pattern.search(markdown)
    if not match:
        return ""
    return match.group(1).strip()


def _rewrite_section_body(markdown: str, heading: str, transform, *, next_heading: str | None = None) -> str:
    if next_heading:
        pattern = re.compile(rf"(?ms)^({re.escape(heading)}\n)(.*?)(?=^{re.escape(next_heading)}\n|^----\s*$|\Z)")
    else:
        pattern = re.compile(rf"(?ms)^({re.escape(heading)}\n)(.*?)(?=^###\s|^##\s|^----\s*$|\Z)")
    match = pattern.search(markdown)
    if not match:
        return markdown
    replacement = match.group(1) + transform(match.group(2).strip()).strip() + "\n\n"
    return markdown[: match.start()] + replacement + markdown[match.end() :]


def _rewrite_bullet_value(markdown: str, bullet_heading: str, transform) -> str:
    pattern = re.compile(rf"(?ms)^({re.escape(bullet_heading)}\n)(.*?)(?=^- [^\n]+：\n|^----\s*$|\Z)")
    match = pattern.search(markdown)
    if not match:
        return markdown
    replacement = match.group(1) + transform(match.group(2).strip()).strip() + "\n\n"
    return markdown[: match.start()] + replacement + markdown[match.end() :]


def _load_deep_read_template(template_path: Path) -> str:
    template_text = template_path.read_text(encoding="utf-8")
    _validate_deep_read_template(template_text, template_path)
    return template_text


def _validate_deep_read_template(template_text: str, template_path: Path) -> None:
    missing_markers = [marker for marker in REQUIRED_DEEP_READ_HEADINGS if marker not in template_text]
    if "记录时间戳:" not in template_text:
        missing_markers.append("记录时间戳:")
    if missing_markers:
        joined = "、".join(missing_markers)
        raise ValueError(f"Deep read template missing required markers in {template_path}: {joined}")

    found_vars = set(DEEP_READ_TEMPLATE_VAR_RE.findall(template_text))
    missing_vars = sorted(DEEP_READ_TEMPLATE_REQUIRED_VARS - found_vars)
    if missing_vars:
        joined = ", ".join(missing_vars)
        raise ValueError(f"Deep read template missing required placeholders in {template_path}: {joined}")


def _render_deep_read_template(template_text: str, context: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise ValueError(f"Deep read template placeholder has no context value: {key}")
        return str(context[key])

    rendered = DEEP_READ_TEMPLATE_VAR_RE.sub(replace, template_text)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered
