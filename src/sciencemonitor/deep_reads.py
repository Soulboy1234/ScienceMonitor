from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from .article_summaries import (
    abbreviate_journal_name,
    build_doi_url,
    extract_related_report_links,
    first_author_label,
    format_authors_apa,
    normalize_doi,
    obsidian_link,
    parse_authors,
    sanitize_filename,
)
from .article_index import sync_out_library
from .config import (
    article_summaries_root,
    deep_reads_pdf_root,
    deep_reads_root,
    load_runtime_config,
    project_root,
    templates_root,
)
from .crossref import CrossrefClient
from .html_extract import extract_full_text_from_html, extract_page_metadata, extract_pdf_urls
from .http import HTTPClient
from .llm import AnalysisEngine, DeepReadAnalysis
from .storage import Storage
from .utils import clean_abstract_text, clean_title_text


REQUIRED_DEEP_READ_HEADINGS = [
    "# 论文深度阅读报告",
    "## 论文信息",
    "### 一句话总述",
    "## 论文详解",
    "### 1. 为什么做这项研究",
    "### 2. 作者是怎么推进这个问题的",
    "### 3. 文章最关键的结果是什么",
    "### 4. 这篇文章的新意以及对科学研究的贡献",
    "### 5. 文章的局限性",
    "### 6. 文章的可复现性",
    "### 7. 与已有工作的关系",
    "## 总结",
    "### 最终结论",
    "### 补充信息与挂接",
]

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
) -> DeepReadResult:
    project = root or project_root()
    runtime = load_runtime_config(project)
    if not runtime.get("features", {}).get("weekly_report_enabled", True):
        # no-op; weekly report toggle should not block deep reads
        pass

    analysis_engine = AnalysisEngine(project)
    if not analysis_engine.deep_read_enabled():
        return DeepReadResult(False, "深度解读功能当前已关闭。请在配置界面或 PROJECT_CONFIG.md 中开启后再运行。")
    if analysis_engine.provider == "rules":
        return DeepReadResult(False, "当前 provider=rules，不支持 LLM 深度解读。请切换到 codex_local 或 openai_api。")

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

    related_summary = _find_related_summary(project, metadata.get("doi", ""))
    related_summary_payload = _summary_payload(related_summary) if related_summary else None
    analysis = analysis_engine.analyze_deep_read(metadata, resolution.full_text, related_summary_payload)
    if analysis is None:
        return DeepReadResult(False, "深度解读分析未生成结果。请检查当前 provider、额度或输入文本长度。", source_kind=resolution.source_kind)
    analysis = _normalize_deep_read_analysis(analysis)

    output_dir = deep_reads_root(project)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = deep_reads_pdf_root(project)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    linked_pdf_path = None
    if resolution.pdf_path and resolution.pdf_path.exists():
        target_pdf_name = sanitize_filename(resolution.pdf_path.name)
        linked_pdf_path = pdf_dir / target_pdf_name
        if resolution.pdf_path.resolve() != linked_pdf_path.resolve():
            shutil.copy2(resolution.pdf_path, linked_pdf_path)
        else:
            linked_pdf_path = resolution.pdf_path

    note_path = _build_deep_read_output_path(project, output_dir, metadata, analysis, related_summary)
    markdown = _render_deep_read_markdown(
        project=project,
        metadata=metadata,
        analysis=analysis,
        related_summary=related_summary,
        pdf_path=linked_pdf_path,
        source_kind=resolution.source_kind,
        source_url=resolution.source_url,
    )
    validation_issues = _validate_deep_read_markdown(markdown)
    if validation_issues:
        return DeepReadResult(
            False,
            "深度解读生成结果未通过模板校验：" + "；".join(validation_issues),
            source_kind=resolution.source_kind,
        )
    note_path.write_text(markdown, encoding="utf-8")
    sync_out_library(project)
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
) -> dict[str, str]:
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


def _search_crossref_by_title(title: str) -> dict[str, str] | None:
    client = CrossrefClient(HTTPClient())
    payload = client.http.get_json(
        client.API_URL,
        params={
            "rows": "5",
            "query.title": title,
            "select": "DOI,URL,title,container-title,author,published-online,published-print,published,issued",
        },
    )
    items = payload.get("message", {}).get("items", [])
    if not items:
        return None
    best = items[0]
    best_title = clean_title_text((best.get("title") or [""])[0] if best.get("title") else "")
    if not best_title:
        return None
    authors = []
    for item in best.get("author") or []:
        given = (item.get("given") or "").strip()
        family = (item.get("family") or "").strip()
        full = " ".join(part for part in [given, family] if part)
        if full:
            authors.append(full)
    published = ""
    for field in ("published-online", "published-print", "published", "issued"):
        parts = ((best.get(field) or {}).get("date-parts") or [])
        if parts and parts[0]:
            current = parts[0]
            year = current[0]
            month = current[1] if len(current) > 1 else 1
            day = current[2] if len(current) > 2 else 1
            published = f"{year:04d}-{month:02d}-{day:02d}"
            break
    return {
        "doi": str(best.get("DOI", "") or ""),
        "title": best_title,
        "journal": str((best.get("container-title") or [""])[0] if best.get("container-title") else ""),
        "url": str(best.get("URL", "") or ""),
        "authors": "\n".join(authors),
        "published_date": published,
        "raw_authors": "\n".join(authors),
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
            return FullTextResolution(True, "provided_pdf", full_text=extracted, pdf_path=explicit_pdf, source_url=str(explicit_pdf))
        return FullTextResolution(False, "provided_pdf", message="提供的 PDF 未能提取出足够文本，请确认 PDF 可读。")

    if not runtime.get("deep_read", {}).get("search_full_text_when_pdf_missing", True):
        return FullTextResolution(False, "missing_pdf", message="当前配置禁止在缺少 PDF 时自动搜索全文。请提供文章 PDF。")

    http = HTTPClient(timeout=20)
    candidate_urls = []
    doi_url = build_doi_url(metadata.get("doi", ""), metadata.get("url", ""))
    if doi_url:
        candidate_urls.append(doi_url)
    if metadata.get("url") and metadata["url"] not in candidate_urls:
        candidate_urls.append(metadata["url"])

    for candidate in candidate_urls:
        try:
            html_text = http.get_text(candidate)
        except Exception:
            continue
        page_title, _ = extract_page_metadata(html_text)
        pdf_urls = extract_pdf_urls(html_text, candidate)
        for pdf_url in pdf_urls:
            downloaded = _download_pdf(http, pdf_url, project)
            if downloaded is None:
                continue
            extracted = _extract_pdf_text(project, downloaded, runtime)
            if extracted:
                return FullTextResolution(True, "downloaded_pdf", full_text=extracted, pdf_path=downloaded, source_url=pdf_url)
        full_text, is_full_text = extract_full_text_from_html(html_text)
        if is_full_text:
            return FullTextResolution(True, "html_full_text", full_text=full_text, pdf_path=None, source_url=candidate)
        if page_title and metadata.get("title") and metadata["title"].lower() in page_title.lower():
            continue

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
        filename = f"{first_author} ({year}) - {journal} - {chinese}深度解读.md"
    return output_dir / filename


def _render_deep_read_markdown(
    project: Path,
    metadata: dict[str, str],
    analysis: DeepReadAnalysis,
    related_summary: Path | None,
    pdf_path: Path | None,
    source_kind: str,
    source_url: str,
) -> str:
    report_links = extract_related_report_links(related_summary.read_text(encoding="utf-8")) if related_summary and related_summary.exists() else []
    links = []
    if pdf_path:
        links.append(obsidian_link(pdf_path, "PDF", root=project))
    else:
        doi_url = build_doi_url(metadata.get("doi", ""), source_url or metadata.get("url", ""))
        if doi_url:
            links.append(f"[DOI]({doi_url})")
    if related_summary:
        links.append(obsidian_link(related_summary, "单篇总结", root=project))
    if report_links:
        links.extend(report_links[:1])
    tag_text = " ".join("#" + tag.replace(" ", "") for tag in analysis.tags)
    authors = parse_authors(metadata.get("raw_authors", "") or metadata.get("authors", ""))
    authors_text = format_authors_apa(authors) if authors else "Unknown"
    year = (metadata.get("published_date", "") or "Unknown")[:4]
    doi_url = build_doi_url(metadata.get("doi", ""), source_url or metadata.get("url", ""))
    apa = f"{authors_text} ({year}). {clean_title_text(metadata.get('title', ''))}. {metadata.get('journal', '')}. {doi_url}".strip()
    return "\n".join(
        [
            "# 论文深度阅读报告",
            "----",
            f"- {' '.join(links)} {tag_text}".rstrip(),
            f"- _{apa}_",
            "",
            "## 论文信息",
            f"- **题目**：{clean_title_text(metadata.get('title', ''))}",
            f"- **作者**：{metadata.get('authors', '').replace(chr(10), ', ')}",
            f"- **期刊**：{metadata.get('journal', '')}",
            f"- **年份**：{year}",
            f"- **论文类型**：{analysis.paper_type or '研究论文'}",
            "",
            "### 一句话总述",
            analysis.one_sentence_overview,
            "",
            "## 论文详解",
            "### 1. 为什么做这项研究",
            analysis.why,
            "",
            "### 2. 作者是怎么推进这个问题的",
            analysis.how,
            "",
            "### 3. 文章最关键的结果是什么",
            analysis.key_results,
            "",
            "### 4. 这篇文章的新意以及对科学研究的贡献",
            analysis.contribution,
            "",
            "### 5. 文章的局限性",
            analysis.limitations,
            "",
            "### 6. 文章的可复现性",
            analysis.reproducibility,
            "",
            "### 7. 与已有工作的关系",
            analysis.relation,
            "",
            "## 总结",
            "### 最终结论",
            analysis.final_conclusion,
            "",
            "### 补充信息与挂接",
            f"- 和我已有工作的关系：{analysis.relation_to_my_work}",
            f"- 后续值得追踪的问题：{analysis.follow_up_questions}",
            f"- 需要人工复核的点：{analysis.needs_manual_review}",
            f"- 已挂接的目录：{analysis.knowledge_position}",
            "",
            "----",
            f"记录时间戳: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]
    )


def _normalize_deep_read_analysis(analysis: DeepReadAnalysis) -> DeepReadAnalysis:
    return replace(
        analysis,
        chinese_title=clean_title_text(analysis.chinese_title),
        paper_type=_normalize_deep_read_text(analysis.paper_type),
        one_sentence_overview=_normalize_one_sentence_overview(analysis.one_sentence_overview),
        why=_normalize_deep_read_text(analysis.why),
        how=_normalize_deep_read_text(analysis.how),
        key_results=_normalize_deep_read_text(analysis.key_results),
        contribution=_normalize_deep_read_text(analysis.contribution),
        limitations=_normalize_deep_read_text(analysis.limitations),
        reproducibility=_normalize_deep_read_text(analysis.reproducibility),
        relation=_normalize_deep_read_text(analysis.relation),
        final_conclusion=_normalize_deep_read_text(analysis.final_conclusion),
        relation_to_my_work=_normalize_deep_read_text(analysis.relation_to_my_work),
        follow_up_questions=_normalize_deep_read_text(analysis.follow_up_questions),
        needs_manual_review=_normalize_deep_read_text(analysis.needs_manual_review),
        knowledge_position=_normalize_deep_read_text(analysis.knowledge_position),
    )


def _normalize_deep_read_text(value: str) -> str:
    text = (value or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    for pattern, replacement in DEEP_READ_TEXT_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.replace("消融 实验", "消融实验")
    text = text.replace("这个文章", "这篇文章")
    text = text.replace("This paper", "这篇文章")
    text = text.replace("This study", "这项研究")
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


def _validate_deep_read_markdown(markdown: str) -> list[str]:
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
    return issues
