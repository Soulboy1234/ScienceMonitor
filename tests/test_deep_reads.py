from __future__ import annotations

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

from sciencemonitor.deep_reads import run_deep_read
from sciencemonitor.llm import DeepReadAnalysis
from sciencemonitor.storage import Storage


def _write_minimal_project(root: pathlib.Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "doc" / "template").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "config" / "analysis.json").write_text(
        json.dumps(
            {
                "provider": "codex_local",
                "deep_reads": {
                    "enabled": True,
                    "max_input_chars": 12000,
                    "fallback_to_rules": False,
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


class DeepReadTest(unittest.TestCase):
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
                tags=["热层/密度", "卫星影响", "研究星球/地球"],
                paper_type="深度学习重建 + ablation 实验",
                one_sentence_overview="这个文章真正想回答的，不是“行星际环境会不会影响热层密度”，而是更尖锐的一步：行星际环境变率本身能否独立驱动 day-to-day thermosphere variability。",
                why="作者希望回答热层密度变化如何影响卫星阻力环境。",
                how="作者结合全文中的观测、模型和 benchmark 对比推进结论。",
                key_results="最硬的结果是热层密度变化与阻力环境存在清晰对应关系。",
                contribution="这篇文章把相关问题推进到了可以直接支撑卫星影响判断的层面。",
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
            self.assertIn("### 7. 与已有工作的关系", text)


if __name__ == "__main__":
    unittest.main()
