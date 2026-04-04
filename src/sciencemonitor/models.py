from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SourceConfig:
    id: str
    journal_title: str
    aliases: list[str]
    tier: str
    mode: str
    priority: int
    description: str
    issn: str = ""
    crossref_date_field: str = "pub"


@dataclass(frozen=True)
class TopicProfile:
    id: str
    label: str
    keywords: list[str]


@dataclass
class Paper:
    fingerprint: str
    source_id: str
    source_name: str
    journal_title: str
    title: str
    abstract: str
    published_date: date
    doi: str
    url: str
    authors: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    topic_labels: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    tier: str = ""
    mode: str = ""
    raw_container_title: str = ""
    fetched_at: str = ""
    notes: list[str] = field(default_factory=list)

    def as_db_tuple(self) -> tuple[Any, ...]:
        return (
            self.fingerprint,
            self.source_id,
            self.source_name,
            self.journal_title,
            self.title,
            self.abstract,
            self.published_date.isoformat(),
            self.doi,
            self.url,
            "\n".join(self.authors),
            "\n".join(self.topics),
            "\n".join(self.topic_labels),
            self.relevance_score,
            self.tier,
            self.mode,
            self.raw_container_title,
            self.fetched_at,
            "\n".join(self.notes),
        )


@dataclass(frozen=True)
class ArticleSummaryResult:
    row: Any
    analysis: Any
    output_path: Any
    note_title: str
    chinese_title: str
    tags: list[str]
    body: str
    supplement: str
    recommendation: str
    one_sentence: str
    rendered_markdown: str
