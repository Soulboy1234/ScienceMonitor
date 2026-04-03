from __future__ import annotations

import difflib
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from unittest import mock

from reportlab.pdfgen import canvas

from .article_summaries import ArticleSummaryResult, generate_article_summaries
from .config import logs_root, project_root
from .deep_reads import run_deep_read
from .llm import AnalysisEngine, ArticleAnalysis, DeepReadAnalysis, ReportAnalysis
from .reporting import build_report
from .storage import Storage


@dataclass(frozen=True)
class GoldenEvalCaseResult:
    name: str
    fixture_path: Path
    actual_path: Path
    passed: bool
    updated: bool
    diff_path: Path | None
    message: str


def golden_eval_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "evals" / "golden"


def golden_eval_log_root(root: Path | None = None) -> Path:
    return logs_root(root) / "golden_eval"


def run_golden_eval(root: Path | None = None, *, update: bool = False) -> list[GoldenEvalCaseResult]:
    project = root or project_root()
    fixture_root = golden_eval_root(project)
    actual_root = golden_eval_log_root(project) / "actual"
    diff_root = golden_eval_log_root(project) / "diffs"
    fixture_root.mkdir(parents=True, exist_ok=True)
    actual_root.mkdir(parents=True, exist_ok=True)
    diff_root.mkdir(parents=True, exist_ok=True)

    cases = [
        ("article_summary", _build_article_summary_golden(project)),
        ("daily_report", _build_daily_report_golden(project)),
        ("deep_read", _build_deep_read_golden(project)),
    ]

    results: list[GoldenEvalCaseResult] = []
    for name, normalized_output in cases:
        fixture_path = fixture_root / f"{name}.md"
        actual_path = actual_root / f"{name}.md"
        diff_path = diff_root / f"{name}.diff"
        actual_path.write_text(normalized_output, encoding="utf-8")

        if update or not fixture_path.exists():
            fixture_path.write_text(normalized_output, encoding="utf-8")
            if diff_path.exists():
                diff_path.unlink()
            results.append(
                GoldenEvalCaseResult(
                    name=name,
                    fixture_path=fixture_path,
                    actual_path=actual_path,
                    passed=True,
                    updated=True,
                    diff_path=None,
                    message="updated fixture",
                )
            )
            continue

        expected_output = fixture_path.read_text(encoding="utf-8")
        if expected_output == normalized_output:
            if diff_path.exists():
                diff_path.unlink()
            results.append(
                GoldenEvalCaseResult(
                    name=name,
                    fixture_path=fixture_path,
                    actual_path=actual_path,
                    passed=True,
                    updated=False,
                    diff_path=None,
                    message="matched fixture",
                )
            )
            continue

        diff_text = "".join(
            difflib.unified_diff(
                expected_output.splitlines(keepends=True),
                normalized_output.splitlines(keepends=True),
                fromfile=str(fixture_path),
                tofile=str(actual_path),
            )
        )
        diff_path.write_text(diff_text, encoding="utf-8")
        results.append(
            GoldenEvalCaseResult(
                name=name,
                fixture_path=fixture_path,
                actual_path=actual_path,
                passed=False,
                updated=False,
                diff_path=diff_path,
                message="output drift detected",
            )
        )
    return results


def render_golden_eval_summary(results: list[GoldenEvalCaseResult]) -> str:
    lines = [
        "Golden eval summary:",
        f"- cases={len(results)}",
        f"- passed={sum(1 for item in results if item.passed)}",
        f"- updated={sum(1 for item in results if item.updated)}",
        f"- failed={sum(1 for item in results if not item.passed)}",
    ]
    for item in results:
        status = "updated" if item.updated else ("ok" if item.passed else "drift")
        lines.append(f"- {item.name}: {status}")
        lines.append(f"  fixture={item.fixture_path}")
        lines.append(f"  actual={item.actual_path}")
        if item.diff_path:
            lines.append(f"  diff={item.diff_path}")
    return "\n".join(lines)


def _build_article_summary_golden(project: Path) -> str:
    row = {
        "fingerprint": "golden-article-summary",
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
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "article_summaries"
        analysis_engine = AnalysisEngine(project)
        with mock.patch(
            "sciencemonitor.llm.AnalysisEngine.analyze_article",
            return_value=ArticleAnalysis(
                chinese_title="磁暴背景下电离层 TEC 与热层密度变化",
                tags=["电离层/TEC", "热层/密度", "磁暴", "仪器/GNSS"],
                body="这篇文章基于摘要信息讨论磁暴期间电离层 TEC 与热层密度的联合变化。",
                supplement="需要后续结合全文继续核对具体方法与定量结果。",
                recommendation="建议优先复核数据来源与磁暴分阶段特征。",
                one_sentence="文章围绕磁暴期间电离层 TEC 与热层密度变化展开。",
            ),
        ):
            paths = generate_article_summaries(
                [row],
                project / "config" / "templates" / "article_summary_template.md",
                output_dir,
                analysis_engine=analysis_engine,
                root=project,
            )
        return _normalize_markdown(paths[0].read_text(encoding="utf-8"))


def _build_daily_report_golden(project: Path) -> str:
    analysis_engine = AnalysisEngine(project)
    with mock.patch(
        "sciencemonitor.llm.AnalysisEngine.analyze_report",
        return_value=ReportAnalysis(
            overview_bullets=["今天的论文重点落在磁暴背景下的电离层 TEC 与热层密度响应。", "当前样例更偏向风暴响应类研究。"],
            daily_suggestions=["优先核对全文中的磁暴分阶段描述。", "关注 GNSS 观测与热层参数之间的耦合解释。"],
            topic_insights=[],
            journal_insights=[],
        ),
    ):
        markdown, _ = build_report(date(2026, 3, 14), [_sample_summary_result(project)], root=project, analysis_engine=analysis_engine)
    return _normalize_markdown(markdown)


def _build_deep_read_golden(project: Path) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_minimal_deep_read_project(root, project)
        storage = Storage(root / "data" / "science_monitor.db")
        pdf_path = root / "sample.pdf"
        canv = canvas.Canvas(str(pdf_path))
        canv.drawString(72, 750, "Introduction")
        canv.save()
        fake_analysis = DeepReadAnalysis(
            chinese_title="热层密度与卫星阻力响应的全文深度阅读",
            tags=["热层/密度", "卫星影响"],
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
            with mock.patch(
                "sciencemonitor.deep_reads._extract_pdf_text",
                return_value="Introduction Methods Results thermosphere density satellite drag",
            ), mock.patch(
                "sciencemonitor.deep_reads._resolve_metadata",
                return_value={
                    "doi": "10.1000/example",
                    "title": "Example Paper",
                    "journal": "JGR: Space Physics",
                    "url": "https://example.org",
                    "authors": "Alice Smith\nBob Chen",
                    "published_date": "2026-03-14",
                    "raw_authors": "Alice Smith\nBob Chen",
                },
            ), mock.patch(
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
        if not result.success or result.output_path is None:
            raise RuntimeError(f"Failed to build golden deep read output: {result.message}")
        return _normalize_markdown(result.output_path.read_text(encoding="utf-8"))


def _sample_summary_result(project: Path) -> ArticleSummaryResult:
    row = {
        "fingerprint": "golden-report",
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
        output_path=project / "out" / "auto" / "article_summaries" / "sample.md",
        note_title="Author 2026 - JGR.SP - 电离层背景下TEC特征研究",
        chinese_title="电离层背景下TEC特征研究",
        tags=["电离层/TEC"],
        body="这篇文章主要关注电离层 TEC 变化。",
        supplement="后续可继续关注相关过程。",
        recommendation="建议优先细读。",
        one_sentence="文章围绕电离层变化研究 TEC 特征。",
        rendered_markdown="sample",
    )


def _write_minimal_deep_read_project(target_root: Path, source_root: Path) -> None:
    (target_root / "config").mkdir(parents=True, exist_ok=True)
    (target_root / "config" / "templates").mkdir(parents=True, exist_ok=True)
    (target_root / "data").mkdir(parents=True, exist_ok=True)
    (target_root / "config" / "analysis.json").write_text(
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
    (target_root / "config" / "runtime.json").write_text(
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
    (target_root / "config" / "paths.json").write_text(
        json.dumps({"output_root": "out"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (target_root / "config" / "focus_tags.json").write_text(
        (source_root / "config" / "focus_tags.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (target_root / "config" / "templates" / "deep_reading_report_template.md").write_text(
        (source_root / "config" / "templates" / "deep_reading_report_template.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _normalize_markdown(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"记录时间戳:\s*.+", "记录时间戳: <TIMESTAMP>", normalized)
    normalized = re.sub(r"- 生成时间：.+", "- 生成时间：<TIMESTAMP>", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return normalized + "\n"
