from __future__ import annotations

import multiprocessing as mp
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import (
    article_summaries_root,
    data_root,
    load_runtime_config,
    load_sources,
    load_topics,
    project_root,
    reports_root,
    templates_root,
)
from .article_index import sync_out_library
from .article_summaries import generate_article_summary_results, sync_summary_report_links
from .crossref import CrossrefClient
from .html_extract import extract_page_metadata
from .http import HTTPClient
from .llm import AnalysisEngine
from .models import Paper, SourceConfig
from .reporting import build_report, write_report
from .storage import Storage
from .topics import TopicClassifier
from .utils import build_fingerprint, clean_abstract_text

NON_RESEARCH_TITLE_PATTERNS = [
    r"^issue information$",
    r"^thank you to our \d{4} reviewers$",
    r"^editorial$",
    r"^corrigendum\b",
    r"^erratum\b",
    r"^retraction\b",
    r"^expression of concern\b",
    r"^reply to\b",
    r"^comment on\b",
]


@dataclass
class UpdateResult:
    fetched_count: int
    kept_count: int
    report_date: date
    error_count: int
    errors: list[str]


def _crossref_fetch_worker(
    queue,
    source: SourceConfig,
    since_date_iso: str,
    until_date_iso: str,
    max_rows: int,
    timeout: int,
) -> None:
    try:
        client = CrossrefClient(HTTPClient(timeout=timeout))
        papers = client.fetch_recent_works(
            source=source,
            since_date=date.fromisoformat(since_date_iso),
            until_date=date.fromisoformat(until_date_iso),
            max_rows=max_rows,
        )
        queue.put(("ok", papers))
    except Exception as exc:  # pragma: no cover - worker failure path is exercised via parent handling.
        queue.put(("error", f"{type(exc).__name__}: {exc}"))


class ScienceMonitor:
    def __init__(
        self,
        root: Path | None = None,
        http_client: HTTPClient | None = None,
        crossref_client: CrossrefClient | None = None,
        storage: Storage | None = None,
    ) -> None:
        self.root = root or project_root()
        self.http = http_client or HTTPClient()
        self.crossref = crossref_client or CrossrefClient(self.http)
        self.use_isolated_crossref_fetch = crossref_client is None
        self.crossref_fetch_timeout = max(int(getattr(self.http, "timeout", 15) or 15), 15)
        self.sources = load_sources(self.root / "config" / "sources.json")
        self.topics = load_topics(self.root / "config" / "topics.json")
        self.runtime_config = load_runtime_config(self.root)
        self.classifier = TopicClassifier(self.topics)
        self.storage = storage or Storage(data_root(self.root) / "science_monitor.db")
        self.analysis_engine = AnalysisEngine(self.root)

    def close(self) -> None:
        self.storage.close()

    def update(
        self,
        report_date: date,
        days_back: int,
        max_per_source: int,
        hydrate: bool = True,
        source_ids: set[str] | None = None,
    ) -> UpdateResult:
        since_date = report_date - timedelta(days=max(days_back - 1, 0))
        fetched_total = 0
        kept: list[Paper] = []
        errors: list[str] = []

        for source in self._iter_sources(source_ids):
            try:
                papers = self._fetch_recent_works(source, since_date, report_date, max_per_source)
            except Exception as exc:
                errors.append(f"{source.id}: {exc}")
                continue
            fetched_total += len(papers)
            for paper in papers:
                result = self.classifier.classify(paper, source)
                if hydrate and self._should_hydrate_paper(paper, source, result):
                    self._hydrate_paper(paper)
                    result = self.classifier.classify(paper, source)
                if self._should_drop_paper(paper, source, result):
                    continue
                if not self.classifier.should_keep(result, source):
                    continue
                paper.topics = result.topics
                paper.topic_labels = result.topic_labels
                paper.relevance_score = result.relevance_score
                paper.notes = result.matched_keywords
                if paper.doi or paper.title:
                    paper.fingerprint = build_fingerprint(
                        paper.source_id,
                        paper.title,
                        paper.published_date,
                        paper.doi,
                    )
                kept.append(paper)

        # Deduplicate across sources by DOI first, then title/date.
        deduped = self._deduplicate(kept)
        self.storage.upsert_papers(deduped)
        return UpdateResult(
            fetched_count=fetched_total,
            kept_count=len(deduped),
            report_date=report_date,
            error_count=len(errors),
            errors=errors,
        )

    def generate_report(self, report_date: date) -> tuple[Path, dict]:
        return self.generate_windowed_report(report_date=report_date, window_days=7)

    def generate_windowed_report(self, report_date: date, window_days: int = 7) -> tuple[Path, dict]:
        if not self.weekly_report_enabled():
            raise RuntimeError("Weekly report generation is disabled in config/runtime.json.")
        summary_results = self.generate_article_summary_results(report_date=report_date, window_days=window_days)
        markdown, stats = build_report(
            report_date,
            summary_results,
            window_days=window_days,
            analysis_engine=self.analysis_engine,
        )
        report_path = write_report(reports_root(self.root), report_date, markdown)
        sync_summary_report_links(summary_results, report_path, root=self.root)
        self.storage.save_report(
            report_date=report_date,
            path=report_path,
            markdown=markdown,
            stats=stats,
            created_at=datetime.utcnow().isoformat(timespec="seconds"),
        )
        sync_out_library(self.root)
        return report_path, stats

    def generate_article_summary_files(self, report_date: date, window_days: int = 7) -> list[Path]:
        results = self.generate_article_summary_results(report_date, window_days)
        sync_out_library(self.root)
        return [item.output_path for item in results]

    def generate_article_summary_results(self, report_date: date, window_days: int = 7):
        start_date = report_date - timedelta(days=max(window_days - 1, 0))
        rows = self.storage.get_recent_papers(start_date, report_date)
        rows = [row for row in rows if not self._row_is_non_research(row)]
        return generate_article_summary_results(
            rows=rows,
            template_path=templates_root(self.root) / "article_summary_template.md",
            output_dir=article_summaries_root(self.root),
            analysis_engine=self.analysis_engine,
        )

    def sync_output_library(self):
        return sync_out_library(self.root)

    def run_daily(
        self,
        report_date: date,
        days_back: int = 7,
        max_per_source: int = 20,
        source_ids: set[str] | None = None,
    ) -> tuple[UpdateResult, Path | None, dict]:
        update_result = self.update(
            report_date=report_date,
            days_back=days_back,
            max_per_source=max_per_source,
            hydrate=True,
            source_ids=source_ids,
        )
        if not self.weekly_report_enabled():
            self.generate_article_summary_results(report_date, window_days=days_back)
            sync_out_library(self.root)
            return (
                update_result,
                None,
                {
                    "report_date": report_date.isoformat(),
                    "window_days": days_back,
                    "paper_count": 0,
                    "journal_count": 0,
                    "highlight_count": 0,
                },
            )
        report_path, stats = self.generate_windowed_report(report_date, window_days=days_back)
        return update_result, report_path, stats

    def weekly_report_enabled(self) -> bool:
        return bool(self.runtime_config.get("features", {}).get("weekly_report_enabled", True))

    def list_sources(self) -> list[SourceConfig]:
        return list(self.sources)

    def _iter_sources(self, source_ids: set[str] | None) -> list[SourceConfig]:
        if not source_ids:
            return list(self.sources)
        return [source for source in self.sources if source.id in source_ids]

    def _fetch_recent_works(
        self,
        source: SourceConfig,
        since_date: date,
        until_date: date,
        max_rows: int,
    ) -> list[Paper]:
        if not self.use_isolated_crossref_fetch:
            return self.crossref.fetch_recent_works(
                source=source,
                since_date=since_date,
                until_date=until_date,
                max_rows=max_rows,
            )

        ctx = mp.get_context("spawn")
        queue = ctx.Queue()
        process = ctx.Process(
            target=_crossref_fetch_worker,
            args=(
                queue,
                source,
                since_date.isoformat(),
                until_date.isoformat(),
                max_rows,
                self.crossref_fetch_timeout,
            ),
        )
        process.start()
        process.join(self.crossref_fetch_timeout + 5)
        if process.is_alive():
            process.terminate()
            process.join(2)
            raise TimeoutError(
                f"{source.id} fetch exceeded {self.crossref_fetch_timeout}s and was terminated"
            )

        if not queue.empty():
            status, payload = queue.get()
            if status == "ok":
                return payload
            raise RuntimeError(payload)

        if process.exitcode not in (0, None):
            raise RuntimeError(f"{source.id} worker exited with code {process.exitcode}")
        return []

    def _should_hydrate_paper(self, paper: Paper, source: SourceConfig, result) -> bool:
        if paper.abstract and len(paper.abstract) >= 80:
            return False
        if source.mode == "full":
            return True
        return bool(result.topics) or result.has_domain_anchor or result.has_strong_domain_anchor

    def _should_drop_paper(self, paper: Paper, source: SourceConfig, result) -> bool:
        title = paper.title.strip().lower()
        if any(re.match(pattern, title) for pattern in NON_RESEARCH_TITLE_PATTERNS):
            return True
        if result.has_noise_conflict and not result.has_strong_domain_anchor:
            return True
        if source.mode == "full" and not result.topics and not result.has_strong_domain_anchor:
            return True
        if source.mode == "full" and self._only_auxiliary_topics(result.topics) and not result.has_strong_domain_anchor:
            return True
        return False

    def _row_is_non_research(self, row) -> bool:
        title = str(row["title"] or "").strip().lower()
        return any(re.match(pattern, title) for pattern in NON_RESEARCH_TITLE_PATTERNS)

    def _only_auxiliary_topics(self, topics: list[str]) -> bool:
        return bool(topics) and all(topic == "methods_models" for topic in topics)

    def _hydrate_paper(self, paper: Paper) -> None:
        if not paper.url:
            return
        try:
            html = self.http.get_text(paper.url)
            page_title, abstract = extract_page_metadata(html)
        except Exception:
            return

        if abstract and (not paper.abstract or len(abstract) > len(paper.abstract)):
            paper.abstract = clean_abstract_text(abstract)
        if page_title and len(page_title) > len(paper.title) and len(page_title) < 240:
            paper.title = page_title
        time.sleep(0.1)

    def _deduplicate(self, papers: list[Paper]) -> list[Paper]:
        by_key: dict[str, Paper] = {}
        for paper in sorted(papers, key=lambda item: (item.relevance_score, item.tier), reverse=True):
            key = self._paper_key(paper)
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = paper
                continue
            if len(paper.abstract) > len(existing.abstract):
                by_key[key] = paper
        return list(by_key.values())

    def _paper_key(self, paper: Paper) -> str:
        if paper.doi:
            return f"doi::{paper.doi.lower()}"
        return f"title::{paper.title.strip().lower()}::{paper.published_date.isoformat()}"
