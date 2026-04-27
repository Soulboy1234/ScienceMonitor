from __future__ import annotations

from collections import Counter
import pathlib
import sys
import tempfile
import unittest
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.llm import ReportAnalysis, TopicInsight
from sciencemonitor.reporting import (
    _run_report_review_loop,
    build_report_wordcloud_display_labels,
    build_report,
    build_report_date_range_label,
    cleanup_unused_report_tag_wordclouds,
    collect_report_tag_frequencies,
    format_highlight_block,
    format_topic_section,
    referenced_report_tag_wordcloud_names,
    should_include_report_wordcloud_tag,
    write_report,
)
from sciencemonitor.config import UserPreferenceProfile
from sciencemonitor.llm_contracts import build_report_prompt
from sciencemonitor.models import ArticleSummaryResult
from sciencemonitor.reporting_support import ReportThemeBucket, collect_report_theme_buckets, theme_tags_for_summary, topic_recommendation_buckets


class _FakeAnalysisEngine:
    def __init__(self, preferences: UserPreferenceProfile) -> None:
        self.user_preferences = preferences

    def analyze_report(self, report_date, summaries):
        return None


class _RowLike:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __getitem__(self, key: str) -> object:
        return self._payload[key]


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
    def test_format_highlight_block_uses_obsidian_safe_tags(self) -> None:
        summary = _sample_summary()
        summary = summary.__class__(**{**summary.__dict__, "tags": ["He+波段", "指数/F10.7"]})

        lines = format_highlight_block(1, summary)
        joined = "\n".join(lines)

        self.assertIn("标签： #He＋波段", joined)
        self.assertIn("#He＋波段", joined)
        self.assertIn("#指数/F10．7", joined)
        self.assertNotIn("#He+波段", joined)

    def test_format_highlight_block_builds_specific_report_reason(self) -> None:
        summary = _sample_summary()
        summary = summary.__class__(
            **{
                **summary.__dict__,
                "chinese_title": "准径向IMF与低动压共同作用下的火星感应磁层异常响应",
                "tags": ["对象/其他行星/火星", "对象/太阳风/动压", "仪器/MAVEN", "信息来源/仅摘要"],
                "body": "本文使用MAVEN观测分析准径向IMF与低太阳风动压同时出现时火星感应磁层边界和激波形态的变化，并比较相邻两条轨道的差异。",
                "recommendation": "如果你在跟踪对象/电离层、对象/其他行星/火星，这篇文章值得先看摘要、数据来源和方法部分。",
            }
        )

        lines = format_highlight_block(1, summary)
        joined = "\n".join(lines)

        self.assertIn("围绕“准径向IMF与低动压共同作用下的火星感应磁层异常响应”展开", joined)
        self.assertIn("观测组合、数据来源和关键响应特征", joined)
        self.assertNotIn("如果你在跟踪", joined)

    def test_build_report_contains_sections(self) -> None:
        summary = _sample_summary()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_report_project(root)
            markdown, stats = build_report(date(2026, 3, 14), [summary], root=root, require_analysis=False)
            asset = root / "out" / "research_reports" / "assets" / "2026-03-14 标签词云.png"
            self.assertTrue(asset.exists())

        self.assertIn("## 周报信息", markdown)
        self.assertIn("## 今日概览", markdown)
        self.assertIn("## 文章推荐", markdown)
        self.assertIn("## 各期刊主题汇总", markdown)
        self.assertIn("![[research_reports/assets/2026-03-14 标签词云.png|960]]", markdown)
        self.assertIn("[[auto/article_summaries/sample|A TEC Study]]", markdown)
        self.assertIn("| 期刊 | 新增文章数 |", markdown)
        self.assertEqual(stats["paper_count"], 1)
        self.assertLess(markdown.index("### 建议重点关注的事件或物理过程"), markdown.index("## 文章推荐"))
        self.assertLess(markdown.index("### 对当前工作的可能启发"), markdown.index("## 文章推荐"))
        self.assertLess(markdown.index("![[research_reports/assets/2026-03-14 标签词云.png|960]]"), markdown.index("### 本周重点方向分布"))

    def test_collect_report_tag_frequencies_excludes_management_tags(self) -> None:
        summary = _sample_summary()
        summary = summary.__class__(
            **{
                **summary.__dict__,
                "tags": ["对象/电离层/TEC", "信息来源/仅摘要", "事件/磁暴", "对象/气辉"],
            }
        )
        counter = collect_report_tag_frequencies([summary])

        self.assertEqual(counter["对象/电离层/TEC"], 1)
        self.assertEqual(counter["事件/磁暴"], 1)
        self.assertEqual(counter["对象/气辉"], 1)
        self.assertNotIn("信息来源/仅摘要", counter)

    def test_build_report_wordcloud_display_labels_prefers_leaf_names(self) -> None:
        labels = build_report_wordcloud_display_labels(
            Counter(
                {
                    "对象/磁层/弓激波": 2,
                    "对象/其他行星/火星": 1,
                    "事件/磁暴": 3,
                }
            )
        )
        display_names = {display for display, _, _ in labels}
        self.assertIn("弓激波", display_names)
        self.assertIn("火星", display_names)
        self.assertIn("磁暴", display_names)
        self.assertNotIn("对象/磁层/弓激波", display_names)

    def test_report_wordcloud_excludes_management_and_method_tags(self) -> None:
        self.assertFalse(should_include_report_wordcloud_tag("信息来源/仅摘要"))
        self.assertFalse(should_include_report_wordcloud_tag("方法/统计研究"))
        self.assertFalse(should_include_report_wordcloud_tag("方法/数据分析"))
        self.assertTrue(should_include_report_wordcloud_tag("对象/磁层/弓激波"))

    def test_cleanup_unused_report_tag_wordclouds_keeps_only_referenced_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            reports = root / "out" / "research_reports"
            assets = reports / "assets"
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "config" / "runtime.json").write_text(
                '{"safety": {"allow_output_deletions": true}}\n',
                encoding="utf-8",
            )
            assets.mkdir(parents=True, exist_ok=True)
            keep = assets / "2026-03-14 标签词云.png"
            drop = assets / "2026-03-21 标签词云.png"
            keep.write_bytes(b"keep")
            drop.write_bytes(b"drop")
            (reports / "2026-03-14 周报.md").write_text(
                "## 今日概览\n![[research_reports/assets/2026-03-14 标签词云.png|960]]\n",
                encoding="utf-8",
            )

            self.assertEqual(referenced_report_tag_wordcloud_names(root), {"2026-03-14 标签词云.png"})
            cleanup_unused_report_tag_wordclouds(root)

            self.assertTrue(keep.exists())
            self.assertFalse(drop.exists())

    def test_build_report_date_range_label(self) -> None:
        self.assertEqual(
            build_report_date_range_label(date(2026, 3, 14), 7),
            "统计范围：2026-03-08 至 2026-03-14",
        )

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

        self.assertIn("与当前工作最贴近的内容主要落在", markdown)
        self.assertIn("热层密度", markdown)

    def test_preference_sections_use_llm_analysis_after_supervision(self) -> None:
        base = _sample_summary()
        summary = ArticleSummaryResult(
            row={**dict(base.row), "title": "Thermospheric Density Forecast", "doi": "10.1000/pref-1"},
            analysis=base.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "pref-1.md",
            note_title="Author 2026 - SW - 热层密度短期预报",
            chinese_title="热层密度短期预报",
            tags=["对象/热层/密度", "应用/预测"],
            body="本文研究热层密度短期预报。",
            supplement=base.supplement,
            recommendation=base.recommendation,
            one_sentence="文章围绕热层密度预报展开。",
            rendered_markdown=base.rendered_markdown,
        )
        summary2 = ArticleSummaryResult(
            row={**dict(base.row), "title": "Thermospheric Wind Variability", "doi": "10.1000/pref-3"},
            analysis=base.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "pref-3.md",
            note_title="Author 2026 - JGR.SP - 热层风日际变化",
            chinese_title="热层风日际变化",
            tags=["对象/热层/风场"],
            body="本文研究热层风日际变化。",
            supplement=base.supplement,
            recommendation=base.recommendation,
            one_sentence="文章围绕热层风日际变化展开。",
            rendered_markdown=base.rendered_markdown,
        )
        preferences = UserPreferenceProfile(
            research_focus=["热层密度及其变化机制"],
            priority_alerts=[],
            priority_themes=["热层密度", "热层风", "业务化与预报"],
            theme_keywords={},
        )

        class _PreferenceEngine(_FakeAnalysisEngine):
            def analyze_report(self, report_date, summaries):
                return ReportAnalysis(
                    preference_overview="这批文章与当前工作最直接的重合点在于热层密度预报链路本身，而不是一般性的空间天气背景。",
                    work_implication="可优先借鉴文中对预报变量组织和结果评价方式的处理，再决定是否扩展到你的热层密度问题。",
                    preference_paper_indices=[2],
                    work_implication_paper_indices=[2],
                )

        markdown, _ = build_report(date(2026, 3, 14), [summary, summary2], analysis_engine=_PreferenceEngine(preferences), require_analysis=False)

        self.assertIn("热层密度预报链路本身", markdown)
        self.assertIn("可优先借鉴文中对预报变量组织和结果评价方式的处理", markdown)
        self.assertIn("[[auto/article_summaries/pref-3|Thermospheric Wind Variability]]", markdown)

    def test_preference_sections_reject_low_quality_llm_text(self) -> None:
        summary = _sample_summary()
        summary = ArticleSummaryResult(
            row={**dict(summary.row), "title": "Thermospheric Density Forecast", "doi": "10.1000/pref-2"},
            analysis=summary.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "pref-2.md",
            note_title="Author 2026 - SW - 热层密度短期预报",
            chinese_title="热层密度短期预报",
            tags=["对象/热层/密度", "应用/预测"],
            body="本文研究热层密度短期预报。",
            supplement=summary.supplement,
            recommendation=summary.recommendation,
            one_sentence="文章围绕热层密度预报展开。",
            rendered_markdown=summary.rendered_markdown,
        )
        preferences = UserPreferenceProfile(
            research_focus=["热层密度及其变化机制"],
            priority_alerts=[],
            priority_themes=["热层密度", "业务化与预报"],
            theme_keywords={},
        )

        class _BadPreferenceEngine(_FakeAnalysisEngine):
            def analyze_report(self, report_date, summaries):
                return ReportAnalysis(
                    preference_overview="如果你在跟踪热层密度，这篇文章值得先看摘要。",
                    work_implication="建议结合原标题和摘要确认其最核心的结论与方法。",
                    preference_paper_indices=[99],
                    work_implication_paper_indices=[99],
                )

        markdown, _ = build_report(date(2026, 3, 14), [summary], analysis_engine=_BadPreferenceEngine(preferences), require_analysis=False)

        self.assertNotIn("如果你在跟踪热层密度", markdown)
        self.assertNotIn("建议结合原标题和摘要确认", markdown)
        self.assertIn("与当前工作最贴近的内容主要落在", markdown)
        self.assertIn("这批论文对当前工作的启发主要落在", markdown)

    def test_preference_sections_reject_protocol_garbage_from_llm(self) -> None:
        summary = _sample_summary()
        summary = ArticleSummaryResult(
            row={**dict(summary.row), "title": "Thermospheric Density Forecast", "doi": "10.1000/pref-4"},
            analysis=summary.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "pref-4.md",
            note_title="Author 2026 - SW - 热层密度短期预报",
            chinese_title="热层密度短期预报",
            tags=["对象/热层/密度", "应用/预测"],
            body="本文研究热层密度短期预报。",
            supplement=summary.supplement,
            recommendation=summary.recommendation,
            one_sentence="文章围绕热层密度预报展开。",
            rendered_markdown=summary.rendered_markdown,
        )
        preferences = UserPreferenceProfile(
            research_focus=["热层密度及其变化机制"],
            priority_alerts=[],
            priority_themes=["热层密度", "业务化与预报"],
            theme_keywords={},
        )

        class _GarbagePreferenceEngine(_FakeAnalysisEngine):
            def analyze_report(self, report_date, summaries):
                return ReportAnalysis(
                    preference_overview="assistant to=final codex_output_schema { json invalid }",
                    work_implication="##errmsg## Oops need proper final.",
                )

        markdown, _ = build_report(date(2026, 3, 14), [summary], analysis_engine=_GarbagePreferenceEngine(preferences), require_analysis=False)

        self.assertNotIn("assistant to=final", markdown)
        self.assertNotIn("codex_output_schema", markdown)
        self.assertNotIn("##errmsg##", markdown)
        self.assertIn("与当前工作最贴近的内容主要落在", markdown)
        self.assertIn("这批论文对当前工作的启发主要落在", markdown)

    def test_collect_report_theme_buckets_supports_row_like_records_without_get(self) -> None:
        summary = _sample_summary()
        summary = ArticleSummaryResult(
            row=_RowLike(dict(summary.row)),
            analysis=summary.analysis,
            output_path=summary.output_path,
            note_title=summary.note_title,
            chinese_title=summary.chinese_title,
            tags=["对象/电离层/TEC"],
            body=summary.body,
            supplement=summary.supplement,
            recommendation=summary.recommendation,
            one_sentence=summary.one_sentence,
            rendered_markdown=summary.rendered_markdown,
        )

        buckets = collect_report_theme_buckets([summary], min_count=1)

        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0].display, "电离层/TEC")

    def test_theme_recommendations_exclude_methods_and_generic_sun_earth_coupling(self) -> None:
        base = _sample_summary()
        summary_a = ArticleSummaryResult(
            row=dict(base.row),
            analysis=base.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "theme-a.md",
            note_title="Author 2026 - JGR.SP - 电离层TEC在磁暴期间的响应",
            chinese_title="电离层TEC在磁暴期间的响应",
            tags=["方法/数据分析", "对象/日地耦合", "对象/电离层/TEC", "事件/磁暴"],
            body=base.body,
            supplement=base.supplement,
            recommendation=base.recommendation,
            one_sentence=base.one_sentence,
            rendered_markdown=base.rendered_markdown,
        )
        summary_b = ArticleSummaryResult(
            row={**dict(base.row), "doi": "10.1000/example-2", "title": "Another TEC Study"},
            analysis=base.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "theme-b.md",
            note_title="Author 2026 - JGR.SP - 磁暴期间电离层TEC变化统计",
            chinese_title="磁暴期间电离层TEC变化统计",
            tags=["方法/统计研究", "对象/日地耦合", "对象/电离层/TEC", "事件/磁暴"],
            body=base.body,
            supplement=base.supplement,
            recommendation=base.recommendation,
            one_sentence=base.one_sentence,
            rendered_markdown=base.rendered_markdown,
        )

        theme_tags = theme_tags_for_summary(summary_a)
        self.assertIn("对象/电离层/TEC", theme_tags)
        self.assertIn("事件/磁暴", theme_tags)
        self.assertNotIn("方法/数据分析", theme_tags)
        self.assertNotIn("对象/日地耦合", theme_tags)

        topic_buckets = topic_recommendation_buckets([summary_a, summary_b])
        displays = [bucket.display for bucket in topic_buckets]
        self.assertIn("电离层/TEC", displays)
        self.assertIn("磁暴", displays)
        self.assertNotIn("数据分析", displays)
        self.assertNotIn("统计研究", displays)
        self.assertNotIn("日地耦合", displays)

    def test_topic_recommendations_skip_weak_two_paper_broad_object_clusters(self) -> None:
        base = _sample_summary()
        summary_a = ArticleSummaryResult(
            row=dict(base.row),
            analysis=base.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "weak-topic-a.md",
            note_title="Author 2026 - SW - 太阳风参数对外辐射带电子通量预测",
            chinese_title="太阳风参数对外辐射带电子通量预测",
            tags=["对象/高能粒子/电子", "对象/太阳风", "应用/预测"],
            body=base.body,
            supplement=base.supplement,
            recommendation=base.recommendation,
            one_sentence="文章关注太阳风参数对外辐射带电子通量预测能力。",
            rendered_markdown=base.rendered_markdown,
        )
        summary_b = ArticleSummaryResult(
            row={**dict(base.row), "doi": "10.1000/example-3", "title": "Diffusion Rate Study"},
            analysis=base.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "weak-topic-b.md",
            note_title="Author 2026 - JGR.SP - 不同波谱设定对辐射带电子扩散率影响",
            chinese_title="不同波谱设定对辐射带电子扩散率影响",
            tags=["对象/高能粒子/电子", "对象/波粒相互作用/合声波", "模型/辐射带模型"],
            body=base.body,
            supplement=base.supplement,
            recommendation=base.recommendation,
            one_sentence="文章关注不同波谱设定下辐射带电子扩散率的差异。",
            rendered_markdown=base.rendered_markdown,
        )

        topic_buckets = topic_recommendation_buckets([summary_a, summary_b])
        displays = [bucket.display for bucket in topic_buckets]

        self.assertNotIn("高能粒子/电子", displays)

    def test_preference_overview_requires_direct_relevance_not_background_mentions(self) -> None:
        base = _sample_summary()
        direct = ArticleSummaryResult(
            row={**dict(base.row), "doi": "10.1000/example-4", "title": "Thermospheric Density Forecast"},
            analysis=base.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "direct.md",
            note_title="Author 2026 - SW - 热层密度与卫星阻力预报研究",
            chinese_title="热层密度与卫星阻力预报研究",
            tags=["对象/热层/密度", "应用/卫星影响", "应用/预测"],
            body="本文研究热层密度变化及其对卫星阻力预报的作用。",
            supplement=base.supplement,
            recommendation=base.recommendation,
            one_sentence="文章围绕热层密度变化和卫星阻力预报展开。",
            rendered_markdown=base.rendered_markdown,
        )
        background = ArticleSummaryResult(
            row={**dict(base.row), "doi": "10.1000/example-5", "title": "Generalized Eccentric Dipole"},
            analysis=base.analysis,
            output_path=ROOT / "out" / "auto" / "article_summaries" / "background.md",
            note_title="Author 2026 - JGR.SP - 广义偏心偶极地磁坐标系",
            chinese_title="广义偏心偶极地磁坐标系",
            tags=["对象/电离层", "对象/磁层", "对象/地磁"],
            body="本文提出新坐标系，适用于磁层—电离层—热层耦合研究，但未直接展开热层密度或卫星阻力问题。",
            supplement=base.supplement,
            recommendation=base.recommendation,
            one_sentence="文章提出面向MIT耦合研究的新地磁坐标系。",
            rendered_markdown=base.rendered_markdown,
        )
        preferences = UserPreferenceProfile(
            research_focus=["热层密度及其变化机制"],
            priority_alerts=["磁暴、行星际环境变化对卫星阻力和轨道环境的影响"],
            priority_themes=["热层密度", "卫星影响", "业务化与预报"],
            theme_keywords={},
        )

        markdown, _ = build_report(date(2026, 3, 14), [direct, background], analysis_engine=_FakeAnalysisEngine(preferences), require_analysis=False)
        start = markdown.index("### 与当前工作相关的重点")
        end = markdown.index("## 文章推荐", start)
        preference_block = markdown[start:end]

        self.assertIn("[[auto/article_summaries/direct|Thermospheric Density Forecast]]", preference_block)
        self.assertNotIn("[[auto/article_summaries/background|Generalized Eccentric Dipole]]", preference_block)

    def test_topic_section_falls_back_from_generic_llm_summary(self) -> None:
        summary = _sample_summary()
        bucket = ReportThemeBucket(
            tag="事件/太阳耀斑",
            display="太阳耀斑",
            count=2,
            journals=("Solar Physics",),
            summaries=(summary, summary),
        )
        analysis = ReportAnalysis(
            topic_insights=[
                TopicInsight(
                    label="太阳耀斑",
                    summary="该文主要涉及对象/太阳、事件/太阳耀斑，建议结合原标题和摘要确认其最核心的结论与方法。",
                )
            ]
        )
        lines = format_topic_section(
            1,
            bucket,
            report_analysis=analysis,
            preferences=UserPreferenceProfile(research_focus=[], priority_alerts=[], priority_themes=[], theme_keywords={}),
        )
        joined = "\n".join(lines)

        self.assertIn("相关文章分别指出：", joined)
        self.assertNotIn("该文主要涉及", joined)

    def test_build_report_prompt_uses_compact_summary_blocks(self) -> None:
        summary = _sample_summary()
        summary = ArticleSummaryResult(
            row=summary.row,
            analysis=summary.analysis,
            output_path=summary.output_path,
            note_title=summary.note_title,
            chinese_title=summary.chinese_title,
            tags=["对象/电离层/TEC", "对象/热层/密度", "事件/磁暴", "应用/卫星影响"],
            body="A" * 400,
            supplement="这段补充信息不应再直接进入周报 prompt。",
            recommendation=summary.recommendation,
            one_sentence="这是一段核心总结。",
            rendered_markdown=summary.rendered_markdown,
        )

        prompt = build_report_prompt(
            date(2026, 3, 14),
            [summary],
            UserPreferenceProfile(research_focus=[], priority_alerts=[], priority_themes=[], theme_keywords={}),
        )

        self.assertIn("核心信息：这是一段核心总结。", prompt)
        self.assertNotIn("补充信息：", prompt)
        self.assertNotIn("这段补充信息不应再直接进入周报 prompt。", prompt)
        self.assertIn("preference_overview 单独对应“与当前工作相关的重点”", prompt)
        self.assertIn("work_implication 单独对应“对当前工作的可能启发”", prompt)
        self.assertIn("preference_paper_indices 用整数编号返回最能支撑 preference_overview 的论文序号", prompt)

    def test_report_daily_suggestions_are_normalized_to_chinese_terms(self) -> None:
        summary = _sample_summary()

        class _SuggestionEngine(_FakeAnalysisEngine):
            def analyze_report(self, report_date, summaries):
                return ReportAnalysis(
                    daily_suggestions=[
                        "重点关注上游结构对 thermospheric forcing 的前置控制。"
                    ]
                )

        markdown, _ = build_report(
            date(2026, 3, 14),
            [summary],
            analysis_engine=_SuggestionEngine(UserPreferenceProfile(research_focus=[], priority_alerts=[], priority_themes=[], theme_keywords={})),
            require_analysis=False,
        )

        self.assertIn("热层外部强迫", markdown)
        self.assertNotIn("thermospheric forcing", markdown)

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
                    "## 各期刊主题汇总",
                    "{{journal_roundup_block}}",
                    "",
                    "## 周报信息",
                    "{{report_info_block}}",
                    "",
                    "## 今日概览",
                    "### 本周重点方向分布",
                    "{{overview_table_block}}",
                    "",
                    "### 整体观察",
                    "{{objective_overview_block}}",
                    "",
                    "### 与当前工作相关的重点",
                    "{{preference_overview_block}}",
                    "",
                    "## 文章推荐",
                    "### 推荐论文",
                    "{{recommended_papers_block}}",
                    "",
                    "### 建议重点关注的事件或物理过程",
                    "{{recommended_processes_block}}",
                    "",
                    "### 对当前工作的可能启发",
                    "{{work_implications_block}}",
                    "",
                    "## 主题推荐",
                    "{{theme_recommendations_block}}",
                    "",
                    "## 其他",
                    "### 未获取摘要/全文的文献",
                    "{{missing_sources_block}}",
                    "",
                    "### 附注",
                    "- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。",
                    "- 生成时间：{{generated_at}}",
                    "",
                    "----",
                ]
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(custom_template, encoding="utf-8")

            markdown, _ = build_report(date(2026, 3, 14), [_sample_summary()], root=root, require_analysis=False)

        self.assertLess(markdown.index("## 各期刊主题汇总"), markdown.index("## 今日概览"))

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
                    "## 周报信息",
                    "{{report_info_block}}",
                    "",
                    "## 今日概览",
                    "### 本周重点方向分布",
                    "{{overview_table_block}}",
                    "",
                    "### 整体观察",
                    "{{objective_overview_block}}",
                    "",
                    "### 与当前工作相关的重点",
                    "{{preference_overview_block}}",
                    "",
                    "## 文章推荐",
                    "### 推荐论文",
                    "{{recommended_papers_block}}",
                    "",
                    "### 建议重点关注的事件或物理过程",
                    "{{recommended_processes_block}}",
                    "",
                    "### 对当前工作的可能启发",
                    "{{work_implications_block}}",
                    "",
                    "## 主题推荐",
                    "{{theme_recommendations_block}}",
                    "",
                    "## 各期刊主题汇总",
                    "",
                    "## 其他",
                    "### 未获取摘要/全文的文献",
                    "{{missing_sources_block}}",
                    "",
                    "### 附注",
                    "- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。",
                    "- 生成时间：{{generated_at}}",
                    "",
                    "----",
                ]
            )
            (root / "config" / "templates" / "daily_report_template.md").write_text(invalid_template, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required placeholders"):
                build_report(date(2026, 3, 14), [_sample_summary()], root=root, require_analysis=False)

    def test_build_report_lists_missing_source_rows_without_article_links(self) -> None:
        missing_row = {
            "fingerprint": "missing",
            "source_id": "asr",
            "source_name": "Advances in Space Research",
            "journal_title": "Advances in Space Research",
            "title": "Severe geomagnetic storm driven by a slow ICME",
            "abstract": "",
            "published_date": "2026-04-01",
            "doi": "10.1016/j.asr.2026.01.082",
            "url": "https://doi.org/10.1016/j.asr.2026.01.082",
            "authors": "A Author",
            "topics": "solar_terrestrial_coupling",
            "topic_labels": "日地耦合\n空间天气",
            "relevance_score": 6.0,
            "tier": "related",
            "mode": "topic_filter",
            "raw_container_title": "Advances in Space Research",
            "fetched_at": "2026-04-01T00:00:00",
            "notes": "",
        }
        markdown, stats = build_report(
            date(2026, 4, 6),
            [_sample_summary()],
            missing_source_rows=[missing_row],
            require_analysis=False,
        )

        self.assertEqual(stats["paper_count"], 2)
        self.assertEqual(stats["summarized_count"], 1)
        self.assertEqual(stats["missing_source_count"], 1)
        self.assertIn("### 未获取摘要/全文的文献", markdown)
        self.assertIn("10.1016/j.asr.2026.01.082", markdown)
        self.assertIn("Advances in Space Research", markdown)
        self.assertNotIn("[[auto/article_summaries", markdown.split("### 未获取摘要/全文的文献", 1)[1])

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
                "## 周报信息",
                "| 期刊 | 新增文章数 |",
                "| --- | ---: |",
                "| JGR: Space Physics | 1 |",
                "",
                "## 今日概览",
                "### 本周重点方向分布",
                "| 重点方向 | 文章数 | 重点期刊 |",
                "| --- | ---: | --- |",
                "| 电离层/TEC | 1 | JGR: Space Physics |",
                "",
                "### 整体观察",
                "- 概览。",
                "",
                "### 与当前工作相关的重点",
                "- 相关内容。",
                "",
                "## 文章推荐",
                "### 推荐论文",
                "   1. [[auto/article_summaries/sample|A TEC Study]]",
                "",
                "### 建议重点关注的事件或物理过程",
                "- 过程一。",
                "",
                "### 对当前工作的可能启发",
                "- 启发一。",
                "",
                "## 主题推荐",
                "### 主题 1：电离层/TEC",
                "",
                "- 推荐理由：示例。",
                "",
                "## 各期刊主题汇总",
                "### JGR: Space Physics",
                "",
                "- 今日新增文章数：1",
                "",
                "## 其他",
                "### 未获取摘要/全文的文献",
                "- 无。",
                "",
                "### 附注",
                "- 本报告以标题、摘要和元数据为基础生成，后续可结合单篇文献卡片进一步细读。",
                "- 生成时间：2026-03-14T00:00:00 UTC",
                "",
                "----",
                "",
            ]
        )
        reviewed, issues = _run_report_review_loop(markdown)
        self.assertFalse(issues)
        self.assertNotIn("### 主题 1：电离层/TEC\n\n-", reviewed)
        self.assertNotIn("### JGR: Space Physics\n\n-", reviewed)

    def test_write_report_uses_weekly_suffix_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            path = write_report(root, date(2026, 3, 24), "# test\n")

            self.assertEqual(path.name, "2026-03-24 周报.md")
            self.assertTrue((root / "latest.md").exists())


if __name__ == "__main__":
    unittest.main()
