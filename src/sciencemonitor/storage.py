from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from .models import Paper


CREATE_PAPERS_SQL = """
CREATE TABLE IF NOT EXISTS papers (
    fingerprint TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    journal_title TEXT NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    published_date TEXT NOT NULL,
    doi TEXT NOT NULL,
    url TEXT NOT NULL,
    authors TEXT NOT NULL,
    topics TEXT NOT NULL,
    topic_labels TEXT NOT NULL,
    relevance_score REAL NOT NULL,
    tier TEXT NOT NULL,
    mode TEXT NOT NULL,
    raw_container_title TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    notes TEXT NOT NULL
)
"""

CREATE_REPORTS_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    report_date TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    markdown TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        self.conn.close()

    def _initialize(self) -> None:
        with self.conn:
            self.conn.execute(CREATE_PAPERS_SQL)
            self.conn.execute(CREATE_REPORTS_SQL)

    def upsert_papers(self, papers: list[Paper]) -> int:
        if not papers:
            return 0
        sql = """
        INSERT INTO papers (
            fingerprint, source_id, source_name, journal_title, title, abstract,
            published_date, doi, url, authors, topics, topic_labels,
            relevance_score, tier, mode, raw_container_title, fetched_at, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fingerprint) DO UPDATE SET
            abstract = excluded.abstract,
            url = excluded.url,
            authors = excluded.authors,
            topics = excluded.topics,
            topic_labels = excluded.topic_labels,
            relevance_score = excluded.relevance_score,
            fetched_at = excluded.fetched_at,
            notes = excluded.notes
        """
        with self.conn:
            self.conn.executemany(sql, [paper.as_db_tuple() for paper in papers])
        return len(papers)

    def get_papers_for_date(self, report_date: date) -> list[sqlite3.Row]:
        sql = """
        SELECT *
        FROM papers
        WHERE published_date = ?
        ORDER BY relevance_score DESC, source_name ASC, title ASC
        """
        return list(self.conn.execute(sql, (report_date.isoformat(),)))

    def get_recent_papers(self, start_date: date, end_date: date) -> list[sqlite3.Row]:
        sql = """
        SELECT *
        FROM papers
        WHERE published_date BETWEEN ? AND ?
        ORDER BY published_date DESC, relevance_score DESC
        """
        return list(self.conn.execute(sql, (start_date.isoformat(), end_date.isoformat())))

    def get_paper_by_doi(self, doi: str) -> sqlite3.Row | None:
        sql = """
        SELECT *
        FROM papers
        WHERE lower(doi) = lower(?)
        ORDER BY published_date DESC, relevance_score DESC
        LIMIT 1
        """
        return self.conn.execute(sql, (doi,)).fetchone()

    def search_paper_by_title(self, title: str) -> sqlite3.Row | None:
        sql = """
        SELECT *
        FROM papers
        WHERE lower(title) = lower(?)
        ORDER BY published_date DESC, relevance_score DESC
        LIMIT 1
        """
        row = self.conn.execute(sql, (title,)).fetchone()
        if row:
            return row
        sql_like = """
        SELECT *
        FROM papers
        WHERE lower(title) LIKE lower(?)
        ORDER BY published_date DESC, relevance_score DESC
        LIMIT 1
        """
        return self.conn.execute(sql_like, (f"%{title}%",)).fetchone()

    def save_report(self, report_date: date, path: Path, markdown: str, stats: dict, created_at: str) -> None:
        sql = """
        INSERT INTO reports (report_date, path, markdown, stats_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(report_date) DO UPDATE SET
            path = excluded.path,
            markdown = excluded.markdown,
            stats_json = excluded.stats_json,
            created_at = excluded.created_at
        """
        with self.conn:
            self.conn.execute(
                sql,
                (
                    report_date.isoformat(),
                    str(path),
                    markdown,
                    json.dumps(stats, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
