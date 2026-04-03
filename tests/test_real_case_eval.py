from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.article_fetch import SummarySourceMaterial
from sciencemonitor.deep_reads import DeepReadResult
from sciencemonitor.llm import ArticleAnalysis, ReportAnalysis
from sciencemonitor.real_case_eval import run_real_case_eval, run_real_case_fixture_eval


def _write_minimal_real_case_project(root: pathlib.Path, *, include_report_template: bool = False) -> None:
    (root / "config" / "templates").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(exist_ok=True)
    (root / "evals" / "real_cases").mkdir(parents=True, exist_ok=True)
    (root / "config" / "templates" / "article_summary_template.md").write_text(
        (ROOT / "config" / "templates" / "article_summary_template.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    if include_report_template:
        (root / "config" / "templates" / "daily_report_template.md").write_text(
            (ROOT / "config" / "templates" / "daily_report_template.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (root / "config" / "focus_tags.json").write_text(
        (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "evals" / "real_cases" / "cases.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "example_case",
                        "title": "Example Paper",
                        "journal": "JGR: Space Physics",
                        "doi": "10.1000/example",
                        "url": "https://example.org/paper",
                        "asset_pdf": "assets/example.pdf",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _summary_source(source_kind: str = "crossref_abstract", *, abstract_only: bool = True) -> SummarySourceMaterial:
    return SummarySourceMaterial(
        doi="10.1000/example",
        title="Example Paper",
        journal="JGR: Space Physics",
        url="https://example.org/paper",
        authors=["A Author"],
        published_date="2026-03-14",
        abstract="This paper studies TEC variability during a storm.",
        summary_text="This paper studies TEC variability during a storm.",
        source_kind=source_kind,
        abstract_only=abstract_only,
        pdf_urls=[],
    )


def _article_analysis(tags: list[str] | None = None) -> ArticleAnalysis:
    return ArticleAnalysis(
        chinese_title="示例论文中文总结",
        tags=tags or ["电离层/TEC", "信息来源/仅摘要"],
        body="这篇文章基于摘要信息讨论了 TEC 变化。",
        supplement="需要后续结合全文继续核对。",
        recommendation="建议后续补全文。",
        one_sentence="文章围绕 TEC 变化展开。",
    )


class RealCaseEvalTest(unittest.TestCase):
    def test_run_real_case_fixture_eval_updates_and_matches_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_real_case_project(root)

            with mock.patch(
                "sciencemonitor.article_summaries.resolve_summary_source_material",
                return_value=_summary_source(),
            ), mock.patch(
                "sciencemonitor.llm.AnalysisEngine.analyze_article",
                return_value=_article_analysis(),
            ), mock.patch(
                "sciencemonitor.llm.AnalysisEngine.analyze_report",
                return_value=ReportAnalysis(),
            ):
                results, checks = run_real_case_fixture_eval(root=root, update=True)
                self.assertEqual(len(results), 1)
                self.assertTrue(all(item.passed for item in results))
                self.assertTrue(checks)
                self.assertTrue(all(item.updated for item in checks))

                results, checks = run_real_case_fixture_eval(root=root)
                self.assertEqual(len(results), 1)
                self.assertTrue(all(item.passed for item in results))
                self.assertTrue(checks)
                self.assertTrue(all(item.passed for item in checks))
                self.assertTrue(all(not item.updated for item in checks))

    def test_run_real_case_fixture_eval_reports_missing_fixture_without_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_real_case_project(root)

            with mock.patch(
                "sciencemonitor.article_summaries.resolve_summary_source_material",
                return_value=_summary_source(),
            ), mock.patch(
                "sciencemonitor.llm.AnalysisEngine.analyze_article",
                return_value=_article_analysis(),
            ), mock.patch(
                "sciencemonitor.llm.AnalysisEngine.analyze_report",
                return_value=ReportAnalysis(),
            ):
                results, checks = run_real_case_fixture_eval(root=root)
                self.assertEqual(len(results), 1)
                self.assertTrue(all(item.passed for item in results))
                self.assertTrue(checks)
                self.assertTrue(any(not item.passed and item.message == "missing fixture" for item in checks))

    def test_run_real_case_eval_generates_summary_and_metadata_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config" / "templates").mkdir(parents=True, exist_ok=True)
            (root / "config").mkdir(exist_ok=True)
            (root / "evals" / "real_cases").mkdir(parents=True, exist_ok=True)
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                (ROOT / "config" / "templates" / "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "evals" / "real_cases" / "cases.json").write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "example_case",
                                "title": "Example Paper",
                                "journal": "JGR: Space Physics",
                                "doi": "10.1000/example",
                                "url": "https://example.org/paper",
                                "asset_pdf": "assets/example.pdf",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch(
                "sciencemonitor.article_summaries.resolve_summary_source_material",
                return_value=SummarySourceMaterial(
                    doi="10.1000/example",
                    title="Example Paper",
                    journal="JGR: Space Physics",
                    url="https://example.org/paper",
                    authors=["A Author"],
                    published_date="2026-03-14",
                    abstract="This paper studies TEC variability during a storm.",
                    summary_text="This paper studies TEC variability during a storm.",
                    source_kind="crossref_abstract",
                    abstract_only=True,
                    pdf_urls=[],
                ),
            ), mock.patch(
                "sciencemonitor.llm.AnalysisEngine.analyze_article",
                return_value=ArticleAnalysis(
                    chinese_title="示例论文中文总结",
                    tags=["电离层/TEC", "信息来源/仅摘要"],
                    body="这篇文章基于摘要信息讨论了 TEC 变化。",
                    supplement="需要后续结合全文继续核对。",
                    recommendation="建议后续补全文。",
                    one_sentence="文章围绕 TEC 变化展开。",
                ),
            ), mock.patch(
                "sciencemonitor.llm.AnalysisEngine.analyze_report",
                return_value=ReportAnalysis(),
            ):
                results = run_real_case_eval(root=root)
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0].passed)
                self.assertTrue(results[0].abstract_only)
                self.assertIsNotNone(results[0].summary_path)
                self.assertTrue(results[0].summary_path.exists())
                self.assertIsNone(results[0].report_path)
                self.assertIsNotNone(results[0].metadata_path)
                payload = json.loads(results[0].metadata_path.read_text(encoding="utf-8"))
                self.assertTrue(payload["abstract_only"])
                self.assertEqual(payload["summary_source_kind"], "crossref_abstract")
                self.assertFalse(payload["report_generated"])

    def test_run_real_case_eval_can_generate_report_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config" / "templates").mkdir(parents=True, exist_ok=True)
            (root / "config").mkdir(exist_ok=True)
            (root / "evals" / "real_cases").mkdir(parents=True, exist_ok=True)
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                (ROOT / "config" / "templates" / "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(
                (ROOT / "config" / "templates" / "daily_report_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "evals" / "real_cases" / "cases.json").write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "example_case",
                                "title": "Example Paper",
                                "journal": "JGR: Space Physics",
                                "doi": "10.1000/example",
                                "url": "https://example.org/paper",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch(
                "sciencemonitor.article_summaries.resolve_summary_source_material",
                return_value=SummarySourceMaterial(
                    doi="10.1000/example",
                    title="Example Paper",
                    journal="JGR: Space Physics",
                    url="https://example.org/paper",
                    authors=["A Author"],
                    published_date="2026-03-14",
                    abstract="This paper studies TEC variability during a storm.",
                    summary_text="This paper studies TEC variability during a storm.",
                    source_kind="crossref_abstract",
                    abstract_only=True,
                    pdf_urls=[],
                ),
            ), mock.patch(
                "sciencemonitor.llm.AnalysisEngine.analyze_article",
                return_value=ArticleAnalysis(
                    chinese_title="示例论文中文总结",
                    tags=["电离层/TEC", "信息来源/仅摘要"],
                    body="这篇文章基于摘要信息讨论了 TEC 变化。",
                    supplement="需要后续结合全文继续核对。",
                    recommendation="建议后续补全文。",
                    one_sentence="文章围绕 TEC 变化展开。",
                ),
            ), mock.patch(
                "sciencemonitor.llm.AnalysisEngine.analyze_report",
                return_value=ReportAnalysis(
                    overview_bullets=["今天有一篇与 TEC 变化相关的论文。"],
                    daily_suggestions=["优先补全文后再做深入判断。"],
                    topic_insights=[],
                    journal_insights=[],
                ),
            ):
                results = run_real_case_eval(root=root, include_report=True)
                self.assertEqual(len(results), 1)
                self.assertIsNotNone(results[0].report_path)
                self.assertTrue(results[0].report_path.exists())
                payload = json.loads(results[0].metadata_path.read_text(encoding="utf-8"))
                self.assertTrue(payload["report_generated"])

    def test_run_real_case_eval_can_generate_repo_local_deep_read_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config" / "templates").mkdir(parents=True, exist_ok=True)
            (root / "config").mkdir(exist_ok=True)
            (root / "evals" / "real_cases").mkdir(parents=True, exist_ok=True)
            (root / "config" / "templates" / "article_summary_template.md").write_text(
                (ROOT / "config" / "templates" / "article_summary_template.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "evals" / "real_cases" / "cases.json").write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "example_case",
                                "title": "Example Paper",
                                "journal": "JGR: Space Physics",
                                "doi": "10.1000/example",
                                "url": "https://example.org/paper",
                                "asset_pdf": "assets/example.pdf",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            asset_dir = root / "evals" / "real_cases" / "assets"
            asset_dir.mkdir(parents=True, exist_ok=True)
            (asset_dir / "example.pdf").write_bytes(b"%PDF-1.4")

            def fake_run_deep_read(**kwargs):
                output_dir = kwargs["output_dir_override"]
                pdf_dir = kwargs["pdf_dir_override"]
                output_dir.mkdir(parents=True, exist_ok=True)
                pdf_dir.mkdir(parents=True, exist_ok=True)
                note_path = output_dir / "deep_read.md"
                pdf_path = pdf_dir / "example.pdf"
                note_path.write_text("# deep read", encoding="utf-8")
                pdf_path.write_bytes(b"%PDF-1.4")
                self.assertFalse(kwargs["sync_library"])
                return DeepReadResult(
                    success=True,
                    message="ok",
                    output_path=note_path,
                    pdf_output_path=pdf_path,
                    source_kind="local_pdf_full_text",
                )

            with mock.patch(
                "sciencemonitor.article_summaries.resolve_summary_source_material",
                return_value=SummarySourceMaterial(
                    doi="10.1000/example",
                    title="Example Paper",
                    journal="JGR: Space Physics",
                    url="https://example.org/paper",
                    authors=["A Author"],
                    published_date="2026-03-14",
                    abstract="This paper studies TEC variability during a storm.",
                    summary_text="This paper studies TEC variability during a storm.",
                    source_kind="local_pdf_full_text",
                    abstract_only=False,
                    pdf_urls=[],
                ),
            ), mock.patch(
                "sciencemonitor.llm.AnalysisEngine.analyze_article",
                return_value=ArticleAnalysis(
                    chinese_title="示例论文中文总结",
                    tags=["电离层/TEC"],
                    body="这篇文章基于全文讨论了 TEC 变化。",
                    supplement="需要后续结合图表继续核对。",
                    recommendation="可以继续做深读。",
                    one_sentence="文章围绕 TEC 变化展开。",
                ),
            ), mock.patch(
                "sciencemonitor.real_case_eval.run_deep_read",
                side_effect=fake_run_deep_read,
            ):
                results = run_real_case_eval(root=root, include_deep_read=True)
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0].passed)
                self.assertIsNotNone(results[0].deep_read_path)
                self.assertTrue(results[0].deep_read_path.exists())
                self.assertIn("/log/real_case_eval/example_case/deep_reads/", str(results[0].deep_read_path))
                self.assertIsNotNone(results[0].deep_read_pdf_path)
                self.assertTrue(results[0].deep_read_pdf_path.exists())
                payload = json.loads(results[0].metadata_path.read_text(encoding="utf-8"))
                self.assertTrue(payload["deep_read_generated"])
                self.assertIn("/log/real_case_eval/example_case/deep_reads/", payload["deep_read_output_path"])
                self.assertEqual(payload["deep_read_source_kind"], "local_pdf_full_text")


if __name__ == "__main__":
    unittest.main()
