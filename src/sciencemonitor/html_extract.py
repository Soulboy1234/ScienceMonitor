from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

from .utils import clean_abstract_text, clean_title_text, first_non_empty


ABSTRACT_SECTION_RE = re.compile(
    r"<(?:section|div)[^>]+(?:abstract|summary)[^>]*>(.*?)</(?:section|div)>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\\1>")
META_CONTENT_RE = re.compile(
    r'(?is)<meta[^>]+(?:name|property)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']+)["\']'
)
HREF_RE = re.compile(r'(?is)<a[^>]+href=["\']([^"\']+)["\']')


class MetadataHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.script_blobs: list[str] = []
        self.in_title = False
        self.current_script_is_json = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "meta":
            key = attr_map.get("name") or attr_map.get("property") or attr_map.get("itemprop")
            if key and "content" in attr_map:
                self.meta[key.lower()] = attr_map["content"]
        elif tag.lower() == "title":
            self.in_title = True
        elif tag.lower() == "script":
            self.current_script_is_json = attr_map.get("type", "").lower() == "application/ld+json"

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False
        elif tag.lower() == "script":
            self.current_script_is_json = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        elif self.current_script_is_json:
            self.script_blobs.append(data)


def strip_tags(fragment: str) -> str:
    text = TAG_RE.sub(" ", fragment)
    text = unescape(text)
    return clean_abstract_text(text)


def _extract_description_from_jsonld(script_blobs: list[str]) -> str:
    for blob in script_blobs:
        blob = blob.strip()
        if not blob:
            continue
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            description = item.get("description")
            if isinstance(description, str) and description.strip():
                return clean_abstract_text(description)
    return ""


def extract_page_metadata(html: str) -> tuple[str, str]:
    parser = MetadataHTMLParser()
    parser.feed(html)

    title = clean_title_text(" ".join(parser.title_parts))
    meta = parser.meta
    abstract = first_non_empty(
        meta.get("citation_abstract", ""),
        meta.get("dc.description", ""),
        meta.get("description", ""),
        meta.get("og:description", ""),
        meta.get("twitter:description", ""),
        _extract_description_from_jsonld(parser.script_blobs),
    )

    if not abstract:
        match = ABSTRACT_SECTION_RE.search(html)
        if match:
            abstract = strip_tags(match.group(1))

    page_title = clean_title_text(
        first_non_empty(
            meta.get("citation_title", ""),
            meta.get("og:title", ""),
            meta.get("twitter:title", ""),
            title,
        )
    )
    return page_title, abstract


def extract_pdf_urls(html: str, base_url: str) -> list[str]:
    candidates: list[str] = []
    for key, content in META_CONTENT_RE.findall(html):
        if key.lower() in {"citation_pdf_url", "pdf_url"} and content.strip():
            candidates.append(urljoin(base_url, content.strip()))

    for href in HREF_RE.findall(html):
        clean = href.strip()
        lowered = clean.lower()
        if ".pdf" in lowered or "/pdf" in lowered:
            candidates.append(urljoin(base_url, clean))

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def extract_full_text_from_html(html: str) -> tuple[str, bool]:
    text = SCRIPT_STYLE_RE.sub(" ", html)
    text = TAG_RE.sub(" ", text)
    text = unescape(text)
    text = clean_abstract_text(text)
    lowered = text.lower()
    likely_full_text = len(text) >= 6000 and any(
        marker in lowered
        for marker in ("introduction", "methods", "results", "discussion", "conclusion", "references")
    )
    return text, likely_full_text
