from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .article_source_text import (
    build_summary_packet_from_scientific_text,
    compact_scientific_text_for_summary,
    prepare_scientific_source_text,
)
from .config import data_root
from .crossref import CrossrefClient
from .html_extract import extract_full_text_from_html, extract_page_metadata, extract_pdf_urls
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


@dataclass(frozen=True)
class ArticlePageSnapshot:
    source_url: str = ""
    page_title: str = ""
    abstract: str = ""
    full_text: str = ""
    is_full_text: bool = False
    pdf_urls: list[str] = field(default_factory=list)


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
    for candidate in candidate_urls:
        try:
            html = http.get_text(candidate)
        except Exception:
            continue

        page_title, abstract = extract_page_metadata(html)
        pdf_urls = extract_pdf_urls(html, candidate)
        full_text, is_full_text = extract_full_text_from_html(html)
        current = ArticlePageSnapshot(
            source_url=candidate,
            page_title=page_title,
            abstract=abstract,
            full_text=full_text if is_full_text else "",
            is_full_text=is_full_text,
            pdf_urls=pdf_urls,
        )
        if current.is_full_text:
            return current
        if _page_snapshot_score(current) > _page_snapshot_score(best):
            best = current
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
    else:
        source_kind = "missing"
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
    )


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

    try:
        result = subprocess.run(
            [pdftotext_bin, "-layout", "-nopgbrk", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "", ""
    scientific_text = prepare_scientific_source_text(result.stdout, assume_pdf_layout=True)
    summary_packet = build_summary_packet_from_scientific_text(scientific_text)
    return scientific_text, summary_packet


def extract_pdf_scientific_text(pdf_path: Path, *, project_root: Path | None = None) -> str:
    scientific_text, _ = _extract_local_pdf_text(pdf_path, project_root=project_root)
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
