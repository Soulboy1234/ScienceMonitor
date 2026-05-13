from __future__ import annotations

import os
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
from sciencemonitor.article_summary_markdown import build_tag_line, extract_summary_tags, index_existing_summary_files
from sciencemonitor.article_summaries import (
    _run_article_summary_review_loop,
    _validate_article_summary_markdown,
    generate_article_summaries,
    load_existing_summary_result,
    render_article_summary,
)
from sciencemonitor.article_summary_meta import abbreviate_journal_name, first_author_label, format_single_author_apa, get_override
from sciencemonitor.article_summary_text import (
    get_focus_tags,
    infer_method,
    infer_rule_based_tags_from_parts,
    infer_tags_from_text,
    sanitize_tags,
    validate_summary_fields,
)
from sciencemonitor.llm import ArticleAnalysis


class ArticleSummariesTest(unittest.TestCase):
    def test_build_tag_line_encodes_obsidian_unsafe_symbols_and_extract_restores_canonical_tags(self) -> None:
        tag_line = build_tag_line(["He+波段", "指数/F10.7", "模式/Research&Ops"])

        self.assertIn("#He＋波段", tag_line)
        self.assertIn("#指数/F10．7", tag_line)
        self.assertIn("#模式/Research＆Ops", tag_line)

        markdown = f"- [DOI](https://doi.org/10.1000/example) {tag_line}"
        self.assertEqual(
            extract_summary_tags(markdown),
            ["He+波段", "指数/F10.7", "模式/Research&Ops"],
        )

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
            self.assertIn("#对象/电离层/TEC", content)
            self.assertIn("#事件/磁暴", content)
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

    def test_generate_article_summary_skips_metadata_only_records(self) -> None:
        row = {
            "fingerprint": "redirect123",
            "source_id": "asr",
            "source_name": "Advances in Space Research",
            "title": "Redirecting",
            "abstract": "",
            "published_date": "2026-04-01",
            "doi": "10.1000/redirect",
            "url": "https://doi.org/10.1000/redirect",
            "authors": "Alice Smith",
            "topic_labels": "电离层\n空间天气",
            "relevance_score": 6.0,
            "notes": "",
            "summary_source_kind": "missing",
        }
        template = ROOT / "config" / "templates" / "article_summary_template.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            paths = generate_article_summaries([row], template, output_dir, require_analysis=False)
            self.assertEqual(paths, [])
            self.assertFalse(list(output_dir.glob("*.md")))

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

    def test_load_existing_summary_result_prefers_disk_tags_over_database_focus_tags(self) -> None:
        row = {
            "fingerprint": "example123",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "Mid-latitude ionospheric disturbance observed by VLF and satellite data",
            "abstract": "We investigate ionospheric disturbance and thermospheric response during a geomagnetic storm.",
            "published_date": "2026-03-14",
            "doi": "10.1000/existing",
            "url": "https://example.org/existing",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "ionosphere\nthermosphere\ngeomagnetic storm",
        }
        template_path = ROOT / "config" / "templates" / "article_summary_template.md"
        template_text = template_path.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "Smith 2026 - JGR.SP - 现有总结.md"
            path.write_text(
                "\n".join(
                    [
                        "----",
                        "- [DOI](https://doi.org/10.1000/existing) #对象/电离层/高纬 #事件/磁暴 #仪器/SABER #信息来源/仅摘要",
                        "- _Smith, A., & Chen, B. (2026). Mid-latitude ionospheric disturbance observed by VLF and satellite data. JGR: Space Physics. https://doi.org/10.1000/existing_",
                        "- 本文研究中高纬电离层扰动与 VLF、SABER 联合观测结果。",
                        "- 「补充信息」",
                        "\t1. 当前总结仅基于摘要和元数据生成，未获得全文；与热层密度和卫星阻力的直接联系未展开。",
                        "- 「文中引用」",
                        "\t1. 暂留空。",
                        "- 「好句子」",
                        "\t1. 暂留空。",
                        "- 「关联报告」",
                        "\t1. 暂留空。",
                        "",
                        "----",
                        "记录时间戳: 2026-04-17 12:00:00",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            existing_files = index_existing_summary_files(output_dir)
            result = load_existing_summary_result(existing_files, row, template_text=template_text, root=ROOT)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertIn("对象/电离层/高纬", result.tags)
            self.assertIn("仪器/SABER", result.tags)
            self.assertNotIn("对象/热层/密度", result.tags)
            self.assertNotIn("应用/卫星影响", result.tags)

    def test_load_existing_summary_result_does_not_infer_density_from_negative_supplement(self) -> None:
        row = {
            "fingerprint": "resseguier123",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "A new orthogonal geomagnetic coordinate system: the generalized eccentric dipole",
            "abstract": "A new geomagnetic coordinate system is proposed for magnetosphere-ionosphere-thermosphere coupling studies.",
            "published_date": "2026-03-14",
            "doi": "10.1000/ged",
            "url": "https://example.org/ged",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "电离层\n热层\n日地耦合",
            "relevance_score": 7.5,
            "notes": "geomagnetic coordinate system\nthermosphere",
        }
        template_path = ROOT / "config" / "templates" / "article_summary_template.md"
        template_text = template_path.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "Resseguier 2026 - JGR.SP - 广义偏心偶极.md"
            path.write_text(
                "\n".join(
                    [
                        "----",
                        "- [DOI](https://doi.org/10.1000/ged) #对象/电离层 #对象/磁层 #对象/地磁 #仪器/CHAMP #模型/GED #信息来源/仅摘要",
                        "- _Smith, A., & Chen, B. (2026). A new orthogonal geomagnetic coordinate system: the generalized eccentric dipole. JGR: Space Physics. https://doi.org/10.1000/ged_",
                        "- 本文研究新的地磁坐标表示问题，提出 GED 坐标系，适用于磁层—电离层—热层耦合系统研究。",
                        "- 「补充信息」",
                        "\t1. 当前总结仅基于摘要和元数据生成，未获得全文；这篇文章更偏基础坐标框架与模型方法，不是直接研究热层密度异常、热层风或卫星应用影响的工作。",
                        "- 「文中引用」",
                        "\t1. 暂留空。",
                        "- 「好句子」",
                        "\t1. 暂留空。",
                        "- 「关联报告」",
                        "\t1. 暂留空。",
                        "",
                        "----",
                        "记录时间戳: 2026-04-22 10:00:00",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            existing_files = index_existing_summary_files(output_dir)
            result = load_existing_summary_result(existing_files, row, template_text=template_text, root=ROOT)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertIn("模型/GED", result.tags)
            self.assertNotIn("对象/热层/密度", result.tags)

    def test_load_existing_summary_result_does_not_reintroduce_planet_alias_tags(self) -> None:
        row = {
            "fingerprint": "hanley123",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "MAVEN observations of the martian magnetospheric response to simultaneous quasi-radial IMF and low dynamic pressure",
            "abstract": "The study examines the Martian induced magnetosphere and ionosphere under quasi-radial IMF and low solar-wind dynamic pressure.",
            "published_date": "2026-03-14",
            "doi": "10.1000/mars",
            "url": "https://example.org/mars",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "其他行星\n火星",
            "relevance_score": 7.5,
            "notes": "mars\nmartian magnetosphere",
        }
        template_path = ROOT / "config" / "templates" / "article_summary_template.md"
        template_text = template_path.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir) / "article_summaries"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "Hanley 2026 - JGR.SP - 火星感应磁层异常响应.md"
            path.write_text(
                "\n".join(
                    [
                        "----",
                        "- [DOI](https://doi.org/10.1000/mars) #对象/电离层 #对象/其他行星/火星 #对象/磁层/弓激波 #对象/重离子 #对象/太阳风/动压 #对象/磁层/感应磁层 #仪器/MAVEN #信息来源/仅摘要",
                        "- _Smith, A., & Chen, B. (2026). MAVEN observations of the martian magnetospheric response to simultaneous quasi-radial IMF and low dynamic pressure. JGR: Space Physics. https://doi.org/10.1000/mars_",
                        "- 本文研究火星感应磁层在准径向 IMF 与低动压条件下的响应。",
                        "- 「补充信息」",
                        "\t1. 当前总结仅基于摘要和元数据生成，未获得全文。",
                        "- 「文中引用」",
                        "\t1. 暂留空。",
                        "- 「好句子」",
                        "\t1. 暂留空。",
                        "- 「关联报告」",
                        "\t1. 暂留空。",
                        "",
                        "----",
                        "记录时间戳: 2026-04-22 10:10:00",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            existing_files = index_existing_summary_files(output_dir)
            result = load_existing_summary_result(existing_files, row, template_text=template_text, root=ROOT)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertIn("对象/其他行星/火星", result.tags)
            self.assertNotIn("其他行星/火星", result.tags)

    def test_render_article_summary_canonicalizes_legacy_planet_alias_tags(self) -> None:
        row = {
            "fingerprint": "saturn123",
            "source_id": "jgr_space_physics",
            "source_name": "JGR: Space Physics",
            "title": "The study of the quasi-periodicity observed on plasma density and magnetic field on Saturn's magnetosphere",
            "abstract": "This study examines Saturn magnetosphere plasma density and magnetic field quasi-periodicity.",
            "published_date": "2026-03-14",
            "doi": "10.1000/saturn",
            "url": "https://example.org/saturn",
            "authors": "Alice Smith\nBob Chen",
            "topic_labels": "其他行星\n土星",
            "relevance_score": 7.5,
            "notes": "saturn magnetosphere",
        }
        template = (ROOT / "config" / "templates" / "article_summary_template.md").read_text(encoding="utf-8")

        markdown = render_article_summary(
            row,
            template_text=template,
            note_title="Neupane 2026 - JGR.SP - 土星磁层等离子体密度与磁场准周期性的耦合来源分析",
            tags=["其他行星/土星", "方法/数据分析", "信息来源/仅摘要"],
            body="本文研究土星磁层中等离子体密度与磁场准周期性的耦合来源。",
            supplement="当前总结仅基于摘要和元数据生成，未获得全文。",
            root=ROOT,
        )

        rendered_tags = extract_summary_tags(markdown)
        self.assertIn("对象/其他行星/土星", rendered_tags)
        self.assertNotIn("其他行星/土星", rendered_tags)
        self.assertNotIn("方法/数据分析", rendered_tags)

    def test_index_existing_summary_files_keeps_duplicates_when_output_delete_not_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            output_dir = root / "out" / "auto" / "article_summaries"
            output_dir.mkdir(parents=True, exist_ok=True)
            older = output_dir / "older.md"
            newer = output_dir / "newer.md"
            content = "\n".join(
                [
                    "----",
                    "- [DOI](https://doi.org/10.1000/example)",
                    "- _Example_",
                    "- 正文",
                    "",
                    "----",
                    "记录时间戳: 2026-04-10 10:00:00",
                    "",
                ]
            )
            older.write_text(content, encoding="utf-8")
            newer.write_text(content, encoding="utf-8")
            os.utime(older, ns=(1_000_000_000, 1_000_000_000))
            os.utime(newer, ns=(2_000_000_000, 2_000_000_000))

            indexed = index_existing_summary_files(output_dir, root=root)

            self.assertEqual(indexed["10.1000/example"], newer)
            self.assertTrue(older.exists())
            self.assertTrue(newer.exists())

    def test_index_existing_summary_files_dedupes_same_doi_when_output_delete_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "config" / "runtime.json").write_text(
                json.dumps(
                    {
                        "safety": {
                            "allow_output_deletions": True,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "out" / "auto" / "article_summaries"
            output_dir.mkdir(parents=True, exist_ok=True)
            older = output_dir / "older.md"
            newer = output_dir / "newer.md"
            content = "\n".join(
                [
                    "----",
                    "- [DOI](https://doi.org/10.1000/example)",
                    "- _Example_",
                    "- 正文",
                    "",
                    "----",
                    "记录时间戳: 2026-04-10 10:00:00",
                    "",
                ]
            )
            older.write_text(content, encoding="utf-8")
            newer.write_text(content, encoding="utf-8")
            os.utime(older, ns=(1_000_000_000, 1_000_000_000))
            os.utime(newer, ns=(2_000_000_000, 2_000_000_000))

            indexed = index_existing_summary_files(output_dir, root=root)

            self.assertEqual(indexed["10.1000/example"], newer)
            self.assertFalse(older.exists())
            self.assertTrue(newer.exists())

    def test_force_regeneration_reuses_same_doi_output_path(self) -> None:
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
            second_paths = generate_article_summaries(
                [row],
                template,
                output_dir,
                require_analysis=False,
                reuse_existing_summaries=False,
            )

            self.assertEqual(first_paths[0], second_paths[0])
            self.assertEqual(len(list(output_dir.glob("*.md"))), 1)

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
        self.assertNotIn("对象/热层", tags)
        self.assertIn("对象/热层/风场", tags)
        self.assertIn("对象/热层/密度", tags)

    def test_infer_tags_from_text_uses_document_style_without_earth_tag(self) -> None:
        tags = infer_tags_from_text(
            "This study investigates Earth's thermospheric NO production and the drag of LEO satellites."
        )
        self.assertNotIn("对象/研究星球/地球", tags)
        self.assertNotIn("对象/热层/密度", tags)

    def test_infer_tags_from_text_does_not_treat_plain_by_as_imf_component(self) -> None:
        tags = infer_tags_from_text(
            "Improving the extraction ability of thermospheric mass density variations from observational data by deep learning."
        )
        self.assertNotIn("指数/IMF/By", tags)

    def test_infer_rule_based_tags_does_not_add_satellite_impact_for_background_drag_only(self) -> None:
        tags = infer_rule_based_tags_from_parts(
            title_text="Earth thermospheric NO production",
            body_text="This study investigates Earth's thermospheric NO production and the drag of LEO satellites.",
            extra_text="",
            root=ROOT,
        )
        self.assertNotIn("应用/卫星影响", tags)

    def test_infer_rule_based_tags_adds_satellite_impact_when_main_text_discusses_environmental_impact(self) -> None:
        tags = infer_rule_based_tags_from_parts(
            title_text="Geomagnetic storm impacts on satellite drag and orbit maintenance",
            body_text="This paper evaluates how geomagnetic storm driven thermospheric density changes increase satellite drag, alter orbit decay, and affect operational orbit maintenance.",
            extra_text="",
            root=ROOT,
        )
        self.assertIn("应用/卫星影响", tags)

    def test_infer_rule_based_tags_does_not_add_thermosphere_density_from_negated_supplement(self) -> None:
        tags = infer_rule_based_tags_from_parts(
            title_text="How well can solar wind parameters predict outer radiation belt electron flux?",
            body_text="This study evaluates outer radiation belt electron flux forecast skill using solar wind parameters and geomagnetic indices.",
            extra_text="文章重点在辐射带电子通量预报，不涉及热层密度、热层风或卫星阻力的直接分析。",
            root=ROOT,
        )
        self.assertNotIn("对象/热层/密度", tags)

    def test_sanitize_tags_keeps_only_first_other_planet(self) -> None:
        tags = sanitize_tags(["研究星球/土星", "研究星球/木星", "热层/风"])
        self.assertEqual(tags.count("对象/其他行星/土星"), 1)
        self.assertNotIn("对象/其他行星/木星", tags)

    def test_sanitize_tags_records_open_vocabulary_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            tags = sanitize_tags(["卫星影响", "极区/极光电流片", "区域/阿拉斯加"], root=root, context="deep_read", record_candidates=True)

            self.assertIn("应用/卫星影响", tags)
            self.assertIn("对象/极区/极光电流片", tags)
            self.assertNotIn("对象/区域/阿拉斯加", tags)
            payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))
            self.assertIn("对象/极区/极光电流片", payload["tags"])
            self.assertNotIn("对象/区域/阿拉斯加", payload["tags"])
            self.assertEqual(payload["tags"]["对象/极区/极光电流片"]["contexts"]["deep_read"], 1)

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
        self.assertIn("对象/热层/密度", tags)
        self.assertIn("应用/卫星影响", tags)
        self.assertIn("事件/磁暴", tags)
        self.assertIn("仪器/CHAMP", tags)
        self.assertIn("仪器/GRACE", tags)
        self.assertIn("方法/建模/机器学习", tags)
        self.assertIn("对象/热层/EMA", tags)
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
        self.assertIn("对象/热层/密度", tags)
        self.assertIn("方法/建模/机器学习", tags)
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
        self.assertNotIn("事件/磁暴", tags)

    def test_get_focus_tags_drops_satellite_impact_when_analysis_tag_lacks_context_support(self) -> None:
        row = {
            "title": "Thermospheric nitric oxide production during quiet conditions",
            "abstract": "This study investigates Earth's thermospheric NO production and the drag of LEO satellites as a side remark.",
            "notes": "",
            "topic_labels": "",
            "doi": "10.1000/no-example",
            "source_name": "JGR: Space Physics",
            "journal_title": "JGR: Space Physics",
            "published_date": "2026-04-17",
            "authors": "Example Author",
            "url": "https://example.org/no",
        }
        analysis = ArticleAnalysis(
            chinese_title="示例",
            tags=["应用/卫星影响", "热层/密度"],
            body="文章主要讨论热层 NO 产生，顺带提到低轨卫星阻力。",
            supplement="示例",
            recommendation="示例",
            one_sentence="示例",
        )
        tags = get_focus_tags(row, analysis=analysis, root=ROOT)
        self.assertNotIn("应用/卫星影响", tags)

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

    def test_validate_summary_fields_respects_manual_abstract_only_claim_even_with_cached_pdf(self) -> None:
        row = {
            "fingerprint": "abcdef123456",
            "source_id": "jgr_space_physics",
            "source_name": "Journal of Geophysical Research: Space Physics",
            "title": "Spatial Feature of the Multi-Day Thermospheric Mass Density Oscillations",
            "abstract": "Abstract: multi-day thermospheric mass density oscillations are studied.",
            "published_date": "2026-03-29",
            "doi": "10.1029/2025JA034650",
            "url": "https://example.org",
            "authors": "Wenbo Li",
            "topic_labels": "",
            "relevance_score": 9.0,
            "notes": "",
            "summary_source_kind": "local_pdf_full_text",
        }

        _, tags, _, supplement, _, _ = validate_summary_fields(
            row,
            "示例标题",
            ["热层/密度"],
            "示例正文",
            "仅基于论文题目页可获取的摘要与元数据整理，未获取到可靠的全文内容。",
            "示例建议",
            "示例一句话",
            root=ROOT,
        )
        self.assertIn("信息来源/仅摘要", tags)
        self.assertIn("当前总结仅基于摘要和元数据生成", supplement)
        self.assertNotIn("程序已读取并缓存全文", supplement)

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

    def test_national_academies_metadata_formats_as_organization(self) -> None:
        author = "National Academies of Sciences, Engineering, and Medicine"

        self.assertEqual(first_author_label(author), "National Academies")
        self.assertEqual(format_single_author_apa(author), author)
        self.assertEqual(abbreviate_journal_name("National Academies Press"), "NAP")


if __name__ == "__main__":
    unittest.main()
