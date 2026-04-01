from __future__ import annotations

import html
import hashlib
import re
from datetime import date


WHITESPACE_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")
MATH_RE = re.compile(r"\${1,2}.*?\${1,2}")
LATEX_COMMAND_RE = re.compile(r"\\[A-Za-z]+")
GRAPHICAL_ABSTRACT_RE = re.compile(r"\bGraphical Abstract\b.*$", re.IGNORECASE)
CHEMICAL_TOKEN_RE = re.compile(r"\b([A-Za-z])\s+(\d)\s*([+\-])\b")


def normalize_text(value: str) -> str:
    text = value or ""
    text = html.unescape(text)
    text = text.strip().lower()
    text = WHITESPACE_RE.sub(" ", text)
    return text


def normalize_journal_title(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)
    return text


def clean_abstract_text(value: str) -> str:
    text = value or ""
    text = text.replace("<jats:p>", " ")
    text = text.replace("</jats:p>", " ")
    text = text.replace("<jats:title>", " ")
    text = text.replace("</jats:title>", " ")
    text = TAG_RE.sub(" ", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = MATH_RE.sub(" ", text)
    text = LATEX_COMMAND_RE.sub(" ", text)
    text = GRAPHICAL_ABSTRACT_RE.sub(" ", text)
    text = CHEMICAL_TOKEN_RE.sub(r"\1\2\3", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def clean_title_text(value: str) -> str:
    text = clean_abstract_text(value)
    text = text.replace(" − ", "−")
    text = text.replace(" ’ ", "’")
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def safe_date(parts: list[int] | None) -> date | None:
    if not parts:
        return None
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def build_fingerprint(source_id: str, title: str, published_date: date, doi: str) -> str:
    stable = "||".join(
        [
            source_id.strip().lower(),
            doi.strip().lower(),
            title.strip().lower(),
            published_date.isoformat(),
        ]
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def first_non_empty(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""
