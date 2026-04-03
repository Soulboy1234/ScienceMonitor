from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
import json
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.article_fetch import SummarySourceMaterial
from sciencemonitor.article_summaries import (
    _run_article_summary_review_loop,
    _validate_article_summary_markdown,
    abbreviate_journal_name,
    generate_article_summaries,
    get_focus_tags,
    get_override,
    infer_method,
    infer_tags_from_text,
    sanitize_tags,
    validate_summary_fields,
)
from sciencemonitor.llm import ArticleAnalysis


class ArticleSummariesTest(unittest.TestCase):
    def test_generate_article_summary_file(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Ionosphere Response to a Geomagnetic Storm",
            "abstract": "We investigate TEC and thermosphere changes during a geomagnetic storm using GNSS observations.",
            "published_date": "2026-03-14",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "ionosphere\nthermosphere\ngeomagnetic storm",
        }
        template = ROOT / "config" / "templates" / "article_summary_template.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            paths = generate_article_summaries([row], template, output_dir, require_analysis=False)

            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].name, "Smith 2026 - JGR.SP - 磁暴背景下电离层TEC特征研究.md")
            content = paths[0].read_text(encoding="utf-8")
            self.assertIn("- [DOI](https://doi.org/10.1000/example)", content)
            self.assertIn("#电离层/TEC", content)
            self.assertIn("#磁暴", content)
            self.assertIn("#仪器/GNSS", content)
            self.assertIn("Smith, A., & Chen, B. (2026). Ionosphere response to a geomagnetic storm.", content)
            self.assertIn("- 这篇文章主要关注", content)

    def test_generate_article_summary_marks_abstract_only_when_live_fetch_falls_back(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Ionosphere Response to a Geomagnetic Storm",
            "abstract": "",
            "published_date": "2026-03-14",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "ionosphere\nthermosphere\ngeomagnetic storm",
            "journal_title": "JGR: Space Physics",
        }
        template = ROOT / "config" / "templates" / "article_summary_template.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            with mock.patch(
                "sciencemonitor.article_summaries.resolve_summary_source_material",
                return_value=SummarySourceMaterial(
                    doi="10.1000/example",
                    title="Ionosphere Response to a Geomagnetic Storm",
                    journal="JGR: Space Physics",
                    url="https://example.org",
                    authors=["Alice Smith", "Bob Chen"],
                    published_date="2026-03-14",
                    abstract="This paper studies TEC variability during a storm.",
                    summary_text="This paper studies TEC variability during a storm.",
                    source_kind="crossref_abstract",
                    abstract_only=True,
                    pdf_urls=[],
                ),
            ):
                paths = generate_article_summaries([row], template, output_dir, enable_live_fetch=True, require_analysis=False)

            content = paths[0].read_text(encoding="utf-8")
            self.assertIn("#信息来源/仅摘要", content)
            self.assertIn("当前总结仅基于摘要和元数据生成", content)

    def test_article_summary_review_loop_repairs_generic_body_and_abstract_notice(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Ionosphere Response to a Geomagnetic Storm",
            "abstract": "This paper studies TEC variability during a storm.",
            "published_date": "2026-03-14",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "ionosphere\nthermosphere\ngeomagnetic storm",
            "summary_source_kind": "crossref_abstract",
        }
        template = (ROOT / "config" / "templates" / "article_summary_template.md").read_text(encoding="utf-8")
        markdown = "\n".join(
            [
                "----",
                "- [DOI](https://doi.org/10.1000/example) #电离层/TEC",
                "- _Smith, A., & Chen, B. (2026). Ionosphere response to a geomagnetic storm. JGR: Space Physics. https://doi.org/10.1000/example_",
                "- 文章围绕相关空间物理问题，利用相关数据分析了关键物理量的变化特征。",
                "- 「补充信息」",
                "\t1. 结果片段还需要进一步确认。",
                "- 「文中引用」",
                "\t1. 暂留空。",
                "- 「好句子」",
                "\t1. 暂留空。",
                "- 「关联报告」",
                "\t1. 暂留空。",
                "",
                "----",
                "记录时间戳: 2026-04-03 12:00:00",
                "",
            ]
        )
        reviewed, issues = _run_article_summary_review_loop(
            row,
            template_text=template,
            note_title="Smith 2026 - JGR.SP - 电离层背景下TEC特征研究",
            markdown=markdown,
            root=ROOT,
        )
        self.assertFalse(issues)
        self.assertIn("#信息来源/仅摘要", reviewed)
        self.assertIn("当前总结仅基于摘要和元数据生成", reviewed)
        self.assertNotIn("结果片段", reviewed)
        self.assertNotIn("文章围绕相关空间物理问题", reviewed)

    def test_article_summary_validation_flags_missing_abstract_notice(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Ionosphere Response to a Geomagnetic Storm",
            "abstract": "This paper studies TEC variability during a storm.",
            "published_date": "2026-03-14",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "ionosphere\nthermosphere\ngeomagnetic storm",
            "summary_source_kind": "crossref_abstract",
        }
        markdown = "\n".join(
            [
                "----",
                "- [DOI](https://doi.org/10.1000/example) #电离层/TEC",
                "- _Smith, A., & Chen, B. (2026). Ionosphere response to a geomagnetic storm. JGR: Space Physics. https://doi.org/10.1000/example_",
                "- 这篇文章主要关注电离层 TEC 变化。",
                "- 「补充信息」",
                "\t1. 后续可继续关注相关过程。",
                "- 「文中引用」",
                "\t1. 暂留空。",
                "- 「好句子」",
                "\t1. 暂留空。",
                "- 「关联报告」",
                "\t1. 暂留空。",
                "",
                "----",
                "记录时间戳: 2026-04-03 12:00:00",
                "",
            ]
        )
        issues = _validate_article_summary_markdown(markdown, row=row)
        self.assertIn("摘要级单篇总结缺少“信息来源/仅摘要”标签", issues)
        self.assertIn("摘要级单篇总结缺少摘要来源说明", issues)

    def test_regeneration_reuses_same_filename(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Ionosphere Response to a Geomagnetic Storm",
            "abstract": "We investigate TEC and thermosphere changes during a geomagnetic storm using GNSS observations.",
            "published_date": "2026-03-14",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "ionosphere\nthermosphere\ngeomagnetic storm",
        }
        template = ROOT / "config" / "templates" / "article_summary_template.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            first_paths = generate_article_summaries([row], template, output_dir, require_analysis=False)
            second_paths = generate_article_summaries([row], template, output_dir, require_analysis=False)

            self.assertEqual(first_paths[0], second_paths[0])
            self.assertEqual(len(list(output_dir.glob('*.md'))), 1)

    def test_custom_template_controls_render_order(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Ionosphere Response to a Geomagnetic Storm",
            "abstract": "We investigate TEC and thermosphere changes during a geomagnetic storm using GNSS observations.",
            "published_date": "2026-03-14",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "ionosphere\nthermosphere\ngeomagnetic storm",
        }

        custom_template = "\n".join(
            [
                "----",
                "{{resource_line}}",
                "- {{body}}",
                "- _{{apa_citation}}_",
                "- 「补充信息」",
                "\t1. {{supplement}}",
                "- 「文中引用」",
                "{{references_block}}",
                "- 「好句子」",
                "{{quotes_block}}",
                "- 「关联报告」",
                "{{related_reports_block}}",
                "",
                "----",
                "记录时间戳: {{timestamp_date}} {{timestamp_time}}",
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            template_path = pathlib.Path(tmpdir) / "article_summary_template.md"
            template_path.write_text(custom_template, encoding="utf-8")

            paths = generate_article_summaries([row], template_path, output_dir, require_analysis=False)

            content = paths[0].read_text(encoding="utf-8")
            self.assertLess(content.index("- 这篇文章主要关注"), content.index("- _Smith, A., & Chen, B. (2026)."))

    def test_invalid_template_missing_required_placeholder_fails_fast(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Ionosphere Response to a Geomagnetic Storm",
            "abstract": "We investigate TEC and thermosphere changes during a geomagnetic storm using GNSS observations.",
            "published_date": "2026-03-14",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "ionosphere\nthermosphere\ngeomagnetic storm",
        }

        invalid_template = "\n".join(
            [
                "----",
                "{{resource_line}}",
                "- _{{apa_citation}}_",
                "- 「补充信息」",
                "\t1. {{supplement}}",
                "- 「文中引用」",
                "{{references_block}}",
                "- 「好句子」",
                "{{quotes_block}}",
                "- 「关联报告」",
                "{{related_reports_block}}",
                "",
                "----",
                "记录时间戳: {{timestamp_date}} {{timestamp_time}}",
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            template_path = pathlib.Path(tmpdir) / "article_summary_template.md"
            template_path.write_text(invalid_template, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required placeholders"):
                generate_article_summaries([row], template_path, output_dir)

    def test_generate_article_summary_requires_llm_by_default(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Ionosphere Response to a Geomagnetic Storm",
            "abstract": "We investigate TEC and thermosphere changes during a geomagnetic storm using GNSS observations.",
            "published_date": "2026-03-14",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "ionosphere\nthermosphere\ngeomagnetic storm",
        }
        template = ROOT / "config" / "templates" / "article_summary_template.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            with self.assertRaisesRegex(RuntimeError, "不再支持规则法"):
                generate_article_summaries([row], template, output_dir)

    def test_validate_summary_fields_strips_invalid_tags_and_generic_text(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Storm-Time Thermospheric Mass Density Response",
            "abstract": "We analyze thermospheric mass density and satellite drag during a storm.",
            "published_date": "2026-03-14",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Alice Smith",
            "topic_labels": "热层\n空间天气",
            "relevance_score": 7.5,
            "notes": "thermospheric mass density\ndrag",
        }

        chinese_title, tags, body, supplement, recommendation, one_sentence = validate_summary_fields(
            row,
            "文献内容概括待补充",
            ["#热层", "轨道环境/南大西洋异常区】Oops", ""],
            "文章围绕相关空间物理问题，利用相关数据分析了关键物理量的变化特征。",
            "",
            "这篇文章与当前主题方向相关，适合放入今日重点跟进列表。",
            "文章围绕相关空间物理问题，利用相关数据分析了关键物理量的变化特征。",
        )

        self.assertNotEqual(chinese_title, "文献内容概括待补充")
        self.assertNotIn("Oops", " ".join(tags))
        self.assertTrue(tags)
        self.assertNotIn("文章围绕相关空间物理问题", body)
        self.assertNotIn("适合放入今日重点跟进列表", recommendation)
        self.assertNotIn("文章围绕相关空间物理问题", one_sentence)

    def test_sanitize_tags_prefers_specific_thermosphere_hierarchy(self) -> None:
        tags = sanitize_tags(["热层", "热层/风", "热层/密度", "热层/风"])
        self.assertNotIn("热层", tags)
        self.assertIn("热层/风场", tags)
        self.assertIn("热层/密度", tags)

    def test_infer_tags_from_text_uses_document_style_without_earth_tag(self) -> None:
        tags = infer_tags_from_text(
            "This study investigates Earth's thermospheric NO production and the drag of LEO satellites."
        )
        self.assertIn("热层/密度", tags)
        self.assertNotIn("研究星球/地球", tags)

    def test_infer_tags_from_text_does_not_treat_plain_by_as_imf_component(self) -> None:
        tags = infer_tags_from_text(
            "Improving the extraction ability of thermospheric mass density variations from observational data by deep learning."
        )
        self.assertNotIn("指数/IMF/By", tags)

    def test_sanitize_tags_keeps_only_first_other_planet(self) -> None:
        tags = sanitize_tags(["研究星球/土星", "研究星球/木星", "热层/风"])
        self.assertEqual(tags.count("其他行星/土星"), 1)
        self.assertNotIn("其他行星/木星", tags)

    def test_sanitize_tags_records_open_vocabulary_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            tags = sanitize_tags(["卫星影响", "新的候选标签"], root=root, context="deep_read", record_candidates=True)

            self.assertIn("卫星影响", tags)
            self.assertIn("新的候选标签", tags)
            payload = json.loads((root / "data" / "tag_candidates.json").read_text(encoding="utf-8"))
            self.assertIn("新的候选标签", payload["candidates"])
            self.assertEqual(payload["candidates"]["新的候选标签"]["contexts"]["deep_read"], 1)

    def test_sanitize_tags_maps_summary_drift_back_to_canonical_labels(self) -> None:
        tags = sanitize_tags(
            [
                "热层/质量密度",
                "卫星/阻力",
                "扰动/磁暴",
                "卫星/CHAMP",
                "卫星/GRACE",
                "模型/深度学习",
                "模型/残差网络",
                "赤道/质量密度异常",
                "信息来源/仅摘要",
            ],
            root=ROOT,
        )
        self.assertIn("热层/密度", tags)
        self.assertIn("卫星影响", tags)
        self.assertIn("磁暴", tags)
        self.assertIn("仪器/CHAMP", tags)
        self.assertIn("仪器/GRACE", tags)
        self.assertIn("深度学习", tags)
        self.assertIn("特征/赤道质量密度异常", tags)
        self.assertIn("信息来源/仅摘要", tags)

    def test_get_focus_tags_merges_analysis_tags_with_text_inference(self) -> None:
        row = {
            "title": "Improving the Extraction Ability of Thermospheric Mass Density Variations From Observational Data by Deep Learning",
            "abstract": "The DL model is trained with CHAMP observations and evaluated with GRACE observations.",
            "notes": "",
            "topic_labels": "",
            "doi": "10.1000/example",
            "source_name": "Space Weather",
            "journal_title": "Space Weather",
            "published_date": "2023-07-10",
            "authors": "Wenbo Li",
            "url": "https://example.org",
        }
        analysis = ArticleAnalysis(
            chinese_title="示例",
            tags=["热层", "模型/残差网络", "卫星/CHAMP"],
            body="示例",
            supplement="示例",
            recommendation="示例",
            one_sentence="示例",
        )
        tags = get_focus_tags(row, analysis=analysis, root=ROOT)
        self.assertIn("热层/密度", tags)
        self.assertIn("深度学习", tags)
        self.assertIn("仪器/CHAMP", tags)

    def test_get_focus_tags_adds_event_driver_from_full_text_packet(self) -> None:
        row = {
            "title": "Improving the Extraction Ability of Thermospheric Mass Density Variations From Observational Data by Deep Learning",
            "abstract": "Abstract: The model can discriminate physical processes by simulating Equatorial Mass density Anomaly and geomagnetic storms.",
            "notes": "",
            "topic_labels": "",
            "doi": "10.1000/example",
            "source_name": "Space Weather",
            "journal_title": "Space Weather",
            "published_date": "2023-07-10",
            "authors": "Wenbo Li",
            "url": "https://example.org",
            "summary_source_kind": "local_pdf_full_text",
        }
        analysis = ArticleAnalysis(
            chinese_title="示例",
            tags=["热层/密度", "深度学习", "仪器/CHAMP"],
            body="示例",
            supplement="示例",
            recommendation="示例",
            one_sentence="示例",
        )
        tags = get_focus_tags(row, analysis=analysis, root=ROOT)
        self.assertIn("磁暴", tags)

    def test_validate_summary_fields_rewrites_confusing_full_text_supplement_wording(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "space_weather",
            "source_name": "Space Weather",
            "title": "Improving the Extraction Ability of Thermospheric Mass Density Variations From Observational Data by Deep Learning",
            "abstract": "Abstract: geomagnetic storms are used in the controlled simulation.",
            "published_date": "2023-07-10",
            "doi": "10.1000/example",
            "url": "https://example.org",
            "authors": "Wenbo Li",
            "topic_labels": "",
            "relevance_score": 9.0,
            "notes": "",
            "summary_source_kind": "local_pdf_full_text",
        }

        _, _, _, supplement, _, _ = validate_summary_fields(
            row,
            "示例标题",
            ["热层/密度", "深度学习", "仪器/CHAMP"],
            "示例正文",
            "当前材料虽来自全文整理稿，但所给节选主要覆盖摘要、数据说明、结果片段和结论摘要。文本未给出业务化效果，因此不能外推。",
            "示例建议",
            "示例一句话",
            root=ROOT,
        )
        self.assertIn("程序已读取并缓存全文", supplement)
        self.assertNotIn("结果片段", supplement)

    def test_infer_method_distinguishes_machine_learning_and_empirical_models_from_numerical_simulation(self) -> None:
        row = {
            "title": "Improving thermospheric density estimation by deep learning",
            "abstract": "We train a ResNet model with CHAMP and compare it with HASDM and NRLMSISE-00.",
        }
        methods = infer_method(row)
        self.assertIn("机器学习建模", methods)
        self.assertIn("经验模型对比", methods)
        self.assertNotIn("理论数值模式", methods)

    def test_get_override_can_be_disabled_per_row(self) -> None:
        self.assertIsNotNone(get_override({"doi": "10.1029/2025JA034386"}))
        self.assertIsNone(get_override({"doi": "10.1029/2025JA034386", "disable_special_overrides": True}))

    def test_abbreviate_journal_name_supports_full_jgr_title(self) -> None:
        self.assertEqual(abbreviate_journal_name("Journal of Geophysical Research: Space Physics"), "JGR.SP")


if __name__ == "__main__":
    unittest.main()
