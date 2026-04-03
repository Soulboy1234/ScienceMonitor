from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

from reportlab.pdfgen import canvas

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.deep_reads import (
    _audit_deep_read_markdown,
    _normalize_deep_read_analysis,
    _normalize_key_results_text,
    _normalize_relation_to_my_work_text,
    _normalize_structured_deep_read_text,
    _render_deep_read_markdown,
    _resolve_metadata,
    _run_deep_read_review_loop,
    _validate_deep_read_markdown,
    run_deep_read,
)
from sciencemonitor.llm import DeepReadAnalysis, _extract_introduction_excerpt
from sciencemonitor.storage import Storage


def _write_minimal_project(root: pathlib.Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "templates").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "config" / "analysis.json").write_text(
        json.dumps(
            {
                "provider": "codex_local",
                "deep_reads": {
                    "enabled": True,
                    "max_input_chars": 12000,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "config" / "runtime.json").write_text(
        json.dumps(
            {
                "features": {"weekly_report_enabled": True},
                "deep_read": {"search_full_text_when_pdf_missing": True, "pdf_page_limit": 10},
                "cli_defaults": {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "config" / "paths.json").write_text(
        json.dumps({"output_root": "out"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "config" / "focus_tags.json").write_text(
        ROOT.joinpath("config", "focus_tags.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "config" / "templates" / "deep_reading_report_template.md").write_text(
        ROOT.joinpath("config", "templates", "deep_reading_report_template.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


class DeepReadTest(unittest.TestCase):
    def test_structured_text_breaks_out_numbered_items_even_after_colons(self) -> None:
        text = _normalize_structured_deep_read_text(
            "硬结论：1. 第一条。2. 第二条。次级结论：1. 第三条。2. 第四条。合理推论：1. 第五条。需进一步研究讨论的结论：1. 第六条。"
        )
        self.assertRegex(text, r"硬结论：\n+1\. 第一条。")
        self.assertRegex(text, r"\n+2\. 第二条。")
        self.assertRegex(text, r"\n\n次级结论：\n+1\. 第三条。")
        self.assertRegex(text, r"\n+2\. 第四条。")
        self.assertRegex(text, r"\n\n合理推论：\n+1\. 第五条。")
        self.assertRegex(text, r"\n\n需进一步研究讨论的结论：\n+1\. 第六条。")
        self.assertNotIn("硬结论：\n\n1.", text)

    def test_key_results_uses_level_four_subheadings(self) -> None:
        text = _normalize_key_results_text(
            "### 硬结论\n1. 第一条。\n### 次级结论\n1. 第二条。\n合理推论：1. 第三条。需进一步研究讨论的结论：1. 第四条。"
        )
        self.assertIn("#### 硬结论\n1. 第一条。", text)
        self.assertIn("#### 次级结论\n1. 第二条。", text)
        self.assertIn("#### 合理推论\n1. 第三条。", text)
        self.assertIn("#### 需进一步研究讨论的结论\n1. 第四条。", text)
        self.assertNotRegex(text, r"(?m)^###\s+硬结论$")

    def test_structured_text_renames_legacy_discussion_label(self) -> None:
        text = _normalize_structured_deep_read_text("合理解释：1. 第一条。仍需保留的部分：1. 第二条。")
        self.assertIn("合理推论：", text)
        self.assertIn("需进一步研究讨论的结论：", text)
        self.assertNotIn("合理解释", text)
        self.assertNotIn("仍需保留的部分", text)

    def test_structured_text_converts_chinese_ordinals_to_numbered_list(self) -> None:
        text = _normalize_structured_deep_read_text("它的价值体现在三点。第一，证据更直接。第二，链条更完整。第三，假说更清楚。")
        self.assertRegex(text, r"它的价值体现在三点。\n1\. 证据更直接。")
        self.assertRegex(text, r"\n2\. 链条更完整。")
        self.assertRegex(text, r"\n3\. 假说更清楚。")

    def test_structured_text_keeps_no_blank_line_before_list_and_one_after(self) -> None:
        text = _normalize_structured_deep_read_text("前文说明。1. 第一条。2. 第二条。整体看，后文总结。")
        self.assertIn("前文说明。\n1. 第一条。\n2. 第二条。\n\n整体看，后文总结。", text)
        self.assertNotIn("前文说明。\n\n1. 第一条。", text)
        self.assertNotIn("2. 第二条。\n\n\n整体看，后文总结。", text)

    def test_structured_text_breaks_numbered_reasons_without_space(self) -> None:
        text = _normalize_structured_deep_read_text("主要有三层原因。1. 第一层。2. 第二层。3. 第三层。")
        self.assertIn("主要有三层原因。\n1. 第一层。\n2. 第二层。\n3. 第三层。", text)

    def test_structured_text_rejoins_broken_hyphenated_terms(self) -> None:
        text = _normalize_structured_deep_read_text("Fabry\n-Perot 与离子\n-中性耦合控制 6\n3\n0.0 nm 发射。")
        self.assertIn("Fabry-Perot", text)
        self.assertIn("离子-中性", text)
        self.assertIn("630.0 nm", text)

    def test_relation_to_my_work_drops_downstream_items_without_breaking_numbering(self) -> None:
        text = _normalize_relation_to_my_work_text(
            "它提示两个重要方向。1. 可以继续跟踪东亚中纬边界区受极区过程直接控制的判据。2. 风场快速反转和摩擦加热可直接用于热层密度模型和阻力预报。",
            tags=["热层/风场", "极区/对流边界"],
        )
        self.assertIn("它和当前主线的直接关系主要体现在以下几点。", text)
        self.assertIn("1. 可以继续跟踪东亚中纬边界区受极区过程直接控制的判据。", text)
        self.assertNotIn("2.", text)
        self.assertIn("不宜直接外推到业务化或定量应用。", text)
        self.assertNotIn("两个重要方向", text)

    def test_goal_text_preserves_line_breaks_when_filtering_sentences(self) -> None:
        from sciencemonitor.deep_reads import _normalize_goal_text

        text = _normalize_goal_text(
            "引言指出已有研究已经知道背景。作者认为这个问题值得单独研究，主要有三层原因。1. 第一层原因。2. 第二层原因。3. 第三层原因。",
            tags=["热层/风场", "极区/对流边界"],
        )
        self.assertIn("主要有三层原因。\n1. 第一层原因。\n2. 第二层原因。\n3. 第三层原因。", text)

    def test_goal_text_rewrites_not_but_pattern_to_direct_problem_statement(self) -> None:
        from sciencemonitor.deep_reads import _normalize_goal_text

        text = _normalize_goal_text(
            "引言给出的核心问题不是“磁暴会不会扰动热层风”，这一点已有充分认识；作者真正要解决的是：在亚洲扇区几何磁纬相对较低的中纬地区，漠河这样的站点是否会被极区过程直接控制，以及这种控制在热层风上会呈现什么样的时序特征。作者认为这个问题值得单独研究，主要有三层原因。1. 第一层原因。2. 第二层原因。3. 第三层原因。",
            tags=["热层/风场", "极区/对流边界"],
        )
        self.assertIn(
            "作者要解决的问题是：在亚洲扇区几何磁纬相对较低的中纬地区，漠河这样的站点是否会被极区过程直接控制，以及这种控制在热层风上会呈现什么样的时序特征。",
            text,
        )
        self.assertNotIn("核心问题不是", text)
        self.assertIn("主要有三层原因。\n1. 第一层原因。\n2. 第二层原因。\n3. 第三层原因。", text)

    def test_goal_text_strips_redundant_author_wants_to_answer_prefix(self) -> None:
        from sciencemonitor.deep_reads import _normalize_goal_text

        text = _normalize_goal_text(
            "作者希望回答热层密度变化如何影响卫星阻力环境。",
            tags=["热层/密度"],
        )
        self.assertEqual(text, "作者要解决的问题是：热层密度变化如何影响卫星阻力环境。")

    def test_review_loop_fixes_why_section_and_key_results_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            note_path = root / "log" / "real_case_eval" / "case_a" / "deep_reads" / "deep_read.md"
            note_path.parent.mkdir(parents=True, exist_ok=True)
            markdown = "\n".join(
                [
                    "# 论文深度阅读报告",
                    "----",
                    "- [PDF](../deep_reads_pdf/example.pdf) #热层/风场 #极区/对流边界",
                    "- _Citation_",
                    "",
                    "## 论文信息",
                    "- **题目**：Example Paper",
                    "- **作者**：A Author",
                    "- **期刊**：JGR: Space Physics",
                    "- **年份**：2026",
                    "- **论文类型**：研究论文",
                    "",
                    "### 一句话总述",
                    "这篇文章的目标是说明格式审核有效。",
                    "",
                    "## 论文详解",
                    "### 为什么做",
                    "引言给出的核心问题不是“磁暴会不会扰动热层风”，而是：边界区站点是否会被极区过程直接控制。作者认为这个问题值得单独研究，主要有三层原因。1. 第一层原因。2. 第二层原因。",
                    "",
                    "### 如何做",
                    "作者通过多仪器联合分析推进结论。",
                    "",
                    "### 关键结果",
                    "### 硬结论\n1. 第一条。",
                    "",
                    "### 新意与贡献",
                    "新意明确。",
                    "",
                    "### 局限性",
                    "仍需补图表核对。",
                    "",
                    "### 可复现性",
                    "基本可复现。",
                    "",
                    "### 与已有工作的关系",
                    "与现有工作相关。",
                    "",
                    "## 总结",
                    "### 最终结论",
                    "结论成立。",
                    "",
                    "### 补充信息",
                    "- 和我已有工作的关系：",
                    "关系说明。",
                    "",
                    "- 后续值得追踪的问题：",
                    "后续问题。",
                    "",
                    "- 需要人工复核的点：",
                    "人工复核。",
                    "",
                    "- Obsidian 索引挂接：",
                    "当前为评测输出，未写入 output_root，未生成 article_index 索引链接。",
                    "",
                    "----",
                    "记录时间戳: 2026-04-03 10:00",
                    "",
                ]
            )
            reviewed, issues = _run_deep_read_review_loop(
                root,
                markdown,
                note_path=note_path,
                tags=["热层/风场", "极区/对流边界"],
            )
        self.assertFalse(issues)
        self.assertIn("作者要解决的问题是：边界区站点是否会被极区过程直接控制。", reviewed)
        self.assertNotIn("不是“磁暴会不会扰动热层风”", reviewed)
        self.assertIn("主要有三层原因。\n1. 第一层原因。\n2. 第二层原因。", reviewed)
        self.assertIn("#### 硬结论\n1. 第一条。", reviewed)

    def test_render_deep_read_markdown_uses_relative_links_for_eval_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            note_path = root / "log" / "real_case_eval" / "case_a" / "deep_reads" / "deep_read.md"
            note_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path = root / "log" / "real_case_eval" / "case_a" / "deep_reads_pdf" / "example.pdf"
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b"%PDF-1.4")
            related_summary = root / "log" / "real_case_eval" / "case_a" / "article_summaries" / "summary.md"
            related_summary.parent.mkdir(parents=True, exist_ok=True)
            related_summary.write_text("- #热层/密度\n", encoding="utf-8")
            analysis = DeepReadAnalysis(
                chinese_title="测试",
                tags=["热层/密度"],
                paper_type="研究论文",
                one_sentence_overview="这篇文章的目标是测试链接。",
                why="作者要解决的问题是：测试。",
                how="测试。",
                key_results="#### 硬结论\n1. 测试。",
                contribution="测试。",
                limitations="测试。",
                reproducibility="测试。",
                relation="测试。",
                final_conclusion="测试。",
                relation_to_my_work="测试。",
                follow_up_questions="测试。",
                needs_manual_review="测试。",
                knowledge_position="当前为评测输出，未写入 output_root，未生成 article_index 索引链接。",
            )
            markdown = _render_deep_read_markdown(
                project=root,
                template_text=(root / "config" / "templates" / "deep_reading_report_template.md").read_text(encoding="utf-8"),
                metadata={
                    "doi": "10.1000/example",
                    "title": "Example Paper",
                    "journal": "JGR: Space Physics",
                    "authors": "A Author",
                    "raw_authors": "A Author",
                    "published_date": "2026-03-31",
                    "url": "https://example.org/paper",
                },
                analysis=analysis,
                related_summary=related_summary,
                note_path=note_path,
                pdf_path=pdf_path,
                source_kind="local_pdf_full_text",
                source_url=str(pdf_path),
                knowledge_position_text="当前为评测输出，未写入 output_root，未生成 article_index 索引链接。",
            )
        self.assertIn("[PDF](../deep_reads_pdf/example.pdf)", markdown)
        self.assertIn("[单篇总结](../article_summaries/summary.md)", markdown)
        self.assertNotIn("[[log/real_case_eval/", markdown)

    def test_audit_detects_eval_obsidian_links_as_invalid(self) -> None:
        markdown = "\n".join(
            [
                "# 论文深度阅读报告",
                "----",
                "- [[log/real_case_eval/case_a/deep_reads_pdf/example|PDF]]",
                "- _Citation_",
                "",
                "## 论文信息",
                "- **题目**：Example",
                "- **作者**：A",
                "- **期刊**：JGR",
                "- **年份**：2026",
                "- **论文类型**：研究论文",
                "",
                "### 一句话总述",
                "这篇文章的目标是测试。",
                "",
                "## 论文详解",
                "### 为什么做",
                "作者要解决的问题是：测试。",
                "",
                "### 如何做",
                "测试。",
                "",
                "### 关键结果",
                "#### 硬结论\n1. 测试。",
                "",
                "### 新意与贡献",
                "测试。",
                "",
                "### 局限性",
                "测试。",
                "",
                "### 可复现性",
                "测试。",
                "",
                "### 与已有工作的关系",
                "测试。",
                "",
                "## 总结",
                "### 最终结论",
                "测试。",
                "",
                "### 补充信息",
                "- 和我已有工作的关系：",
                "测试。",
                "",
                "- 后续值得追踪的问题：",
                "测试。",
                "",
                "- 需要人工复核的点：",
                "测试。",
                "",
                "- Obsidian 索引挂接：",
                "当前为评测输出，未写入 output_root，未生成 article_index 索引链接。",
                "",
                "----",
                "记录时间戳: 2026-04-03 10:00",
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            note_path = root / "log" / "real_case_eval" / "case_a" / "deep_reads" / "deep_read.md"
            note_path.parent.mkdir(parents=True, exist_ok=True)
            issues = _audit_deep_read_markdown(markdown, tags=["热层/风场"])
            validation = _validate_deep_read_markdown(
                markdown,
                project=root,
                note_path=note_path,
            )
        self.assertFalse(issues)
        self.assertIn("评测输出仍使用了生产态 Obsidian 链接", validation)

    def test_deep_read_analysis_can_add_auroral_imager_tag_from_full_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            analysis = DeepReadAnalysis(
                chinese_title="测试",
                tags=["热层/风场", "极区/对流边界", "极区/极光", "磁暴", "仪器/FPI", "仪器/SuperDARN"],
                paper_type="测试",
                one_sentence_overview="测试",
                why="测试",
                how="测试",
                key_results="测试",
                contribution="测试",
                limitations="测试",
                reproducibility="测试",
                relation="测试",
                final_conclusion="测试",
                relation_to_my_work="测试",
                follow_up_questions="测试",
                needs_manual_review="测试",
                knowledge_position="测试",
            )
            normalized = _normalize_deep_read_analysis(
                root,
                analysis,
                metadata_title="Polar convection case",
                full_text="Auroral photographs and FPI observations were used together with SuperDARN convection maps.",
            )
        self.assertIn("仪器/极光图像", normalized.tags)

    def test_extract_introduction_excerpt_prefers_introduction_section(self) -> None:
        excerpt = _extract_introduction_excerpt(
            "Abstract\nshort abstract\n1. Introduction\nThis study addresses a gap in midlatitude thermospheric wind research.\nIt explains why the case matters.\n2. Methods\nMethod details.",
            max_chars=500,
        )
        self.assertIn("gap in midlatitude thermospheric wind research", excerpt)
        self.assertIn("why the case matters", excerpt)
        self.assertNotIn("Method details", excerpt)

    def test_resolve_metadata_can_lookup_crossref_by_doi(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            storage = Storage(root / "data" / "science_monitor.db")
            try:
                with mock.patch(
                    "sciencemonitor.deep_reads._search_crossref_by_doi",
                    return_value={
                        "doi": "10.1000/example",
                        "title": "Example Paper",
                        "journal": "JGR: Space Physics",
                        "url": "https://example.org/paper",
                        "authors": "A Author",
                        "published_date": "2026-03-31",
                        "raw_authors": "A Author",
                        "pdf_urls": [],
                    },
                ):
                    metadata = _resolve_metadata(
                        storage=storage,
                        doi="10.1000/example",
                        title="",
                        journal="",
                        url="",
                    )
            finally:
                storage.close()

        self.assertEqual(metadata["title"], "Example Paper")
        self.assertEqual(metadata["journal"], "JGR: Space Physics")

    def test_fails_when_no_pdf_and_full_text_search_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            storage = Storage(root / "data" / "science_monitor.db")
            try:
                with mock.patch("sciencemonitor.deep_reads._search_crossref_by_title", return_value={
                    "doi": "10.1000/example",
                    "title": "Example Paper",
                    "journal": "JGR: Space Physics",
                    "url": "",
                    "authors": "",
                    "published_date": "2026-03-31",
                    "raw_authors": "",
                }):
                    result = run_deep_read(
                        root=root,
                        storage=storage,
                        doi="",
                        title="Example Paper",
                    )
            finally:
                storage.close()

            self.assertFalse(result.success)
            self.assertIn("请提供文章 PDF", result.message)

    def test_generates_deep_read_from_provided_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            storage = Storage(root / "data" / "science_monitor.db")
            pdf_path = root / "sample.pdf"
            canv = canvas.Canvas(str(pdf_path))
            canv.drawString(72, 750, "Introduction")
            canv.drawString(72, 730, "This paper studies thermosphere density and satellite drag.")
            canv.drawString(72, 710, "Methods")
            canv.drawString(72, 690, "We use observations and modeling.")
            canv.drawString(72, 670, "Results")
            canv.drawString(72, 650, "The key result is robust.")
            canv.save()
            fake_analysis = DeepReadAnalysis(
                chinese_title="热层密度与卫星阻力响应的全文深度阅读",
                tags=["热层/密度", "卫星影响"],
                paper_type="深度学习重建 + ablation 实验",
                one_sentence_overview="这个文章真正想回答的，不是“行星际环境会不会影响热层密度”，而是更尖锐的一步：行星际环境变率本身能否独立驱动 day-to-day thermosphere variability。",
                why="作者希望回答热层密度变化如何影响卫星阻力环境。",
                how="作者结合全文中的观测、模型和 benchmark 对比推进结论。",
                key_results="1. 最硬的结果是热层密度变化与阻力环境存在清晰对应关系。 2. 第二个结果说明这种联系在多个场景下都成立。",
                contribution="这篇文章的贡献不是泛泛讨论，而是把'卫星阻力'这一应用联系明确连到了热层密度变化。",
                limitations="全文仍需要结合图表进一步核对关键幅值和边界条件。",
                reproducibility="如果拿到相同数据和处理流程，主要分析应当可以复现。",
                relation="它和已有热层密度研究互补，并增强了应用侧意义。",
                final_conclusion="最值得记住的是热层密度变化对卫星阻力环境的直接意义。",
                relation_to_my_work="和你后续关注的热层密度与卫星影响主线高度相关。",
                follow_up_questions="后续可继续跟踪不同太阳风背景下的响应差异。",
                needs_manual_review="需要人工核对全文中的图表细节与定量结果。",
                knowledge_position="建议挂接到热层密度与卫星影响相关目录。",
            )
            try:
                with mock.patch("sciencemonitor.deep_reads._extract_pdf_text", return_value="Introduction Methods Results thermosphere density satellite drag"), mock.patch(
                    "sciencemonitor.deep_reads.AnalysisEngine.analyze_deep_read",
                    return_value=fake_analysis,
                ):
                    result = run_deep_read(
                        root=root,
                        storage=storage,
                        doi="10.1000/example",
                        title="Example Paper",
                        pdf_path=str(pdf_path),
                        journal="JGR: Space Physics",
                    )
            finally:
                storage.close()

            self.assertTrue(result.success)
            self.assertIsNotNone(result.output_path)
            self.assertTrue(result.output_path.exists())
            text = result.output_path.read_text(encoding="utf-8")
            self.assertIn("论文深度阅读报告", text)
            self.assertNotIn("文件名：", text)
            self.assertNotIn("全文来源", text)
            self.assertNotRegex(text, r"不是[^。\n]*而是")
            self.assertIn("这篇文章的目标是", text)
            self.assertIn("热层日际变化", text)
            self.assertIn("消融实验", text)
            self.assertIn("基线对照", text)
            self.assertIn("### 与已有工作的关系", text)
            self.assertIn("1. 最硬的结果是热层密度变化与阻力环境存在清晰对应关系。", text)
            self.assertIn("\n2. 第二个结果说明这种联系在多个场景下都成立。", text)
            self.assertNotIn("\n\n2. 第二个结果说明这种联系在多个场景下都成立。", text)
            self.assertIn("“卫星阻力”", text)
            self.assertNotIn("'卫星阻力'", text)

    def test_deep_read_reuses_cached_article_source_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            cache_root = root / "data" / "article_source_cache"
            cache_root.mkdir(parents=True, exist_ok=True)
            cache_key = hashlib.sha1("source_v4|10.1000/example".encode("utf-8")).hexdigest()[:24]
            (cache_root / f"{cache_key}.json").write_text(
                json.dumps(
                    {
                        "doi": "10.1000/example",
                        "title": "Example Paper",
                        "journal": "JGR: Space Physics",
                        "source_kind": "local_pdf_full_text",
                        "source_url": "file:///tmp/example.pdf",
                        "pdf_path": "",
                        "scientific_text": "Full scientific text from cache.",
                        "summary_packet": "Summary packet.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            storage = Storage(root / "data" / "science_monitor.db")
            fake_analysis = DeepReadAnalysis(
                chinese_title="缓存全文深度阅读",
                tags=["热层/密度"],
                paper_type="个例研究",
                one_sentence_overview="作者研究热层密度变化。",
                why="解释热层变化。",
                how="利用缓存全文。",
                key_results="缓存文本可直接复用。",
                contribution="减少重复抽取。",
                limitations="仍需人工看图。",
                reproducibility="缓存可复用。",
                relation="和已有流程兼容。",
                final_conclusion="全文缓存可用于后续深读。",
                relation_to_my_work="有助于减少重复成本。",
                follow_up_questions="后续可再补图表信息。",
                needs_manual_review="图表仍需人工核对。",
                knowledge_position="可挂接全文缓存链路。",
            )
            try:
                with mock.patch(
                    "sciencemonitor.deep_reads._resolve_metadata",
                    return_value={
                        "doi": "10.1000/example",
                        "title": "Example Paper",
                        "journal": "JGR: Space Physics",
                        "url": "https://example.org/paper",
                        "authors": "A Author",
                        "published_date": "2026-03-31",
                    },
                ), mock.patch("sciencemonitor.deep_reads.AnalysisEngine.analyze_deep_read", return_value=fake_analysis):
                    result = run_deep_read(
                        root=root,
                        storage=storage,
                        doi="10.1000/example",
                        title="Example Paper",
                        journal="JGR: Space Physics",
                    )
            finally:
                storage.close()

            self.assertTrue(result.success)
            self.assertEqual(result.source_kind, "local_pdf_full_text")

    def test_deep_read_can_write_to_eval_local_overrides_without_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            storage = Storage(root / "data" / "science_monitor.db")
            pdf_path = root / "sample.pdf"
            canv = canvas.Canvas(str(pdf_path))
            canv.drawString(72, 750, "Introduction")
            canv.drawString(72, 730, "This paper studies thermosphere density and satellite drag.")
            canv.save()
            fake_analysis = DeepReadAnalysis(
                chinese_title="本地评测深度阅读",
                tags=["热层/密度"],
                paper_type="研究论文",
                one_sentence_overview="这篇文章的目标是验证深度解读可以写入本地评测目录。",
                why="验证输出路径隔离。",
                how="通过本地 PDF 生成深度解读。",
                key_results="评测输出不应写入生产目录。",
                contribution="让 real-eval 可以在仓库内闭环。",
                limitations="仍需人工审阅正文质量。",
                reproducibility="同一 PDF 可重复生成同路径产物。",
                relation="和真实案例评测链路直接相关。",
                final_conclusion="深度解读评测应与生产输出隔离。",
                relation_to_my_work="便于手动校准。",
                follow_up_questions="后续可继续补真实基线。",
                needs_manual_review="内容质量仍需人工看。",
                knowledge_position="挂接到评测目录。",
            )
            related_summary = root / "log" / "real_case_eval" / "case_a" / "article_summaries" / "Li 2026 - JGR.SP - 示例单篇总结.md"
            related_summary.parent.mkdir(parents=True, exist_ok=True)
            related_summary.write_text(
                "\n".join(
                    [
                        "- #热层/密度 #磁暴 #仪器/FPI",
                        "- _Citation_",
                        "- 正文内容",
                        "1. 示例摘要",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "log" / "real_case_eval" / "case_a" / "deep_reads"
            pdf_dir = root / "log" / "real_case_eval" / "case_a" / "deep_reads_pdf"
            try:
                with mock.patch(
                    "sciencemonitor.deep_reads._extract_pdf_text",
                    return_value="Introduction Results thermosphere density satellite drag",
                ), mock.patch(
                    "sciencemonitor.deep_reads.AnalysisEngine.analyze_deep_read",
                    return_value=fake_analysis,
                ), mock.patch("sciencemonitor.deep_reads.sync_out_library") as sync_mock:
                    result = run_deep_read(
                        root=root,
                        storage=storage,
                        doi="10.1000/example",
                        title="Example Paper",
                        pdf_path=str(pdf_path),
                        journal="JGR: Space Physics",
                        output_dir_override=output_dir,
                        pdf_dir_override=pdf_dir,
                        sync_library=False,
                        related_summary_override=related_summary,
                    )
            finally:
                storage.close()

            self.assertTrue(result.success)
            self.assertIsNotNone(result.output_path)
            self.assertIsNotNone(result.pdf_output_path)
            self.assertTrue(result.output_path.exists())
            self.assertTrue(result.pdf_output_path.exists())
            self.assertEqual(result.output_path.parent, output_dir)
            self.assertEqual(result.pdf_output_path.parent, pdf_dir)
            self.assertEqual(result.output_path.name, "Li 2026 - JGR.SP - 示例单篇总结 深度解读.md")
            text = result.output_path.read_text(encoding="utf-8")
            self.assertIn("#磁暴", text)
            self.assertIn("#仪器/FPI", text)
            sync_mock.assert_not_called()

    def test_custom_deep_read_template_controls_render_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            custom_template = "\n".join(
                [
                    "# 论文深度阅读报告",
                    "----",
                    "{{entry_line}}",
                    "## 总结",
                    "### 最终结论",
                    "{{final_conclusion}}",
                    "- _{{apa_citation}}_",
                    "## 论文信息",
                    "- **题目**：{{title}}",
                    "- **作者**：{{authors}}",
                    "- **期刊**：{{journal}}",
                    "- **年份**：{{year}}",
                    "- **论文类型**：{{paper_type}}",
                    "### 一句话总述",
                    "{{one_sentence_overview}}",
                    "## 论文详解",
                    "### 为什么做",
                    "{{why}}",
                    "### 如何做",
                    "{{how}}",
                    "### 关键结果",
                    "{{key_results}}",
                    "### 新意与贡献",
                    "{{contribution}}",
                    "### 局限性",
                    "{{limitations}}",
                    "### 可复现性",
                    "{{reproducibility}}",
                    "### 与已有工作的关系",
                    "{{relation}}",
                    "### 补充信息",
                    "- 和我已有工作的关系：",
                    "{{relation_to_my_work}}",
                    "- 后续值得追踪的问题：",
                    "{{follow_up_questions}}",
                    "- 需要人工复核的点：",
                    "{{needs_manual_review}}",
                    "- Obsidian 索引挂接：",
                    "{{knowledge_position}}",
                    "----",
                    "记录时间戳: {{timestamp}}",
                ]
            )
            (root / "config" / "templates" / "deep_reading_report_template.md").write_text(custom_template, encoding="utf-8")

            storage = Storage(root / "data" / "science_monitor.db")
            pdf_path = root / "sample.pdf"
            canv = canvas.Canvas(str(pdf_path))
            canv.drawString(72, 750, "Introduction")
            canv.save()
            fake_analysis = DeepReadAnalysis(
                chinese_title="自定义模板深读",
                tags=["热层/密度", "卫星影响"],
                paper_type="研究论文",
                one_sentence_overview="这篇文章的目标是说明自定义模板已经进入真实渲染链路。",
                why="作者想回答一个关键问题。",
                how="作者通过观测和模型推进结论。",
                key_results="核心结果已经得到。",
                contribution="贡献明确。",
                limitations="仍有局限。",
                reproducibility="可复现。",
                relation="与已有工作互补。",
                final_conclusion="最重要的结论在这里。",
                relation_to_my_work="和我的工作相关。",
                follow_up_questions="还有后续问题。",
                needs_manual_review="还需人工复核。",
                knowledge_position="挂接到相关目录。",
            )
            try:
                with mock.patch("sciencemonitor.deep_reads._extract_pdf_text", return_value="Introduction"), mock.patch(
                    "sciencemonitor.deep_reads.AnalysisEngine.analyze_deep_read",
                    return_value=fake_analysis,
                ):
                    result = run_deep_read(
                        root=root,
                        storage=storage,
                        doi="10.1000/example",
                        title="Example Paper",
                        pdf_path=str(pdf_path),
                        journal="JGR: Space Physics",
                    )
            finally:
                storage.close()

            self.assertTrue(result.success)
            text = result.output_path.read_text(encoding="utf-8")
            self.assertLess(text.index("### 最终结论"), text.index("## 论文信息"))

    def test_invalid_deep_read_template_missing_placeholder_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_minimal_project(root)
            invalid_template = "\n".join(
                [
                    "# 论文深度阅读报告",
                    "----",
                    "{{entry_line}}",
                    "- _{{apa_citation}}_",
                    "## 论文信息",
                    "- **题目**：{{title}}",
                    "- **作者**：{{authors}}",
                    "- **期刊**：{{journal}}",
                    "- **年份**：{{year}}",
                    "- **论文类型**：{{paper_type}}",
                    "### 一句话总述",
                    "{{one_sentence_overview}}",
                    "## 论文详解",
                    "### 为什么做",
                    "{{why}}",
                    "### 如何做",
                    "{{how}}",
                    "### 关键结果",
                    "{{key_results}}",
                    "### 新意与贡献",
                    "{{contribution}}",
                    "### 局限性",
                    "{{limitations}}",
                    "### 可复现性",
                    "{{reproducibility}}",
                    "### 与已有工作的关系",
                    "{{relation}}",
                    "## 总结",
                    "### 最终结论",
                    "{{final_conclusion}}",
                    "### 补充信息",
                    "- 和我已有工作的关系：{{relation_to_my_work}}",
                    "- 后续值得追踪的问题：{{follow_up_questions}}",
                    "- 需要人工复核的点：{{needs_manual_review}}",
                    "----",
                    "记录时间戳: {{timestamp}}",
                ]
            )
            (root / "config" / "templates" / "deep_reading_report_template.md").write_text(invalid_template, encoding="utf-8")

            storage = Storage(root / "data" / "science_monitor.db")
            pdf_path = root / "sample.pdf"
            canv = canvas.Canvas(str(pdf_path))
            canv.drawString(72, 750, "Introduction")
            canv.save()
            fake_analysis = DeepReadAnalysis(
                chinese_title="失效模板深读",
                tags=["热层/密度", "卫星影响"],
                paper_type="研究论文",
                one_sentence_overview="这篇文章的目标是测试模板校验。",
                why="作者想回答一个关键问题。",
                how="作者通过观测和模型推进结论。",
                key_results="核心结果已经得到。",
                contribution="贡献明确。",
                limitations="仍有局限。",
                reproducibility="可复现。",
                relation="与已有工作互补。",
                final_conclusion="最重要的结论在这里。",
                relation_to_my_work="和我的工作相关。",
                follow_up_questions="还有后续问题。",
                needs_manual_review="还需人工复核。",
                knowledge_position="挂接到相关目录。",
            )
            try:
                with mock.patch("sciencemonitor.deep_reads._extract_pdf_text", return_value="Introduction"), mock.patch(
                    "sciencemonitor.deep_reads.AnalysisEngine.analyze_deep_read",
                    return_value=fake_analysis,
                ):
                    with self.assertRaisesRegex(ValueError, "missing required placeholders"):
                        run_deep_read(
                            root=root,
                            storage=storage,
                            doi="10.1000/example",
                            title="Example Paper",
                            pdf_path=str(pdf_path),
                            journal="JGR: Space Physics",
                        )
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
