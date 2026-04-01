from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.models import Paper
from sciencemonitor.pipeline import ScienceMonitor


class FakeCrossrefClient:
    def fetch_recent_works(self, source, since_date, until_date, max_rows=20):
        if source.id != "jgr_space_physics":
            return []
        return [
            Paper(
                fingerprint="seed",
                source_id=source.id,
                source_name=source.journal_title,
                journal_title=source.journal_title,
                title="Ionosphere Response to Solar Wind Forcing",
                abstract="This study examines ionosphere variability and thermosphere density after solar wind forcing.",
                published_date=date(2026, 3, 14),
                doi="10.1000/pipeline",
                url="https://example.org/pipeline",
                authors=["A Author"],
                tier=source.tier,
                mode=source.mode,
            )
        ]


class FilteredCrossrefClient:
    def fetch_recent_works(self, source, since_date, until_date, max_rows=20):
        if source.id != "jgr_space_physics":
            return []
        return [
            Paper(
                fingerprint="issue",
                source_id=source.id,
                source_name=source.journal_title,
                journal_title=source.journal_title,
                title="Issue Information",
                abstract="",
                published_date=date(2026, 3, 14),
                doi="10.1000/issue",
                url="https://example.org/issue",
                authors=["A Author"],
                tier=source.tier,
                mode=source.mode,
            ),
            Paper(
                fingerprint="real",
                source_id=source.id,
                source_name=source.journal_title,
                journal_title=source.journal_title,
                title="Ionosphere Response to Solar Wind Forcing",
                abstract="This study examines ionosphere variability and thermosphere density after solar wind forcing.",
                published_date=date(2026, 3, 14),
                doi="10.1000/real",
                url="https://example.org/real",
                authors=["A Author"],
                tier=source.tier,
                mode=source.mode,
            ),
        ]


class PipelineTest(unittest.TestCase):
    def test_run_daily_generates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "doc" / "harness_control" / "templates").mkdir(parents=True)
            (root / "config" / "sources.json").write_text(
                ROOT.joinpath("config", "sources.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "topics.json").write_text(
                ROOT.joinpath("config", "topics.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                ROOT.joinpath("config", "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "doc" / "harness_control" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("doc", "harness_control", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            monitor = ScienceMonitor(root=root, crossref_client=FakeCrossrefClient())
            try:
                update_result, report_path, stats = monitor.run_daily(
                    report_date=date(2026, 3, 14),
                    days_back=1,
                    max_per_source=5,
                    source_ids={"jgr_space_physics"},
                )
            finally:
                monitor.close()

            self.assertEqual(update_result.kept_count, 1)
            self.assertEqual(stats["paper_count"], 1)
            self.assertTrue(report_path.exists())
            self.assertIn("电离层", report_path.read_text(encoding="utf-8"))
            summary_files = list((root / "out" / "auto" / "article_summaries").glob("*.md"))
            self.assertEqual(len(summary_files), 1)
            summary_text = summary_files[0].read_text(encoding="utf-8")
        self.assertIn("[[research_reports/2026-03-14 周报|2026-03-14 周报]]", summary_text)

    def test_update_drops_non_research_front_matter_from_full_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "doc" / "harness_control" / "templates").mkdir(parents=True)
            (root / "config" / "sources.json").write_text(
                ROOT.joinpath("config", "sources.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "topics.json").write_text(
                ROOT.joinpath("config", "topics.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                ROOT.joinpath("config", "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "doc" / "harness_control" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("doc", "harness_control", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            monitor = ScienceMonitor(root=root, crossref_client=FilteredCrossrefClient())
            try:
                result = monitor.update(
                    report_date=date(2026, 3, 14),
                    days_back=1,
                    max_per_source=5,
                    source_ids={"jgr_space_physics"},
                )
                rows = monitor.storage.get_recent_papers(date(2026, 3, 14), date(2026, 3, 14))
            finally:
                monitor.close()

            self.assertEqual(result.kept_count, 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Ionosphere Response to Solar Wind Forcing")

    def test_run_daily_skips_report_when_weekly_report_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "doc" / "harness_control" / "templates").mkdir(parents=True)
            (root / "config" / "sources.json").write_text(
                ROOT.joinpath("config", "sources.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "topics.json").write_text(
                ROOT.joinpath("config", "topics.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                ROOT.joinpath("config", "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "runtime.json").write_text(
                '{"features":{"weekly_report_enabled":false},"cli_defaults":{},"deep_read":{"search_full_text_when_pdf_missing":true,"pdf_page_limit":40}}\n',
                encoding="utf-8",
            )
            (root / "doc" / "harness_control" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("doc", "harness_control", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            monitor = ScienceMonitor(root=root, crossref_client=FakeCrossrefClient())
            try:
                update_result, report_path, stats = monitor.run_daily(
                    report_date=date(2026, 3, 14),
                    days_back=1,
                    max_per_source=5,
                    source_ids={"jgr_space_physics"},
                )
            finally:
                monitor.close()

            self.assertEqual(update_result.kept_count, 1)
            self.assertIsNone(report_path)
            self.assertEqual(stats["paper_count"], 0)
            summary_files = list((root / "out" / "auto" / "article_summaries").glob("*.md"))
            self.assertEqual(len(summary_files), 1)


if __name__ == "__main__":
    unittest.main()
