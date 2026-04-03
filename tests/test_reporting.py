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

from sciencemonitor.reporting import _run_report_review_loop, build_report, write_report
from sciencemonitor.article_summaries import ArticleSummaryResult
from sciencemonitor.config import UserPreferenceProfile


class _FakeAnalysisEngine:
    def __init__(self, preferences: UserPreferenceProfile) -> None:
        self.user_preferences = preferences

    def analyze_report(self, report_date, summaries):
        return None


def _sample_summary() -> ArticleSummaryResult:
    row = {
        "fingerprint": "fingerprint",
        "source_id": "source_id",
        "source_name": "JGR: Space Physics",
        "journal_title": "JGR: Space Physics",
        "title": "A TEC Study",
        "abstract": "This paper studies ionosphere TEC variability.",
        "published_date": "2026-03-14",
        "doi": "10.1000/example",
        "url": "https://example.org",
        "authors": "A Author",
        "topics": "ionosphere",
        "topic_labels": "电离层",
        "relevance_score": 5.2,
        "tier": "core",
        "mode": "full",
        "raw_container_title": "JGR: Space Physics",
        "fetched_at": "2026-03-14T00:00:00",
        "notes": "ionosphere",
    }
    return ArticleSummaryResult(
        row=row,
        analysis=None,
        output_path=ROOT / "out" / "auto" / "article_summaries" / "sample.md",
        note_title="Author 2026 - JGR.SP - 电离层背景下TEC特征研究",
        chinese_title="电离层背景下TEC特征研究",
        tags=["电离层/TEC"],
        body="这篇文章主要关注电离层 TEC 变化。",
        supplement="后续可继续关注相关过程。",
        recommendation="建议优先细读。",
        one_sentence="文章围绕电离层变化研究 TEC 特征。",
        rendered_markdown="sample",
    )


def _write_minimal_report_project(root: pathlib.Path) -> None:
    (root / "config" / "templates").mkdir(parents=True, exist_ok=True)
    (root / "config" / "templates" / "daily_report_template.md").write_text(
        ROOT.joinpath("config", "templates", "daily_report_template.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


class ReportingTest(unittest.TestCase):
    def test_build_report_contains_sections(self) -> None:
        summary = _sample_summary()
        markdown, stats = build_report(date(2026, 3, 14), [summary], require_analysis=False)

        self.assertIn("## 今日概览", markdown)
        self.assertIn("### 按期刊汇总", markdown)
        self.assertIn("### 今日最值得关注的论文", markdown)
        self.assertIn("[[auto/article_summaries/sample|A TEC Study]]", markdown)
        self.assertEqual(stats["paper_count"], 1)

    def test_build_report_mentions_master_plan_preferences(self) -> None:
        row = {
            "fingerprint": "drag-paper",
            "source_id": "space_weather",
            "source_name": "Space Weather",
            "journal_title": "Space Weather",
            "title": "Satellite Drag Response During a Geomagnetic Storm",
            "abstract": "This paper studies thermospheric mass density and satellite drag.",
            "published_date": "2026-03-14",
            "doi": "10.1000/drag",
            "url": "https://example.org/drag",
            "authors": "A Author",
            "topics": "thermosphere",
            "topic_labels": "热层\n空间天气",
            "relevance_score": 8.0,
            "tier": "core",
            "mode": "full",
            "raw_container_title": "Space Weather",
            "fetched_at": "2026-03-14T00:00:00",
            "notes": "drag",
        }
        summary = ArticleSummaryResult(
            row=row,
            analysis=None,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "drag.md",
            note_title="Author 2026 - SW - 磁暴期间热层密度与卫星阻力响应",
            chinese_title="磁暴期间热层密度与卫星阻力响应",
            tags=["热层/密度", "卫星影响", "空间天气"],
            body="本文讨论磁暴期间热层质量密度变化及其对卫星阻力环境的影响。",
            supplement="后续可关注低轨卫星阻力业务化建模。",
            recommendation="建议优先关注卫星阻力和热层密度结果。",
            one_sentence="该文聚焦热层密度与卫星阻力响应。",
            rendered_markdown="sample",
        )
        preferences = UserPreferenceProfile(
            research_focus=["热层密度及其变化机制"],
            priority_alerts=["磁暴、行星际环境变化对卫星阻力和轨道环境的影响"],
            priority_themes=["热层密度", "卫星影响"],
            theme_keywords={
                "热层密度": ["热层密度", "thermospheric mass density"],
                "卫星影响": ["卫星", "satellite drag", "drag"],
            },
        )
        markdown, _ = build_report(date(2026, 3, 14), [summary], analysis_engine=_FakeAnalysisEngine(preferences), require_analysis=False)

        self.assertIn("按当前研究偏好", markdown)
        self.assertIn("热层密度", markdown)

    def test_custom_report_template_controls_render_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_report_project(root)
            custom_template = "\n".join(
                [
                    "----",
                    "标题：Space Physics Daily Report - {{report_date}}",
                    "统计窗口：近 {{window_days}} 天",
                    "监控期刊：{{journals}}",
                    "",
                    "### 按期刊汇总",
                    "{{journals_block}}",
                    "",
                    "## 今日概览",
                    "- 今日共监控到 {{paper_count}} 篇新论文，来自 {{journal_count}} 本期刊。",
                    "{{overview_bullets_block}}",
                    "",
                    "## 今日搜索的文献的主要关注点分类",
                    "{{focus_categories_block}}",
                    "",
                    "## 今日建议",
                    "{{daily_suggestions_block}}",
                    "",
                    "### 今日最值得关注的论文",
                    "{{highlights_block}}",
                    "",
                    "### 按主题聚焦",
                    "{{topics_block}}",
                    "",
                    "## 附注",
                    "- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。",
                    "- 生成时间：{{generated_at}}",
                    "",
                    "----",
                ]
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(custom_template, encoding="utf-8")

            markdown, _ = build_report(date(2026, 3, 14), [_sample_summary()], root=root, require_analysis=False)

        self.assertLess(markdown.index("### 按期刊汇总"), markdown.index("## 今日概览"))

    def test_invalid_report_template_missing_placeholder_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_report_project(root)
            invalid_template = "\n".join(
                [
                    "----",
                    "标题：Space Physics Daily Report - {{report_date}}",
                    "统计窗口：近 {{window_days}} 天",
                    "监控期刊：{{journals}}",
                    "",
                    "## 今日概览",
                    "- 今日共监控到 {{paper_count}} 篇新论文，来自 {{journal_count}} 本期刊。",
                    "{{overview_bullets_block}}",
                    "",
                    "## 今日搜索的文献的主要关注点分类",
                    "{{focus_categories_block}}",
                    "",
                    "## 今日建议",
                    "{{daily_suggestions_block}}",
                    "",
                    "### 今日最值得关注的论文",
                    "{{highlights_block}}",
                    "",
                    "### 按主题聚焦",
                    "{{topics_block}}",
                    "",
                    "### 按期刊汇总",
                    "",
                    "## 附注",
                    "- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。",
                    "- 生成时间：{{generated_at}}",
                    "",
                    "----",
                ]
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(invalid_template, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required placeholders"):
                build_report(date(2026, 3, 14), [_sample_summary()], root=root, require_analysis=False)

    def test_build_report_requires_llm_by_default(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "不再支持规则法"):
            build_report(date(2026, 3, 14), [_sample_summary()])

    def test_report_review_loop_collapses_extra_blank_lines(self) -> None:
        markdown = "\n".join(
            [
                "----",
                "标题：Space Physics Daily Report - 2026-03-14",
                "统计窗口：近 7 天",
                "监控期刊：JGR: Space Physics",
                "",
                "## 今日概览",
                "- 今日共监控到 1 篇新论文，来自 1 本期刊。",
                "- 概览。",
                "",
                "## 今日搜索的文献的主要关注点分类",
                "- 电离层：1 篇",
                "",
                "## 今日建议",
                "- 建议一。",
                "",
                "### 今日最值得关注的论文",
                "   1. [[auto/article_summaries/sample|A TEC Study]]",
                "",
                "### 按主题聚焦",
                "#### 主题 1：电离层",
                "",
                "   - 今日这一主题下的代表性论文包括：[[auto/article_summaries/sample|A TEC Study]]。",
                "",
                "### 按期刊汇总",
                "#### JGR: Space Physics",
                "",
                "   - 今日新增：1 篇",
                "",
                "## 附注",
                "- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。",
                "- 生成时间：2026-03-14T00:00:00 UTC",
                "",
                "----",
                "",
            ]
        )
        reviewed, issues = _run_report_review_loop(markdown)
        self.assertFalse(issues)
        self.assertNotIn("#### 主题 1：电离层\n\n   -", reviewed)
        self.assertNotIn("#### JGR: Space Physics\n\n   -", reviewed)

    def test_write_report_uses_weekly_suffix_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            path = write_report(root, date(2026, 3, 24), "# test\n")

            self.assertEqual(path.name, "2026-03-24 周报.md")
            self.assertTrue((root / "latest.md").exists())


if __name__ == "__main__":
    unittest.main()
