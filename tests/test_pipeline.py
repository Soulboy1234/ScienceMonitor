from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.models import Paper
from sciencemonitor.pipeline import ScienceMonitor
from sciencemonitor.article_fetch import SummarySourceMaterial
from sciencemonitor.llm import AnalysisProviderInvalidOutput, AnalysisProviderTimeout, ArticleAnalysis, ReportAnalysis


def _stable_summary_material(*args, **kwargs) -> SummarySourceMaterial:
    title = kwargs.get("title", "") or "Example Paper"
    journal = kwargs.get("journal", "") or "JGR: Space Physics"
    url = kwargs.get("url", "") or "https://example.org/paper"
    doi = kwargs.get("doi", "") or "10.1000/example"
    abstract = kwargs.get("abstract", "") or "This paper studies ionosphere TEC variability."
    published_date = kwargs.get("published_date", "") or "2026-03-14"
    authors = list(kwargs.get("authors", []) or ["A Author"])
    return SummarySourceMaterial(
        doi=doi,
        title=title,
        journal=journal,
        url=url,
        authors=authors,
        published_date=published_date,
        abstract=abstract,
        summary_text=abstract,
        source_kind="stored_abstract",
        abstract_only=False,
        pdf_urls=[],
    )


def _fake_article_analysis(*args, **kwargs) -> ArticleAnalysis:
    return ArticleAnalysis(
        chinese_title="电离层背景下TEC特征研究",
        tags=["电离层/TEC", "热层/密度"],
        body="这篇文章基于摘要信息讨论了电离层 TEC 与热层密度变化。",
        supplement="需要后续结合全文继续核对方法和结论。",
        recommendation="建议优先细读摘要与数据来源。",
        one_sentence="文章围绕电离层 TEC 与热层密度变化展开。",
    )


def _fake_report_analysis(*args, **kwargs) -> ReportAnalysis:
    return ReportAnalysis(
        overview_bullets=["今天的论文集中在电离层 TEC 和热层密度。"],
        daily_suggestions=["优先关注和磁暴响应相关的论文。"],
        topic_insights=[],
        journal_insights=[],
    )


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
                fingerprint="reviewers",
                source_id=source.id,
                source_name=source.journal_title,
                journal_title=source.journal_title,
                title="Thank You to Our Peer Reviewers in 2025",
                abstract="",
                published_date=date(2026, 3, 14),
                doi="10.1000/reviewers",
                url="https://example.org/reviewers",
                authors=["A Author"],
                tier=source.tier,
                mode=source.mode,
            ),
            Paper(
                fingerprint="editorial",
                source_id=source.id,
                source_name=source.journal_title,
                journal_title=source.journal_title,
                title="Editorial Note",
                abstract="",
                published_date=date(2026, 3, 14),
                doi="10.1000/editorial",
                url="https://example.org/editorial",
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


class TwoPaperCrossrefClient:
    def fetch_recent_works(self, source, since_date, until_date, max_rows=20):
        if source.id != "jgr_space_physics":
            return []
        return [
            Paper(
                fingerprint="summary-ok",
                source_id=source.id,
                source_name=source.journal_title,
                journal_title=source.journal_title,
                title="Ionosphere Response to Solar Wind Forcing",
                abstract="This study examines ionosphere variability after solar wind forcing.",
                published_date=date(2026, 3, 14),
                doi="10.1000/summary-ok",
                url="https://example.org/summary-ok",
                authors=["A Author"],
                tier=source.tier,
                mode=source.mode,
            ),
            Paper(
                fingerprint="summary-timeout",
                source_id=source.id,
                source_name=source.journal_title,
                journal_title=source.journal_title,
                title="Ionosphere Response to the October 2024 G4 Geomagnetic Storm",
                abstract="This study examines the ionosphere response to a geomagnetic storm.",
                published_date=date(2026, 3, 14),
                doi="10.1000/summary-timeout",
                url="https://example.org/summary-timeout",
                authors=["B Author"],
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
            (root / "config" / "templates").mkdir(parents=True)
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
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("config", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(
                ROOT.joinpath("config", "templates", "daily_report_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            monitor = ScienceMonitor(root=root, crossref_client=FakeCrossrefClient())
            try:
                with mock.patch("sciencemonitor.pipeline.resolve_summary_source_material", side_effect=_stable_summary_material), mock.patch(
                    "sciencemonitor.article_summaries.resolve_summary_source_material",
                    side_effect=_stable_summary_material,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_article",
                    side_effect=_fake_article_analysis,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_report",
                    side_effect=_fake_report_analysis,
                ):
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

    def test_run_daily_skips_ollama_article_timeout_and_lists_in_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "templates").mkdir(parents=True)
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
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("config", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(
                ROOT.joinpath("config", "templates", "daily_report_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            def article_analysis(row, index=0):
                if "October 2024 G4" in str(row["title"]):
                    raise AnalysisProviderTimeout(
                        "ollama_api",
                        timeout_seconds=900,
                        request_name="article_timeout",
                    )
                return _fake_article_analysis(row=row, index=index)

            monitor = ScienceMonitor(root=root, crossref_client=TwoPaperCrossrefClient())
            progress_events: list[dict] = []
            try:
                with mock.patch("sciencemonitor.pipeline.resolve_summary_source_material", side_effect=_stable_summary_material), mock.patch(
                    "sciencemonitor.article_summaries.resolve_summary_source_material",
                    side_effect=_stable_summary_material,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_article",
                    side_effect=article_analysis,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_report",
                    side_effect=_fake_report_analysis,
                ):
                    update_result, report_path, stats = monitor.run_daily(
                        report_date=date(2026, 3, 14),
                        days_back=1,
                        max_per_source=5,
                        source_ids={"jgr_space_physics"},
                        progress_callback=progress_events.append,
                    )
            finally:
                monitor.close()

            markdown = report_path.read_text(encoding="utf-8")
            summary_files = list((root / "out" / "auto" / "article_summaries").glob("*.md"))

        self.assertEqual(update_result.kept_count, 2)
        self.assertEqual(stats["summarized_count"], 1)
        self.assertEqual(stats["skipped_summary_count"], 1)
        self.assertEqual(len(summary_files), 1)
        self.assertIn("### 未完成或未获取摘要/全文的文献", markdown)
        self.assertIn("#### 未完成单篇总结的文献", markdown)
        self.assertIn("10.1000/summary-timeout", markdown)
        self.assertTrue(any(int(item.get("summary_skipped", 0) or 0) == 1 for item in progress_events))

    def test_run_daily_skips_ollama_invalid_json_and_lists_in_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "templates").mkdir(parents=True)
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
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("config", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(
                ROOT.joinpath("config", "templates", "daily_report_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            def article_analysis(row, index=0):
                if "October 2024 G4" in str(row["title"]):
                    raise AnalysisProviderInvalidOutput(
                        "ollama_api",
                        request_name="article_invalid_json",
                        detail="Unterminated string starting at: line 2 column 539 (char 585)",
                    )
                return _fake_article_analysis(row=row, index=index)

            monitor = ScienceMonitor(root=root, crossref_client=TwoPaperCrossrefClient())
            progress_events: list[dict] = []
            try:
                with mock.patch("sciencemonitor.pipeline.resolve_summary_source_material", side_effect=_stable_summary_material), mock.patch(
                    "sciencemonitor.article_summaries.resolve_summary_source_material",
                    side_effect=_stable_summary_material,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_article",
                    side_effect=article_analysis,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_report",
                    side_effect=_fake_report_analysis,
                ):
                    update_result, report_path, stats = monitor.run_daily(
                        report_date=date(2026, 3, 14),
                        days_back=1,
                        max_per_source=5,
                        source_ids={"jgr_space_physics"},
                        progress_callback=progress_events.append,
                    )
            finally:
                monitor.close()

            markdown = report_path.read_text(encoding="utf-8")
            summary_files = list((root / "out" / "auto" / "article_summaries").glob("*.md"))

        self.assertEqual(update_result.kept_count, 2)
        self.assertEqual(stats["summarized_count"], 1)
        self.assertEqual(stats["skipped_summary_count"], 1)
        self.assertEqual(len(summary_files), 1)
        self.assertIn("### 未完成或未获取摘要/全文的文献", markdown)
        self.assertIn("Ollama 本地模型返回的结构化 JSON 不完整或格式错误", markdown)
        self.assertIn("10.1000/summary-timeout", markdown)
        self.assertTrue(any(int(item.get("summary_skipped", 0) or 0) == 1 for item in progress_events))

    def test_update_drops_non_research_front_matter_from_full_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "templates").mkdir(parents=True)
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
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("config", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(
                ROOT.joinpath("config", "templates", "daily_report_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            monitor = ScienceMonitor(root=root, crossref_client=FilteredCrossrefClient())
            try:
                with mock.patch("sciencemonitor.pipeline.resolve_summary_source_material", side_effect=_stable_summary_material):
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

    def test_run_daily_emits_progress_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "templates").mkdir(parents=True)
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
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("config", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(
                ROOT.joinpath("config", "templates", "daily_report_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            monitor = ScienceMonitor(root=root, crossref_client=FakeCrossrefClient())
            progress_events: list[dict] = []
            try:
                with mock.patch("sciencemonitor.pipeline.resolve_summary_source_material", side_effect=_stable_summary_material), mock.patch(
                    "sciencemonitor.article_summaries.resolve_summary_source_material",
                    side_effect=_stable_summary_material,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_article",
                    side_effect=_fake_article_analysis,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_report",
                    side_effect=_fake_report_analysis,
                ):
                    monitor.run_daily(
                        report_date=date(2026, 3, 14),
                        days_back=1,
                        max_per_source=5,
                        source_ids={"jgr_space_physics"},
                        progress_callback=progress_events.append,
                    )
            finally:
                monitor.close()

        stages = [str(item.get("stage", "")) for item in progress_events]
        self.assertIn("starting", stages)
        self.assertIn("fetching", stages)
        self.assertIn("building_report", stages)
        self.assertIn("summary_generation", stages)
        self.assertIn("done", stages)
        summary_events = [item for item in progress_events if item.get("stage") == "summary_generation"]
        self.assertTrue(summary_events)
        self.assertTrue(any(int(item.get("summary_total", 0) or 0) >= 1 for item in summary_events))
        self.assertTrue(any(str(item.get("summary_provider", "") or "") == "codex_local" for item in summary_events))

    def test_run_daily_still_generates_report_when_runtime_weekly_switch_is_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "templates").mkdir(parents=True)
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
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("config", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(
                ROOT.joinpath("config", "templates", "daily_report_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            monitor = ScienceMonitor(root=root, crossref_client=FakeCrossrefClient())
            try:
                with mock.patch("sciencemonitor.pipeline.resolve_summary_source_material", side_effect=_stable_summary_material), mock.patch(
                    "sciencemonitor.article_summaries.resolve_summary_source_material",
                    side_effect=_stable_summary_material,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_article",
                    side_effect=_fake_article_analysis,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_report",
                    side_effect=_fake_report_analysis,
                ):
                    update_result, report_path, stats = monitor.run_daily(
                        report_date=date(2026, 3, 14),
                        days_back=1,
                        max_per_source=5,
                        source_ids={"jgr_space_physics"},
                    )
            finally:
                monitor.close()

            self.assertEqual(update_result.kept_count, 1)
            self.assertIsNotNone(report_path)
            self.assertEqual(stats["paper_count"], 1)
            summary_files = list((root / "out" / "auto" / "article_summaries").glob("*.md"))
            self.assertEqual(len(summary_files), 1)

    def test_run_daily_falls_back_to_stored_abstract_when_live_fetch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "templates").mkdir(parents=True)
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
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                ROOT.joinpath("config", "templates", "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(
                ROOT.joinpath("config", "templates", "daily_report_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            monitor = ScienceMonitor(root=root, crossref_client=FakeCrossrefClient())
            try:
                with mock.patch("sciencemonitor.pipeline.resolve_summary_source_material", side_effect=_stable_summary_material), mock.patch(
                    "sciencemonitor.article_summaries.resolve_summary_source_material",
                    side_effect=RuntimeError("temporary fetch failure"),
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_article",
                    side_effect=_fake_article_analysis,
                ), mock.patch(
                    "sciencemonitor.llm.AnalysisEngine.analyze_report",
                    side_effect=_fake_report_analysis,
                ):
                    update_result, report_path, stats = monitor.run_daily(
                        report_date=date(2026, 3, 14),
                        days_back=1,
                        max_per_source=5,
                        source_ids={"jgr_space_physics"},
                    )
            finally:
                monitor.close()

            self.assertEqual(update_result.kept_count, 1)
            self.assertIsNotNone(report_path)
            self.assertEqual(stats["paper_count"], 1)
            summary_files = list((root / "out" / "auto" / "article_summaries").glob("*.md"))
            self.assertEqual(len(summary_files), 1)
            summary_text = summary_files[0].read_text(encoding="utf-8")
            self.assertIn("#信息来源/仅摘要", summary_text)


if __name__ == "__main__":
    unittest.main()
