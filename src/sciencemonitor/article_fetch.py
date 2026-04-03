from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import data_root
from .crossref import CrossrefClient
from .html_extract import extract_full_text_from_html, extract_page_metadata, extract_pdf_urls
from .http import HTTPClient
from .utils import clean_abstract_text, clean_title_text


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


def prepare_scientific_source_text(raw_text: str, *, assume_pdf_layout: bool = False) -> str:
    text = html.unescape(raw_text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n")
    text = text.replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    if not text.strip():
        return ""

    lines = _normalize_scientific_lines(text, assume_pdf_layout=assume_pdf_layout)
    if not lines:
        return ""
    cleaned = _collapse_scientific_lines(lines)
    if not cleaned:
        return ""

    start_match = re.search(
        r"(?im)^(Abstract|Plain Language Summary|Key Points|1\.\s*Introduction|Introduction)\b",
        cleaned,
    )
    if start_match:
        cleaned = cleaned[start_match.start():]
    tail_patterns = [
        r"(?im)^Acknowledg(?:ment|ements)\b",
        r"(?im)^Data Availability Statement\b",
        r"(?im)^Code Availability\b",
        r"(?im)^References\b",
        r"(?im)^Reference\b",
        r"(?im)^Appendix\b",
        r"(?im)^Supporting Information\b",
    ]
    end_index = len(cleaned)
    for pattern in tail_patterns:
        match = re.search(pattern, cleaned)
        if match:
            end_index = min(end_index, match.start())
    return cleaned[:end_index].strip()


def build_summary_packet_from_scientific_text(
    text: str,
    *,
    max_chars: int = 7000,
    abstract_override: str = "",
) -> str:
    cleaned = prepare_scientific_source_text(text)
    if not cleaned:
        return ""

    sections: list[str] = []
    abstract = clean_abstract_text(abstract_override)
    if abstract:
        abstract = re.sub(r"^\s*Abstract[:\s]+", "", abstract, flags=re.IGNORECASE)
    if not abstract:
        abstract = _extract_labeled_block(
            cleaned,
            "Abstract",
            stop_labels=["Key Points", "Plain Language Summary", "1. Introduction", "Introduction"],
        )
    if abstract:
        sections.append("Abstract:\n" + abstract)

    if not abstract_override:
        plain_language = _extract_labeled_block(
            cleaned,
            "Plain Language Summary",
            stop_labels=["1. Introduction", "Introduction"],
        )
        if plain_language:
            sections.append("Plain Language Summary:\n" + plain_language)

    numbered_sections = _extract_numbered_sections(cleaned)
    methods = _collect_numbered_section_content(
        numbered_sections,
        section_type="methods",
        max_sentences=6,
        max_chars=1600,
    )
    if methods:
        sections.append("Methods/Data:\n" + methods)

    results = _collect_numbered_section_content(
        numbered_sections,
        section_type="results",
        max_sentences=8,
        max_chars=2600,
    )
    if results:
        sections.append("Results:\n" + results)

    discussion = _collect_numbered_section_content(
        numbered_sections,
        section_type="conclusions",
        max_sentences=5,
        max_chars=1500,
    )
    if discussion:
        sections.append("Discussion/Conclusion:\n" + discussion)

    compact = "\n\n".join(part for part in sections if part).strip()
    if not compact:
        compact = cleaned
        abstract_index = re.search(r"(?im)^Abstract\b", cleaned)
        if abstract_index:
            compact = cleaned[abstract_index.start():]
    if len(compact) > max_chars:
        compact = compact[:max_chars].rsplit(" ", 1)[0].strip() + "\n..."
    return compact


def _compact_pdf_text_for_summary(raw_text: str, *, max_chars: int = 6000) -> str:
    return build_summary_packet_from_scientific_text(raw_text, max_chars=max_chars)


def _extract_pdf_section(text: str, start_pattern: str, end_patterns: list[str]) -> str:
    start_match = re.search(start_pattern, text, flags=re.IGNORECASE)
    if not start_match:
        return ""
    end_index = len(text)
    for pattern in end_patterns:
        match = re.search(pattern, text[start_match.end():], flags=re.IGNORECASE)
        if match:
            end_index = min(end_index, start_match.end() + match.start())
    return text[start_match.end():end_index].strip()


def _drop_non_scientific_blocks(text: str) -> str:
    cleaned = text
    patterns = [
        (r"\bSupporting Information:.*?(?=\bAbstract\b|\bKey Points\b|\bPlain Language Summary\b|\b1\.\s*Introduction\b)", " "),
        (r"\bCorrespondence to:.*?(?=\bCitation:\b|\bReceived\b|\bAbstract\b|\b1\.\s*Introduction\b)", " "),
        (r"\bCitation:.*?(?=\bReceived\b|\bAbstract\b|\b1\.\s*Introduction\b)", " "),
        (r"\bAuthor Contributions:.*?(?=\b1\.\s*Introduction\b)", " "),
        (r"\bReceived\b.*?(?=\bAccepted\b|\bAbstract\b|\b1\.\s*Introduction\b)", " "),
        (r"\bAccepted\b.*?(?=\bAbstract\b|\b1\.\s*Introduction\b)", " "),
        (r"\b©\s*\d{4}.*?(?=\b1\.\s*Introduction\b)", " "),
    ]
    for pattern, replacement in patterns:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return clean_abstract_text(cleaned)


def _normalize_scientific_lines(text: str, *, assume_pdf_layout: bool) -> list[str]:
    lines: list[str] = []
    for raw_line in text.split("\n"):
        leading_spaces = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = re.sub(r"\s+", " ", raw_line).strip()
        if not stripped:
            lines.append("")
            continue
        if assume_pdf_layout and leading_spaces < 16 and not _should_keep_low_indent_line(stripped):
            continue
        if _should_drop_scientific_line(stripped):
            continue
        normalized = _split_inline_heading(stripped)
        if not normalized:
            continue
        lines.extend(part for part in normalized.split("\n"))
    return lines


def _collapse_scientific_lines(lines: list[str]) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                blocks.append(" ".join(paragraph).strip())
                paragraph = []
            continue
        if _is_scientific_heading_line(stripped):
            if paragraph:
                blocks.append(" ".join(paragraph).strip())
                paragraph = []
            blocks.append(stripped)
            continue
        paragraph.append(stripped)
    if paragraph:
        blocks.append(" ".join(paragraph).strip())
    return "\n".join(block for block in blocks if block).strip()


def _should_drop_scientific_line(line: str) -> bool:
    patterns = [
        r"^RESEARCH ARTICLE\b",
        r"^10\.\d{4,9}/",
        r"^Key Points:?\b",
        r"^[•·]\s+",
        r"^Supporting Information:?$",
        r"^Supporting Information may be found\b",
        r"^Correspondence to:?$",
        r"^[A-Z]\.\s*[A-Za-z-]+@",
        r"^Citation:?$",
        r"^Received\b",
        r"^Accepted\b",
        r"^Author Contributions:?$",
        r"^(Conceptualization|Data curation|Formal analysis|Funding acquisition|Investigation|Methodology|Project Administration|Resources|Software|Supervision|Validation|Visualization|Writing\b.*):",
        r"^©\s*\d{4}\b",
        r"^CochraneChina,?$",
        r"^Figure\s+\d+\.",
        r"^Table\s+\d+\.",
        r"^This is an open access article\b",
        r"^the terms of the Creative Commons\b",
        r"^Attribution-[A-Za-z-]+\b",
        r"^License, which permits\b",
        r"^distribution in any medium\b",
        r"^original work is properly cited\b",
        r"^non-commercial and no modifications\b",
        r"^adaptations are made\.$",
        r"^LI ET AL\.\b",
        r"^[A-Za-z][A-Za-z .:&-]+\s+10\.\d{4,9}/",
        r"^\d+\s+of\s+\d+$",
        r"^\d{8,},?$",
        r"^\d{4},$",
        r"^\d{1,2},$",
        r"^(Downloaded|from|by|Wiley|Online|Library|on|See|the|Terms|and|Conditions|for|rules|of|use;?|OA|articles|are|governed|applicable|Creative|Commons|License)$",
        r"^\[\d{2}/\d{2}/\d{4}\]\.?$",
        r"^\(https?://onlinelibrary\.wiley\.com/terms-and-conditions\)$",
        r"^https?://agupubs\.onlinelibrary\.wiley\.com/doi/",
        r"^https?://doi\.org/",
        r"^https?://",
    ]
    for pattern in patterns:
        if re.match(pattern, line, flags=re.IGNORECASE):
            return True
    return False


def _split_inline_heading(line: str) -> str:
    inline_headings = [
        "Abstract",
        "Plain Language Summary",
    ]
    for heading in inline_headings:
        if not line.startswith(heading):
            continue
        remainder = line[len(heading):].strip(" :")
        heading_label = heading.rstrip(":")
        if not remainder:
            return heading_label
        return f"{heading_label}\n{remainder}"
    return line


def _is_scientific_heading_line(line: str) -> bool:
    if re.match(r"^(Abstract|Plain Language Summary)\b", line, flags=re.IGNORECASE):
        return True
    return bool(re.match(r"^\d+\.\s+[A-Z][A-Za-z0-9,()\-–/& ]{2,90}$", line))


def _should_keep_low_indent_line(line: str) -> bool:
    if _is_scientific_heading_line(line):
        return True
    return bool(re.match(r"^(Abstract|Plain Language Summary)\b", line, flags=re.IGNORECASE))


def _extract_labeled_block(text: str, label: str, *, stop_labels: list[str]) -> str:
    start_pattern = rf"(?im)^{re.escape(label)}\b"
    start_match = re.search(start_pattern, text)
    if not start_match:
        return ""
    end_index = len(text)
    for stop_label in stop_labels:
        match = re.search(rf"(?im)^{re.escape(stop_label)}\b", text[start_match.end():])
        if match:
            end_index = min(end_index, start_match.end() + match.start())
    block = text[start_match.end():end_index].strip()
    return _trim_section_text(block)


def _extract_numbered_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?im)^(?P<title>\d+\.\s+[A-Z][A-Za-z0-9,()\-–/& ]{2,90})$", text))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group("title").strip()
        body = _trim_section_text(text[start:end].strip())
        if body:
            sections.append((title, body))
    return sections


def _collect_numbered_section_content(
    sections: list[tuple[str, str]],
    *,
    section_type: str,
    max_sentences: int,
    max_chars: int,
) -> str:
    matched_sections = _match_section_group(sections, section_type=section_type)
    if not matched_sections:
        return ""

    candidates: list[dict[str, object]] = []
    for section_index, (title, body) in enumerate(matched_sections):
        for sentence_index, sentence in enumerate(_split_scientific_sentences(body)):
            score = _score_evidence_sentence(sentence, section_type=section_type, title=title)
            if score <= 0:
                continue
            candidates.append(
                {
                    "title": title,
                    "sentence": sentence,
                    "score": score,
                    "section_index": section_index,
                    "sentence_index": sentence_index,
                }
            )

    if not candidates:
        fallback_lines: list[str] = []
        for title, body in matched_sections:
            sentences = _split_scientific_sentences(body)
            if not sentences:
                continue
            fallback_lines.append(f"{title}: {' '.join(sentences[:2])}")
        return "\n".join(line for line in fallback_lines if line).strip()

    selected = _select_evidence_candidates(
        candidates,
        max_sentences=max_sentences,
        max_chars=max_chars,
    )
    grouped: dict[str, list[str]] = {}
    for item in selected:
        title = str(item["title"])
        sentence = str(item["sentence"])
        grouped.setdefault(title, []).append(sentence)
    return "\n".join(f"{title}: {' '.join(sentences)}" for title, sentences in grouped.items()).strip()


def _match_section_group(
    sections: list[tuple[str, str]],
    *,
    section_type: str,
) -> list[tuple[str, str]]:
    matched: list[tuple[str, str]] = []
    if section_type == "methods":
        keywords = ("data", "method", "methods", "methodology", "model", "description", "setup")
        for title, body in sections:
            title_lower = title.lower()
            if any(keyword in title_lower for keyword in keywords):
                matched.append((title, body))
    elif section_type == "results":
        keywords = ("result", "results", "analysis", "evaluation", "performance", "discussion", "comparison")
        for title, body in sections:
            title_lower = title.lower()
            if "conclusion" in title_lower:
                continue
            if any(keyword in title_lower for keyword in keywords):
                matched.append((title, body))
    elif section_type == "conclusions":
        primary_keywords = ("conclusion", "conclusions", "summary")
        fallback_keywords = ("discussion",)
        for title, body in sections:
            title_lower = title.lower()
            if any(keyword in title_lower for keyword in primary_keywords):
                matched.append((title, body))
        if not matched:
            for title, body in sections:
                title_lower = title.lower()
                if any(keyword in title_lower for keyword in fallback_keywords):
                    matched.append((title, body))
    return matched


def _split_scientific_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[。！？!?])\s+|(?<=[.;；])\s+(?=[A-Z0-9(])|(?<=[.])\s+(?=[A-Z][a-z])", normalized)
    sentences: list[str] = []
    for part in parts:
        clean = part.strip()
        if not clean:
            continue
        if sentences and len(clean) < 24 and not re.search(r"\d", clean):
            sentences[-1] = f"{sentences[-1]} {clean}".strip()
            continue
        sentences.append(clean)
    return sentences


def _score_evidence_sentence(sentence: str, *, section_type: str, title: str) -> int:
    lowered = sentence.lower()
    title_lower = title.lower()
    score = 0

    if len(sentence) < 35:
        score -= 2
    if len(sentence) > 420:
        score -= 1
    if re.search(r"\d", sentence):
        score += 2
    if re.search(r"%|rmse|mae|bias|corr|correlation|coefficient|error|improv|better|worse|higher|lower", lowered):
        score += 3
    if re.search(r"storm|geomagnetic|magnetic storm|substorm|quiet|disturb", lowered):
        score += 3
    if re.search(r"show|shows|showed|find|finds|found|reveal|reveals|revealed|indicat|demonstrat|suggest", lowered):
        score += 2

    if section_type == "methods":
        if re.search(r"data|dataset|observation|observed|measurement|instrument|satellite|fpi|superdarn|champ|grace|gnss|roti", lowered):
            score += 4
        if re.search(r"model|network|resnet|train|trained|training|evaluate|evaluation|input|feature|assimilat|simulation", lowered):
            score += 4
        if "introduction" in title_lower:
            score -= 2
    elif section_type == "results":
        if re.search(r"compared|comparison|outperform|improv|reduce|increase|decrease|response|variation|oscillation|anomaly", lowered):
            score += 4
        if re.search(r"case|event|during|under|storm", lowered):
            score += 3
        if "discussion" in title_lower:
            score += 1
    elif section_type == "conclusions":
        if re.search(r"conclude|conclusion|summary|overall|therefore|thus|highlight", lowered):
            score += 4
        if re.search(r"contribution|implication|suggest|indicate|demonstrat", lowered):
            score += 3

    if re.search(r"this paper is organized|section \d+|the remainder of this paper", lowered):
        score -= 6
    return score


def _select_evidence_candidates(
    candidates: list[dict[str, object]],
    *,
    max_sentences: int,
    max_chars: int,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    consumed_chars = 0
    for item in sorted(
        candidates,
        key=lambda current: (
            -int(current["score"]),
            int(current["section_index"]),
            int(current["sentence_index"]),
        ),
    ):
        sentence = str(item["sentence"])
        projected = consumed_chars + len(sentence)
        if selected and projected > max_chars:
            continue
        selected.append(item)
        consumed_chars = projected
        if len(selected) >= max_sentences:
            break

    if not selected and candidates:
        selected = [max(candidates, key=lambda current: int(current["score"]))]

    return sorted(
        selected,
        key=lambda current: (
            int(current["section_index"]),
            int(current["sentence_index"]),
        ),
    )


def _trim_section_text(text: str) -> str:
    value = "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()
    if not value:
        return ""
    return re.sub(r"[ \t]+", " ", value)


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
        if clean:
            return clean
    return ""


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
