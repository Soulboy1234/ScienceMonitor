from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.article_summaries import (
    generate_article_summaries,
    infer_tags_from_text,
    sanitize_tags,
    validate_summary_fields,
)


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
        template = ROOT / "doc" / "harness_control" / "templates" / "article_summary_template.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            paths = generate_article_summaries([row], template, output_dir)

            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].name, "Smith 2026 - JGR.SP - 磁暴背景下TEC特征研究.md")
            content = paths[0].read_text(encoding="utf-8")
            self.assertIn("- [DOI](https://doi.org/10.1000/example)", content)
            self.assertIn("#磁暴", content)
            self.assertIn("#电离层", content)
            self.assertIn("#GNSS", content)
            self.assertIn("#TEC", content)
            self.assertIn("Smith, A., & Chen, B. (2026). Ionosphere response to a geomagnetic storm.", content)
            self.assertIn("- 这篇文章主要关注", content)

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
        template = ROOT / "doc" / "harness_control" / "templates" / "article_summary_template.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            first_paths = generate_article_summaries([row], template, output_dir)
            second_paths = generate_article_summaries([row], template, output_dir)

            self.assertEqual(first_paths[0], second_paths[0])
            self.assertEqual(len(list(output_dir.glob('*.md'))), 1)

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
        self.assertIn("热层/风", tags)
        self.assertIn("热层/密度", tags)

    def test_infer_tags_from_text_adds_research_body_and_thermosphere_tags(self) -> None:
        tags = infer_tags_from_text(
            "This study investigates Earth's thermospheric NO production and the drag of LEO satellites."
        )
        self.assertIn("研究星球/地球", tags)
        self.assertIn("热层/成分", tags)
        self.assertIn("热层/密度", tags)

    def test_sanitize_tags_keeps_only_first_research_body(self) -> None:
        tags = sanitize_tags(["研究星球/土星", "研究星球/木星", "热层/风"])
        self.assertEqual(tags.count("研究星球/土星"), 1)
        self.assertNotIn("研究星球/木星", tags)


if __name__ == "__main__":
    unittest.main()
