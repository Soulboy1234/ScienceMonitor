from __future__ import annotations

import io
import pathlib
import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.config_ui import _render_page, _run_deep_read_action, _run_report_action
from sciencemonitor.deep_reads import DeepReadResult


def _write_ui_project(root: pathlib.Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "doc" / "template").mkdir(parents=True, exist_ok=True)
    (root / "config" / "runtime.json").write_text(
        (
            '{"features":{"weekly_report_enabled":true},'
            '"cli_defaults":{"daily_days_back":7,"daily_max_per_source":20,"report_window_days":7},'
            '"deep_read":{"search_full_text_when_pdf_missing":true,"pdf_page_limit":40}}\n'
        ),
        encoding="utf-8",
    )
    (root / "config" / "analysis.json").write_text(
        (
            '{"provider":"codex_local","report":{"enabled":true,"max_papers_in_prompt":25,"reasoning_effort":"medium"},'
            '"deep_reads":{"enabled":true,"max_input_chars":28000,"reasoning_effort":"high"},'
            '"article_summaries":{"enabled":true,"max_items_per_run":0,"reasoning_effort":"medium"},'
            '"codex_local":{"model":"","executable":"","sandbox":"read-only","timeout_seconds":300},'
            '"openai_api":{"api_key":"","api_key_env":"SCIENCEMONITOR_OPENAI_API_KEY","model":"gpt-5-mini","base_url":"https://api.openai.com/v1/responses","timeout_seconds":120}}\n'
        ),
        encoding="utf-8",
    )
    (root / "config" / "paths.json").write_text('{"output_root":"out"}\n', encoding="utf-8")


@dataclass
class _FakeUpdateResult:
    fetched_count: int = 12
    kept_count: int = 8
    report_date: date = date(2026, 3, 31)
    error_count: int = 0
    errors: list[str] | None = None


class ConfigUITest(unittest.TestCase):
    def test_render_page_contains_operation_buttons(self) -> None:
        html = _render_page(
            project=ROOT,
            runtime={
                "features": {"weekly_report_enabled": True},
                "cli_defaults": {"daily_days_back": 7, "daily_max_per_source": 20, "report_window_days": 7},
                "deep_read": {"search_full_text_when_pdf_missing": True, "pdf_page_limit": 40},
            },
            analysis={
                "provider": "codex_local",
                "deep_reads": {"enabled": True},
                "codex_local": {"model": ""},
            },
            paths={"output_root": "out"},
            doctor={"warnings": [], "current_python": "/tmp/python"},
            status={},
        )
        self.assertIn("开始生成周报", html)
        self.assertIn("开始深度解读", html)
        self.assertIn("关闭面板服务", html)
        self.assertIn('action="/run-report"', html)
        self.assertIn('action="/run-deep-read"', html)
        self.assertIn("chatgpt_web_manual", html)

    def test_run_report_action_uses_monitor_daily_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            captured: dict[str, object] = {}

            class FakeMonitor:
                def __init__(self, project_root):
                    self.root = project_root

                def weekly_report_enabled(self):
                    return True

                def run_daily(self, report_date, days_back, max_per_source, source_ids=None):
                    captured["report_date"] = report_date
                    captured["days_back"] = days_back
                    captured["max_per_source"] = max_per_source
                    captured["source_ids"] = source_ids
                    return (
                        _FakeUpdateResult(),
                        root / "out" / "research_reports" / "2026-03-31 周报.md",
                        {"paper_count": 8, "journal_count": 3, "highlight_count": 4},
                    )

                def close(self):
                    captured["closed"] = True

            with mock.patch("sciencemonitor.config_ui.ScienceMonitor", FakeMonitor):
                result = _run_report_action(
                    root,
                    {
                        "report_date": ["2026-03-31"],
                        "report_window_days_run": ["7"],
                        "run_update_before_report": ["on"],
                        "report_update_days_back": ["7"],
                        "report_max_per_source_run": ["25"],
                        "report_source_ids": ["jgr_space_physics, space_weather"],
                    },
                )

        self.assertEqual(result["kind"], "ok")
        self.assertEqual(result["title"], "周报生成完成")
        self.assertIn("周报覆盖 8 篇论文、3 本期刊", result["message"])
        self.assertEqual(captured["days_back"], 7)
        self.assertEqual(captured["max_per_source"], 25)
        self.assertEqual(captured["source_ids"], {"jgr_space_physics", "space_weather"})
        self.assertTrue(captured["closed"])

    def test_run_deep_read_action_prefers_uploaded_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            output_note = root / "out" / "auto" / "deep_reads" / "sample.md"
            output_note.parent.mkdir(parents=True, exist_ok=True)
            output_note.write_text("# sample", encoding="utf-8")
            output_pdf = root / "out" / "auto" / "deep_reads_pdf" / "sample.pdf"
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            output_pdf.write_bytes(b"%PDF-1.4")
            observed: dict[str, object] = {}

            class FakeMonitor:
                def __init__(self, project_root):
                    self.root = project_root
                    self.storage = object()

                def close(self):
                    observed["closed"] = True

            def fake_run_deep_read(**kwargs):
                observed["pdf_path"] = kwargs["pdf_path"]
                observed["doi"] = kwargs["doi"]
                observed["title"] = kwargs["title"]
                self.assertTrue(pathlib.Path(kwargs["pdf_path"]).exists())
                return DeepReadResult(
                    success=True,
                    message="ok",
                    output_path=output_note,
                    pdf_output_path=output_pdf,
                    source_kind="pdf",
                )

            upload = SimpleNamespace(
                filename="paper.pdf",
                type="application/pdf",
                file=io.BytesIO(b"%PDF-1.4 test"),
            )

            with mock.patch("sciencemonitor.config_ui.ScienceMonitor", FakeMonitor), mock.patch(
                "sciencemonitor.config_ui.run_deep_read",
                side_effect=fake_run_deep_read,
            ):
                result = _run_deep_read_action(
                    root,
                    {
                        "deep_read_doi": ["10.1000/example"],
                        "deep_read_title": ["Example Paper"],
                        "deep_read_journal": ["JGR: Space Physics"],
                        "deep_read_url": [""],
                        "deep_read_pdf_path": [""],
                    },
                    {"deep_read_pdf": upload},
                )

        self.assertEqual(result["kind"], "ok")
        self.assertEqual(result["title"], "深度解读完成")
        self.assertIn("全文来源类型：pdf", result["message"])
        self.assertEqual(observed["doi"], "10.1000/example")
        self.assertEqual(observed["title"], "Example Paper")
        self.assertTrue(str(observed["pdf_path"]).endswith(".pdf"))
        self.assertTrue(observed["closed"])


if __name__ == "__main__":
    unittest.main()
