from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, quote_plus, urlparse

from .article_source_text import (
    build_summary_packet_from_scientific_text,
    compact_scientific_text_for_summary,
    prepare_scientific_source_text,
)
from .config import data_root
from .crossref import CrossrefClient
from .html_extract import extract_full_text_from_html, extract_page_metadata, extract_pdf_urls, extract_redirect_urls
from .http import HTTPClient
from .utils import clean_abstract_text, clean_title_text


INVALID_PAGE_TITLES = {
    "redirecting",
    "redirect",
    "loading",
    "just a moment",
    "access denied",
    "please wait",
}
PDF_TEXT_EXTRACTOR_VERSION = "pdf_text_v2"


@dataclass(frozen=True)
class ArticlePageSnapshot:
    source_url: str = ""
    page_title: str = ""
    abstract: str = ""
    full_text: str = ""
    is_full_text: bool = False
    pdf_urls: list[str] = field(default_factory=list)
    redirect_urls: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SummarySourceMaterial:
    doi: str = ""
    title: str = ""
    journal: str = ""
    url: str = ""
    authors: list[str] = field(default_factory=list)
    published_date: str = ""
    abstract: str = ""
    summary_text: str = ""
    source_kind: str = "missing"
    abstract_only: bool = False
    pdf_urls: list[str] = field(default_factory=list)
    scientific_text: str = ""
    cache_path: str = ""
    diagnostics: list[str] = field(default_factory=list)
    manual_search_urls: list[str] = field(default_factory=list)
    error: str = ""


def build_candidate_article_urls(doi: str = "", url: str = "", extra_urls: list[str] | None = None) -> list[str]:
    values: list[str] = []
    if extra_urls:
        values.extend(extra_urls)
    if url:
        values.append(url.strip())
    doi_url = build_doi_lookup_url(doi)
    if doi_url:
        values.append(doi_url)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        clean = item.strip()
        if not clean or clean in seen:
            continue
        deduped.append(clean)
        seen.add(clean)
    return deduped


def build_doi_lookup_url(doi: str) -> str:
    clean = clean_abstract_text(doi).strip()
    if not clean:
        return ""
    if clean.lower().startswith("10.1029/"):
        clean = clean.upper()
    return f"https://doi.org/{clean}"


def fetch_article_page_snapshot(http: HTTPClient, candidate_urls: list[str]) -> ArticlePageSnapshot:
    best = ArticlePageSnapshot()
    pending = list(candidate_urls)
    seen: set[str] = set()
    diagnostics: list[str] = []
    for candidate in pending:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            html = http.get_text(candidate)
        except HTTPError as exc:
            diagnostics.append(f"{_diagnostic_host(candidate)}: HTTP {exc.code}")
            continue
        except Exception as exc:
            diagnostics.append(f"{_diagnostic_host(candidate)}: {type(exc).__name__}")
            continue

        page_title, abstract = extract_page_metadata(html)
        pdf_urls = extract_pdf_urls(html, candidate)
        redirect_urls = extract_redirect_urls(html, candidate)
        for redirect_url in redirect_urls:
            if redirect_url not in seen and redirect_url not in pending:
                pending.append(redirect_url)
        full_text, is_full_text = extract_full_text_from_html(html)
        current = ArticlePageSnapshot(
            source_url=candidate,
            page_title=page_title,
            abstract=abstract,
            full_text=full_text if is_full_text else "",
            is_full_text=is_full_text,
            pdf_urls=pdf_urls,
            redirect_urls=redirect_urls,
            diagnostics=list(diagnostics),
        )
        if current.is_full_text:
            return current
        if _page_snapshot_score(current) > _page_snapshot_score(best):
            best = current
    if diagnostics and not best.diagnostics:
        best = ArticlePageSnapshot(
            source_url=best.source_url,
            page_title=best.page_title,
            abstract=best.abstract,
            full_text=best.full_text,
            is_full_text=best.is_full_text,
            pdf_urls=best.pdf_urls,
            redirect_urls=best.redirect_urls,
            diagnostics=diagnostics,
        )
    return best


def resolve_summary_source_material(
    *,
    doi: str,
    url: str,
    title: str,
    journal: str,
    abstract: str,
    authors: list[str] | None,
    published_date: str,
    http: HTTPClient,
    crossref: CrossrefClient,
    local_pdf_path: Path | None = None,
    project_root: Path | None = None,
    local_pdf_page_limit: int = 6,
) -> SummarySourceMaterial:
    diagnostics: list[str] = []
    crossref_meta = crossref.lookup_work_by_doi(doi) if doi.strip() else None
    if crossref_meta is None and title.strip():
        crossref_meta = crossref.lookup_work_by_title(title)

    local_pdf_full_text, local_pdf_summary = _extract_local_pdf_text(
        local_pdf_path,
        project_root=project_root,
        page_limit=local_pdf_page_limit,
    )
    if local_pdf_full_text:
        page_snapshot = ArticlePageSnapshot()
    else:
        page_snapshot = fetch_article_page_snapshot(
            http,
            build_candidate_article_urls(
                doi,
                url,
                extra_urls=[str((crossref_meta or {}).get("url", "") or "")],
            ),
        )

    clean_stored_abstract = clean_abstract_text(abstract)
    crossref_abstract = clean_abstract_text(str((crossref_meta or {}).get("abstract", "") or ""))
    best_abstract = _prefer_longer(page_snapshot.abstract, clean_stored_abstract, crossref_abstract)
    diagnostics.extend(page_snapshot.diagnostics)
    if crossref_meta is None:
        diagnostics.append("Crossref: not found")
    elif crossref_abstract:
        diagnostics.append("Crossref: abstract")
    else:
        diagnostics.append("Crossref: no abstract")
    if page_snapshot.redirect_urls:
        diagnostics.append("Publisher redirect: " + ", ".join(page_snapshot.redirect_urls[:2]))
    external_material = None
    if not best_abstract and doi.strip():
        external_material = resolve_external_abstract_material(
            doi=doi,
            title=title,
            http=http,
        )
        diagnostics.extend(external_material.diagnostics)
        if external_material.abstract:
            best_abstract = external_material.abstract
    scientific_text = ""
    cache_path = ""
    if local_pdf_full_text:
        source_kind = "local_pdf_full_text"
        summary_text = build_summary_packet_from_scientific_text(local_pdf_full_text, abstract_override=best_abstract) or local_pdf_summary
        scientific_text = local_pdf_full_text
        abstract_only = False
    elif page_snapshot.is_full_text:
        source_kind = "html_full_text"
        scientific_text = prepare_scientific_source_text(page_snapshot.full_text)
        summary_text = build_summary_packet_from_scientific_text(scientific_text, abstract_override=best_abstract)
        abstract_only = False
    elif page_snapshot.abstract:
        source_kind = "page_abstract"
        summary_text = best_abstract
        abstract_only = True
    elif crossref_abstract:
        source_kind = "crossref_abstract"
        summary_text = best_abstract
        abstract_only = True
    elif clean_stored_abstract:
        source_kind = "stored_abstract"
        summary_text = clean_stored_abstract
        abstract_only = True
    elif external_material and external_material.abstract:
        source_kind = external_material.source_kind
        summary_text = external_material.abstract
        abstract_only = True
    else:
        source_kind = "publisher_redirect_only" if page_snapshot.redirect_urls else "missing"
        summary_text = ""
        abstract_only = False

    resolved_title = _prefer_title(
        page_snapshot.page_title,
        str((crossref_meta or {}).get("title", "") or ""),
        title,
    )
    resolved_journal = clean_title_text(
        str((crossref_meta or {}).get("journal", "") or "") or journal
    )
    resolved_url = (
        page_snapshot.source_url
        or (external_material.source_url if external_material else "")
        or str((crossref_meta or {}).get("url", "") or "")
        or url.strip()
        or build_doi_lookup_url(doi)
    )
    resolved_authors = list(authors or []) or list((crossref_meta or {}).get("authors", []) or [])
    resolved_published = str((crossref_meta or {}).get("published_date", "") or published_date or "")
    resolved_pdf_urls = list((crossref_meta or {}).get("pdf_urls", []) or [])
    for item in page_snapshot.pdf_urls:
        if item not in resolved_pdf_urls:
            resolved_pdf_urls.append(item)
    if external_material:
        for item in external_material.pdf_urls:
            if item not in resolved_pdf_urls:
                resolved_pdf_urls.append(item)
    manual_search_urls = build_manual_search_urls(
        doi=str((crossref_meta or {}).get("doi", "") or doi).strip(),
        title=resolved_title or title,
        url=resolved_url,
        extra_urls=page_snapshot.redirect_urls,
    )
    if project_root is not None and scientific_text:
        cache_path = write_article_source_cache(
            project_root,
            doi=str((crossref_meta or {}).get("doi", "") or doi).strip(),
            title=resolved_title,
            journal=resolved_journal,
            source_kind=source_kind,
            source_url=resolved_url,
            pdf_path=str(local_pdf_path or ""),
            scientific_text=scientific_text,
            summary_packet=summary_text,
            pdf_page_limit=local_pdf_page_limit if source_kind == "local_pdf_full_text" else None,
        )

    return SummarySourceMaterial(
        doi=str((crossref_meta or {}).get("doi", "") or doi).strip(),
        title=resolved_title,
        journal=resolved_journal,
        url=resolved_url,
        authors=resolved_authors,
        published_date=resolved_published,
        abstract=best_abstract,
        summary_text=summary_text,
        source_kind=source_kind,
        abstract_only=abstract_only,
        pdf_urls=resolved_pdf_urls,
        scientific_text=scientific_text,
        cache_path=cache_path,
        diagnostics=_dedupe_text_items(diagnostics),
        manual_search_urls=manual_search_urls,
    )


@dataclass(frozen=True)
class ExternalAbstractMaterial:
    abstract: str = ""
    source_kind: str = ""
    source_url: str = ""
    pdf_urls: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


def resolve_external_abstract_material(*, doi: str, title: str, http: HTTPClient) -> ExternalAbstractMaterial:
    diagnostics: list[str] = []
    openalex = _lookup_openalex_abstract(doi, http=http)
    diagnostics.extend(openalex.diagnostics)
    if openalex.abstract:
        return openalex

    semantic = _lookup_semantic_scholar_abstract(doi, http=http)
    diagnostics.extend(semantic.diagnostics)
    if semantic.abstract:
        return ExternalAbstractMaterial(
            abstract=semantic.abstract,
            source_kind=semantic.source_kind,
            source_url=semantic.source_url,
            pdf_urls=semantic.pdf_urls,
            diagnostics=_dedupe_text_items(diagnostics),
        )

    arxiv_ids = _arxiv_ids_from_urls(openalex.pdf_urls + ([openalex.source_url] if openalex.source_url else []))
    arxiv = _lookup_arxiv_abstract(arxiv_ids=arxiv_ids, title=title, http=http)
    diagnostics.extend(arxiv.diagnostics)
    if arxiv.abstract:
        return ExternalAbstractMaterial(
            abstract=arxiv.abstract,
            source_kind=arxiv.source_kind,
            source_url=arxiv.source_url,
            pdf_urls=arxiv.pdf_urls,
            diagnostics=_dedupe_text_items(diagnostics),
        )
    return ExternalAbstractMaterial(diagnostics=_dedupe_text_items(diagnostics))


def _lookup_openalex_abstract(doi: str, *, http: HTTPClient) -> ExternalAbstractMaterial:
    clean_doi = clean_abstract_text(doi).strip()
    if not clean_doi:
        return ExternalAbstractMaterial(diagnostics=["OpenAlex: no doi"])
    url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"
    try:
        payload = json.loads(http.get_text(url, headers={"Accept": "application/json"}))
    except HTTPError as exc:
        return ExternalAbstractMaterial(diagnostics=[f"OpenAlex: HTTP {exc.code}"])
    except Exception as exc:
        return ExternalAbstractMaterial(diagnostics=[f"OpenAlex: {type(exc).__name__}"])
    abstract = _openalex_abstract_from_inverted_index(payload.get("abstract_inverted_index"))
    open_access = payload.get("open_access") if isinstance(payload.get("open_access"), dict) else {}
    primary = payload.get("primary_location") if isinstance(payload.get("primary_location"), dict) else {}
    oa_url = str(open_access.get("oa_url", "") or "").strip()
    source_url = oa_url or str(primary.get("landing_page_url", "") or payload.get("doi", "") or "").strip()
    pdf_urls = [item for item in [oa_url] if item]
    if abstract:
        return ExternalAbstractMaterial(
            abstract=abstract,
            source_kind="openalex_abstract",
            source_url=source_url,
            pdf_urls=pdf_urls,
            diagnostics=["OpenAlex: abstract"],
        )
    return ExternalAbstractMaterial(
        source_url=source_url,
        pdf_urls=pdf_urls,
        diagnostics=["OpenAlex: no abstract"],
    )


def _lookup_semantic_scholar_abstract(doi: str, *, http: HTTPClient) -> ExternalAbstractMaterial:
    clean_doi = clean_abstract_text(doi).strip()
    if not clean_doi:
        return ExternalAbstractMaterial(diagnostics=["Semantic Scholar: no doi"])
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/"
        f"DOI:{quote(clean_doi, safe='')}?fields=title,abstract,url,openAccessPdf"
    )
    try:
        payload = json.loads(http.get_text(url, headers={"Accept": "application/json"}))
    except HTTPError as exc:
        return ExternalAbstractMaterial(diagnostics=[f"Semantic Scholar: HTTP {exc.code}"])
    except Exception as exc:
        return ExternalAbstractMaterial(diagnostics=[f"Semantic Scholar: {type(exc).__name__}"])
    abstract = clean_abstract_text(str(payload.get("abstract", "") or ""))
    open_pdf = payload.get("openAccessPdf") if isinstance(payload.get("openAccessPdf"), dict) else {}
    pdf_url = str(open_pdf.get("url", "") or "").strip()
    source_url = str(payload.get("url", "") or pdf_url or "").strip()
    if abstract:
        return ExternalAbstractMaterial(
            abstract=abstract,
            source_kind="semantic_scholar_abstract",
            source_url=source_url,
            pdf_urls=[pdf_url] if pdf_url else [],
            diagnostics=["Semantic Scholar: abstract"],
        )
    return ExternalAbstractMaterial(
        source_url=source_url,
        pdf_urls=[pdf_url] if pdf_url else [],
        diagnostics=["Semantic Scholar: no abstract"],
    )


def _lookup_arxiv_abstract(*, arxiv_ids: list[str], title: str, http: HTTPClient) -> ExternalAbstractMaterial:
    ids = _dedupe_text_items(arxiv_ids)
    urls: list[str] = []
    if ids:
        urls.append("https://export.arxiv.org/api/query?id_list=" + ",".join(quote(item, safe="") for item in ids))
    clean_title = clean_title_text(title)
    if clean_title:
        urls.append("https://export.arxiv.org/api/query?search_query=ti:" + quote_plus(f'"{clean_title}"') + "&start=0&max_results=3")
    if not urls:
        return ExternalAbstractMaterial(diagnostics=["arXiv: no query"])
    diagnostics: list[str] = []
    for url in urls:
        try:
            xml_text = http.get_text(url, headers={"Accept": "application/atom+xml"})
        except HTTPError as exc:
            diagnostics.append(f"arXiv: HTTP {exc.code}")
            continue
        except Exception as exc:
            diagnostics.append(f"arXiv: {type(exc).__name__}")
            continue
        abstract, source_url, pdf_url = _parse_arxiv_atom_abstract(xml_text, expected_title=clean_title)
        if abstract:
            return ExternalAbstractMaterial(
                abstract=abstract,
                source_kind="arxiv_abstract",
                source_url=source_url,
                pdf_urls=[pdf_url] if pdf_url else [],
                diagnostics=_dedupe_text_items(diagnostics + ["arXiv: abstract"]),
            )
        diagnostics.append("arXiv: not found")
    return ExternalAbstractMaterial(diagnostics=_dedupe_text_items(diagnostics))


def _openalex_abstract_from_inverted_index(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    positioned: list[tuple[int, str]] = []
    for word, raw_positions in value.items():
        if not isinstance(raw_positions, list):
            continue
        for raw_position in raw_positions:
            try:
                positioned.append((int(raw_position), str(word)))
            except Exception:
                continue
    if not positioned:
        return ""
    return clean_abstract_text(" ".join(word for _, word in sorted(positioned)))


def _arxiv_ids_from_urls(urls: list[str]) -> list[str]:
    ids: list[str] = []
    for raw_url in urls:
        parsed = urlparse(str(raw_url or "").strip())
        if "arxiv.org" not in parsed.netloc.lower():
            continue
        match = re.search(r"/(?:abs|pdf)/([^/?#]+)", parsed.path)
        if not match:
            continue
        arxiv_id = match.group(1).removesuffix(".pdf").strip()
        if arxiv_id:
            ids.append(arxiv_id)
    return _dedupe_text_items(ids)


def _parse_arxiv_atom_abstract(xml_text: str, *, expected_title: str = "") -> tuple[str, str, str]:
    entries = re.findall(r"(?is)<entry>(.*?)</entry>", str(xml_text or ""))
    expected = re.sub(r"\s+", " ", expected_title or "").strip().lower()
    for entry in entries:
        title = clean_title_text(_strip_xml_tags(_first_xml_block(entry, "title")))
        if expected and title and expected not in title.lower() and title.lower() not in expected:
            continue
        summary = clean_abstract_text(_strip_xml_tags(_first_xml_block(entry, "summary")))
        if not summary:
            continue
        source_url = _strip_xml_tags(_first_xml_block(entry, "id"))
        pdf_url = ""
        pdf_match = re.search(r'(?is)<link[^>]+title=["\']pdf["\'][^>]+href=["\']([^"\']+)["\']', entry)
        if pdf_match:
            pdf_url = pdf_match.group(1).strip()
        return summary, source_url, pdf_url
    return "", "", ""


def _first_xml_block(xml_text: str, tag: str) -> str:
    match = re.search(rf"(?is)<{re.escape(tag)}[^>]*>(.*?)</{re.escape(tag)}>", xml_text)
    return match.group(1) if match else ""


def _strip_xml_tags(value: str) -> str:
    return unescape(re.sub(r"(?is)<[^>]+>", " ", value or ""))


def build_manual_search_urls(*, doi: str = "", title: str = "", url: str = "", extra_urls: list[str] | None = None) -> list[str]:
    urls: list[str] = []
    clean_doi = clean_abstract_text(doi).strip()
    clean_title = clean_title_text(title)
    if clean_doi:
        urls.append(build_doi_lookup_url(clean_doi))
    if url:
        urls.append(url.strip())
    for item in extra_urls or []:
        if item:
            urls.append(str(item).strip())
    query = clean_title or clean_doi
    if query:
        urls.append("https://scholar.google.com/scholar?q=" + quote_plus(query))
        urls.append("https://www.google.com/search?q=" + quote_plus(query + " abstract"))
        urls.append("https://www.researchgate.net/search/publication?q=" + quote_plus(query))
    return _dedupe_text_items(urls)


def _extract_local_pdf_text(
    pdf_path: Path | None,
    *,
    project_root: Path | None = None,
    page_limit: int = 6,
) -> tuple[str, str]:
    if pdf_path is None or not pdf_path.exists():
        return "", ""
    pdftotext_bin = shutil.which("pdftotext")
    if not pdftotext_bin and project_root is not None:
        candidate = project_root / ".venv" / "bin" / "pdftotext"
        if candidate.exists():
            pdftotext_bin = str(candidate)
    if not pdftotext_bin:
        return "", ""

    candidates: list[tuple[str, str]] = []
    layout_raw = _run_pdftotext(pdftotext_bin, pdf_path, page_limit=page_limit, layout=True)
    if layout_raw:
        candidates.append(("layout_filtered", prepare_scientific_source_text(layout_raw, assume_pdf_layout=True)))
        candidates.append(("layout_wide", prepare_scientific_source_text(layout_raw, assume_pdf_layout=False)))
    plain_raw = _run_pdftotext(pdftotext_bin, pdf_path, page_limit=page_limit, layout=False)
    if plain_raw:
        candidates.append(("plain_wide", prepare_scientific_source_text(plain_raw, assume_pdf_layout=False)))
    scientific_text = _select_best_pdf_scientific_text(candidates)
    if not scientific_text:
        return "", ""
    summary_packet = build_summary_packet_from_scientific_text(scientific_text)
    return scientific_text, summary_packet


def _run_pdftotext(pdftotext_bin: str, pdf_path: Path, *, page_limit: int, layout: bool) -> str:
    try:
        command = [pdftotext_bin]
        if layout:
            command.append("-layout")
        command.extend(["-nopgbrk", "-f", "1"])
        if page_limit > 0:
            command.extend(["-l", str(page_limit)])
        command.extend([str(pdf_path), "-"])
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    return str(result.stdout or "")


def _select_best_pdf_scientific_text(candidates: list[tuple[str, str]]) -> str:
    scored = [
        (_score_pdf_scientific_text(text, source=name), name, text)
        for name, text in candidates
        if str(text or "").strip()
    ]
    if not scored:
        return ""
    scored.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
    return scored[0][2].strip()


def _score_pdf_scientific_text(text: str, *, source: str) -> int:
    clean = str(text or "").strip()
    if not clean:
        return 0
    lower = clean.lower()
    score = min(len(clean) // 1000, 140)
    score += len(re.findall(r"(?m)^\d+\.\s+[A-Z][A-Za-z0-9,()\-–/& ]{2,90}$", clean)) * 8
    score += min(lower.count("abstract"), 2) * 4
    score += min(lower.count("introduction"), 3) * 4
    score += min(sum(lower.count(item) for item in ("method", "results", "discussion", "conclusion")), 8) * 3
    score += min(sum(lower.count(item) for item in ("pinn", "xai", "case study", "validation", "reproduc")), 12) * 2
    if source == "layout_filtered":
        score += 6
    if len(clean) < 12000:
        score -= 20
    if len(clean) < 6000:
        score -= 30
    return score


def extract_pdf_scientific_text(pdf_path: Path, *, project_root: Path | None = None, page_limit: int = 6) -> str:
    scientific_text, _ = _extract_local_pdf_text(pdf_path, project_root=project_root, page_limit=page_limit)
    return scientific_text


def _compact_pdf_text_for_summary(raw_text: str, *, max_chars: int = 6000) -> str:
    return compact_scientific_text_for_summary(raw_text, max_chars=max_chars)


def _page_snapshot_score(snapshot: ArticlePageSnapshot) -> int:
    return (
        (100000 if snapshot.is_full_text else 0)
        + len(snapshot.abstract)
        + len(snapshot.pdf_urls) * 200
        + len(snapshot.page_title)
    )


def _prefer_longer(*values: str) -> str:
    best = ""
    for value in values:
        clean = clean_abstract_text(value)
        if len(clean) > len(best):
            best = clean
    return best


def _prefer_title(*values: str) -> str:
    for value in values:
        clean = clean_title_text(value)
        if clean and not _is_invalid_page_title(clean):
            return clean
    return ""


def _dedupe_text_items(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = clean_abstract_text(str(item or "")).strip()
        if not clean or clean in seen:
            continue
        deduped.append(clean)
        seen.add(clean)
    return deduped


def _diagnostic_host(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.netloc:
        return parsed.netloc
    return clean_abstract_text(url)[:80] or "source"


def _is_invalid_page_title(value: str) -> bool:
    clean = clean_title_text(value).strip().lower()
    if not clean:
        return True
    return clean in INVALID_PAGE_TITLES or clean.startswith("redirecting")


def article_source_cache_root(project_root: Path) -> Path:
    path = data_root(project_root) / "article_source_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_article_source_cache(
    project_root: Path,
    *,
    doi: str,
    title: str,
    journal: str,
    source_kind: str,
    source_url: str,
    pdf_path: str,
    scientific_text: str,
    summary_packet: str,
    pdf_page_limit: int | None = None,
) -> str:
    cache_path = article_source_cache_root(project_root) / f"{_article_source_cache_key(doi, title)}.json"
    payload = {
        "doi": doi,
        "title": title,
        "journal": journal,
        "source_kind": source_kind,
        "source_url": source_url,
        "pdf_path": pdf_path,
        "scientific_text": scientific_text,
        "summary_packet": summary_packet,
    }
    if pdf_page_limit is not None:
        payload["pdf_page_limit"] = pdf_page_limit
        payload["text_extractor_version"] = PDF_TEXT_EXTRACTOR_VERSION
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(cache_path)


def load_article_source_cache(project_root: Path, *, doi: str = "", title: str = "") -> dict | None:
    cache_path = article_source_cache_root(project_root) / f"{_article_source_cache_key(doi, title)}.json"
    if not cache_path.exists():
        return None
    return json.loads(cache_path.read_text(encoding="utf-8"))


def _article_source_cache_key(doi: str, title: str) -> str:
    identity = clean_abstract_text(doi).lower() or clean_title_text(title).lower()
    identity = f"source_v4|{identity}"
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()[:24]
