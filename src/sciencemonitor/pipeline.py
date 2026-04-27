from __future__ import annotations

import multiprocessing as mp
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from .article_fetch import resolve_summary_source_material
from .config import (
    article_summaries_root,
    data_root,
    load_runtime_config,
    load_sources,
    load_topics,
    project_root,
    reports_root,
    config_templates_root,
)
from .article_index import sync_out_library
from .article_summaries import generate_article_summary_results
from .article_summary_markdown import sync_summary_report_links
from .crossref import CrossrefClient
from .http import HTTPClient
from .llm import AnalysisEngine
from .models import Paper, SourceConfig
from .reporting import build_report, write_report
from .storage import Storage
from .topics import TopicClassifier
from .utils import build_fingerprint, clean_abstract_text

NON_RESEARCH_TITLE_PATTERNS = [
    r"^issue information(?: and (?:table of )?contents?)?$",
    r"^thank you to (?:our|the) (?:peer )?reviewers(?: (?:in|for))? \d{4}$",
    r"^thank you to (?:our|the) (?:peer )?reviewers$",
    r"^editorial(?: note)?$",
    r"^guest editorial$",
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
        progress_callback: Callable[[dict], None] | None = None,
    ) -> UpdateResult:
        since_date = report_date - timedelta(days=max(days_back - 1, 0))
        fetched_total = 0
        kept: list[Paper] = []
        errors: list[str] = []
        sources = self._iter_sources(source_ids)

        self._emit_progress(
            progress_callback,
            stage="fetch_prepare",
            source_total=len(sources),
            source_index=0,
            fetched_count=0,
            kept_count=0,
        )

        for index, source in enumerate(sources, start=1):
            self._emit_progress(
                progress_callback,
                stage="fetching",
                source_total=len(sources),
                source_index=index,
                current_source=source.id,
                fetched_count=fetched_total,
                kept_count=len(kept),
            )
            try:
                papers = self._fetch_recent_works(source, since_date, report_date, max_per_source)
            except Exception as exc:
                errors.append(f"{source.id}: {exc}")
                self._emit_progress(
                    progress_callback,
                    stage="fetching",
                    source_total=len(sources),
                    source_index=index,
                    current_source=source.id,
                    fetched_count=fetched_total,
                    kept_count=len(kept),
                    last_error=str(exc),
                )
                continue
            fetched_total += len(papers)
            kept.extend(self._collect_kept_papers_from_source(papers, source, hydrate))

            self._emit_progress(
                progress_callback,
                stage="fetching",
                source_total=len(sources),
                source_index=index,
                current_source=source.id,
                fetched_count=fetched_total,
                kept_count=len(kept),
            )

        # Deduplicate across sources by DOI first, then title/date.
        self._emit_progress(
            progress_callback,
            stage="deduplicating",
            source_total=len(sources),
            source_index=len(sources),
            fetched_count=fetched_total,
            kept_count=len(kept),
        )
        deduped = self._deduplicate(kept)
        self.storage.upsert_papers(deduped)
        self._emit_progress(
            progress_callback,
            stage="update_complete",
            source_total=len(sources),
            source_index=len(sources),
            fetched_count=fetched_total,
            kept_count=len(deduped),
            error_count=len(errors),
        )
        return UpdateResult(
            fetched_count=fetched_total,
            kept_count=len(deduped),
            report_date=report_date,
            error_count=len(errors),
            errors=errors,
        )

    def generate_report(self, report_date: date) -> tuple[Path, dict]:
        return self.generate_windowed_report(report_date=report_date, window_days=7)

    def generate_windowed_report(
        self,
        report_date: date,
        window_days: int = 7,
        progress_callback: Callable[[dict], None] | None = None,
        reuse_existing_summaries: bool = True,
    ) -> tuple[Path, dict]:
        if not self.weekly_report_enabled():
            raise RuntimeError("Weekly report generation is disabled in config/runtime.json.")
        self._emit_progress(progress_callback, stage="summary_generation", report_date=report_date.isoformat(), window_days=window_days)
        summary_results = self.generate_article_summary_results(
            report_date=report_date,
            window_days=window_days,
            progress_callback=progress_callback,
            reuse_existing_summaries=reuse_existing_summaries,
        )
        self._emit_progress(
            progress_callback,
            stage="report_render",
            report_date=report_date.isoformat(),
            window_days=window_days,
            summary_count=len(summary_results),
        )
        markdown, stats = build_report(
            report_date,
            summary_results,
            missing_source_rows=self._missing_source_rows_for_report(report_date, window_days, summary_results),
            window_days=window_days,
            analysis_engine=self.analysis_engine,
            root=self.root,
            require_analysis=True,
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
        self._emit_progress(
            progress_callback,
            stage="sync_output",
            report_date=report_date.isoformat(),
            window_days=window_days,
            paper_count=stats.get("paper_count", 0),
            journal_count=stats.get("journal_count", 0),
        )
        sync_out_library(self.root)
        return report_path, stats

    def generate_article_summary_files(self, report_date: date, window_days: int = 7) -> list[Path]:
        results = self.generate_article_summary_results(report_date, window_days)
        sync_out_library(self.root)
        return [item.output_path for item in results]

    def generate_article_summary_results(
        self,
        report_date: date,
        window_days: int = 7,
        progress_callback: Callable[[dict], None] | None = None,
        reuse_existing_summaries: bool = True,
    ):
        start_date = report_date - timedelta(days=max(window_days - 1, 0))
        rows = self.storage.get_recent_papers(start_date, report_date)
        rows = [row for row in rows if not self._row_is_non_research(row)]
        return generate_article_summary_results(
            rows=rows,
            template_path=config_templates_root(self.root) / "article_summary_template.md",
            output_dir=article_summaries_root(self.root),
            analysis_engine=self.analysis_engine,
            root=self.root,
            enable_live_fetch=True,
            require_analysis=True,
            progress_callback=progress_callback,
            reuse_existing_summaries=reuse_existing_summaries,
        )

    def _missing_source_rows_for_report(
        self,
        report_date: date,
        window_days: int,
        summary_results: list,
    ) -> list:
        start_date = report_date - timedelta(days=max(window_days - 1, 0))
        rows = [row for row in self.storage.get_recent_papers(start_date, report_date) if not self._row_is_non_research(row)]
        summarized_dois = {str(item.row["doi"] or "").strip().lower() for item in summary_results if str(item.row["doi"] or "").strip()}
        summarized_titles = {str(item.row["title"] or "").strip().lower() for item in summary_results if str(item.row["title"] or "").strip()}
        missing = []
        for row in rows:
            doi = str(row["doi"] or "").strip().lower()
            title = str(row["title"] or "").strip().lower()
            if (doi and doi in summarized_dois) or (not doi and title and title in summarized_titles):
                continue
            if not str(row["abstract"] or "").strip():
                missing.append(row)
        return missing

    def sync_output_library(self):
        return sync_out_library(self.root)

    def run_daily(
        self,
        report_date: date,
        days_back: int = 7,
        max_per_source: int = 20,
        hydrate: bool = True,
        source_ids: set[str] | None = None,
        progress_callback: Callable[[dict], None] | None = None,
        reuse_existing_summaries: bool = True,
    ) -> tuple[UpdateResult, Path | None, dict]:
        self._emit_progress(
            progress_callback,
            stage="starting",
            report_date=report_date.isoformat(),
            days_back=days_back,
            max_per_source=max_per_source,
            hydrate=hydrate,
        )
        update_result = self.update(
            report_date=report_date,
            days_back=days_back,
            max_per_source=max_per_source,
            hydrate=hydrate,
            source_ids=source_ids,
            progress_callback=progress_callback,
        )
        if not self.weekly_report_enabled():
            self._emit_progress(
                progress_callback,
                stage="summary_generation",
                report_date=report_date.isoformat(),
                window_days=days_back,
            )
            self.generate_article_summary_results(
                report_date,
                window_days=days_back,
                progress_callback=progress_callback,
                reuse_existing_summaries=reuse_existing_summaries,
            )
            self._emit_progress(progress_callback, stage="sync_output", report_date=report_date.isoformat(), window_days=days_back)
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
        self._emit_progress(
            progress_callback,
            stage="building_report",
            report_date=report_date.isoformat(),
            window_days=days_back,
            fetched_count=update_result.fetched_count,
            kept_count=update_result.kept_count,
        )
        report_path, stats = self.generate_windowed_report(
            report_date,
            window_days=days_back,
            progress_callback=progress_callback,
            reuse_existing_summaries=reuse_existing_summaries,
        )
        self._emit_progress(
            progress_callback,
            stage="done",
            report_date=report_date.isoformat(),
            window_days=days_back,
            fetched_count=update_result.fetched_count,
            kept_count=update_result.kept_count,
            paper_count=stats.get("paper_count", 0),
            journal_count=stats.get("journal_count", 0),
        )
        return update_result, report_path, stats

    def weekly_report_enabled(self) -> bool:
        return True

    def list_sources(self) -> list[SourceConfig]:
        return list(self.sources)

    def _iter_sources(self, source_ids: set[str] | None) -> list[SourceConfig]:
        if not source_ids:
            return list(self.sources)
        return [source for source in self.sources if source.id in source_ids]

    def _emit_progress(self, callback: Callable[[dict], None] | None, **payload) -> None:
        if callback is None:
            return
        callback(payload)

    def _collect_kept_papers_from_source(
        self,
        papers: list[Paper],
        source: SourceConfig,
        hydrate: bool,
    ) -> list[Paper]:
        kept: list[Paper] = []
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
        return kept

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
        if not paper.url and not paper.doi:
            return
        try:
            material = resolve_summary_source_material(
                doi=paper.doi,
                url=paper.url,
                title=paper.title,
                journal=paper.source_name or paper.journal_title,
                abstract=paper.abstract,
                authors=paper.authors,
                published_date=paper.published_date.isoformat(),
                http=self.http,
                crossref=self.crossref,
            )
        except Exception:
            return

        if material.abstract and (not paper.abstract or len(material.abstract) > len(paper.abstract)):
            paper.abstract = clean_abstract_text(material.abstract)
        if material.title and len(material.title) > len(paper.title) and len(material.title) < 240:
            paper.title = material.title
        if material.url and not paper.url:
            paper.url = material.url
        if material.authors and not paper.authors:
            paper.authors = list(material.authors)
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
