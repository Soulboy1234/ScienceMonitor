from __future__ import annotations

import io
import json
import pathlib
import re
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

from sciencemonitor.config_ui import _render_page, _run_deep_read_action, _run_manual_import_action, _run_report_action, _save_from_form
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
            ui_state={
                "counts": {"article_summaries": 3, "deep_reads": 2, "reports": 1, "manual_files": 4},
                "journals": ["JGR.SP", "SW"],
                "journal_groups": [{"label": "核心监测", "items": ["JGR.SP", "SW"]}],
                "token_usage": "1234（最近记录）",
                "maintenance_status": {
                    "overall": "ok",
                    "doctor": "ok",
                    "pytest": "ok",
                    "harness": "ok",
                    "entropy": "ok",
                    "path": str(ROOT / "log" / "maintenance" / "latest.md"),
                },
            },
        )
        self.assertIn("运行状态检查", html)
        self.assertIn("代码维护检查", html)
        self.assertIn("运行统计", html)
        self.assertIn("总览", html)
        self.assertIn("周报", html)
        self.assertIn("深度解读", html)
        self.assertIn('data-nav-target="weekly-report"', html)
        self.assertIn('data-nav-target="deep-read"', html)
        self.assertIn('action="/run-report"', html)
        self.assertIn('action="/run-deep-read"', html)
        self.assertIn("深度解读任务面板", html)
        self.assertLess(html.index("深度解读任务面板"), html.index("深度解读文章数量统计"))
        self.assertLess(html.index("深度解读文章数量统计"), html.index("最新深度解读报告"))
        self.assertIn("周报最新结果", html)
        self.assertIn("weekly-report-grid", html)
        self.assertIn("weekly-report-form-card", html)
        self.assertIn("weekly-report-journals-card", html)
        self.assertIn('class="form-stack"', html)
        self.assertIn("请求生成面板", html)
        self.assertIn('action="/manual-llm-create"', html)
        self.assertIn('action="/manual-llm-import-upload"', html)
        self.assertIn('name="deep_read_pdf_page_limit"', html)
        self.assertIn("分析后端与服务", html)
        self.assertIn('data-provider-select', html)
        self.assertNotIn('value="chatgpt_web_manual"', html)
        self.assertIn("OpenRouter API", html)
        self.assertIn("data-tooltip=", html)
        self.assertNotIn('class="nav-meta"', html)

    def test_render_page_shows_local_paths_and_manual_status(self) -> None:
        html = _render_page(
            project=ROOT,
            runtime={
                "features": {"weekly_report_enabled": True},
                "cli_defaults": {"daily_days_back": 7, "daily_max_per_source": 20, "report_window_days": 7},
                "deep_read": {"search_full_text_when_pdf_missing": True, "pdf_page_limit": 40},
            },
            analysis={
                "provider": "chatgpt_web_manual",
                "deep_reads": {"enabled": True},
                "codex_local": {"model": ""},
            },
            paths={
                "output_root": "out",
                "local_output_root": "/tmp/private-vault",
                "effective_output_root": "/tmp/private-vault",
                "local_paths_config": "/tmp/project/config/local.paths.json",
            },
            doctor={
                "warnings": [],
                "current_python": "/tmp/python",
                "provider_status": {
                    "provider": "codex_local",
                    "chatgpt_web_manual_pending": 1,
                    "chatgpt_web_manual_ready": 2,
                    "chatgpt_web_manual_stale": 3,
                },
            },
            status={},
            manual_requests=[
                SimpleNamespace(
                    request_id="article_123",
                    display_label="【待导入】Li（2026）- JGR.SP - Example Paper",
                    status="pending",
                    request_kind="article_summary",
                    title="Example Paper",
                    response_filename="response.json",
                )
            ],
            ui_state={
                "counts": {"article_summaries": 1, "deep_reads": 2, "reports": 3, "manual_files": 4},
                "journals": ["JGR.SP", "SW"],
                "journal_groups": [{"label": "核心监测", "items": ["JGR.SP", "SW"]}],
                "token_usage": "未记录",
                "maintenance_status": {
                    "overall": "ok",
                    "doctor": "ok",
                    "pytest": "ok",
                    "harness": "ok",
                    "entropy": "ok",
                    "path": "/tmp/private-vault/log/maintenance/latest.md",
                },
                "latest_article_summary": "/tmp/private-vault/auto/article_summaries/example.md",
                "latest_deep_read": "/tmp/private-vault/auto/deep_reads/example.md",
                "latest_report": "/tmp/private-vault/research_reports/example.md",
            },
        )
        self.assertIn("ScienceMonitor", html)
        self.assertRegex(html, r'brand-version">v\d+\.\d+\.\d+<')
        self.assertIn("面板地址", html)
        self.assertIn("/tmp/private-vault", html)
        self.assertIn("人工中转", html)
        self.assertIn("pending 1 / ready 2", html)
        self.assertIn("ChatGPT 响应文件解读面板", html)
        self.assertIn("【待导入】Li（2026）- JGR.SP - Example Paper", html)
        self.assertNotIn("研究控制台。左侧切换模块，右侧查看状态和执行操作。", html)
        self.assertIn("人工中转最近活动", html)
        self.assertIn('action="/manual-llm-import-upload"', html)
        self.assertIn("真实输出目录（本机私有）", html)
        self.assertNotIn("公开默认路径", html)
        self.assertNotIn("deep_read_internal_id", html)

    def test_save_from_form_writes_private_local_paths_without_overwriting_public_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            _save_from_form(
                root,
                {
                    "provider": ["openai_api"],
                    "article_summaries_reasoning_effort": ["medium"],
                    "report_reasoning_effort": ["medium"],
                    "deep_reads_reasoning_effort": ["high"],
                    "codex_model": [""],
                    "codex_executable": [""],
                    "codex_sandbox": ["read-only"],
                    "codex_timeout_seconds": ["300"],
                    "openai_api_key": [""],
                    "openai_api_key_env": ["SCIENCEMONITOR_OPENAI_API_KEY"],
                    "openai_model": ["gpt-5-mini"],
                    "openai_base_url": ["https://api.openai.com/v1/responses"],
                    "openai_timeout_seconds": ["120"],
                    "local_output_root": ["/tmp/private-vault"],
                },
            )

            public_paths = json.loads((root / "config" / "paths.json").read_text(encoding="utf-8"))
            local_paths = json.loads((root / "config" / "local.paths.json").read_text(encoding="utf-8"))
            analysis = json.loads((root / "config" / "analysis.json").read_text(encoding="utf-8"))

        self.assertEqual(public_paths["output_root"], "out")
        self.assertNotIn("local_output_root", public_paths)
        self.assertNotIn("effective_output_root", public_paths)
        self.assertEqual(local_paths["output_root"], "/tmp/private-vault")
        self.assertEqual(analysis["provider"], "openai_api")
        self.assertNotIn("enabled", analysis["article_summaries"])
        self.assertNotIn("max_items_per_run", analysis["article_summaries"])
        self.assertNotIn("enabled", analysis["report"])
        self.assertNotIn("max_papers_in_prompt", analysis["report"])
        self.assertNotIn("enabled", analysis["deep_reads"])
        self.assertNotIn("max_input_chars", analysis["deep_reads"])

    def test_save_from_form_supports_openrouter_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            _save_from_form(
                root,
                {
                    "provider": ["openrouter_api"],
                    "article_summaries_reasoning_effort": ["medium"],
                    "report_reasoning_effort": ["medium"],
                    "deep_reads_reasoning_effort": ["high"],
                    "codex_model": [""],
                    "codex_executable": [""],
                    "codex_sandbox": ["read-only"],
                    "codex_timeout_seconds": ["300"],
                    "openrouter_model": ["openai/gpt-5-mini"],
                    "openrouter_base_url": ["https://openrouter.ai/api/v1/chat/completions"],
                    "openrouter_api_key_env": ["SCIENCEMONITOR_OPENROUTER_API_KEY"],
                    "openrouter_api_key": [""],
                    "openrouter_site_url": ["https://example.com"],
                    "openrouter_app_name": ["ScienceMonitor"],
                    "openrouter_timeout_seconds": ["120"],
                    "local_output_root": ["/tmp/private-vault"],
                },
            )
            analysis = json.loads((root / "config" / "analysis.json").read_text(encoding="utf-8"))

        self.assertEqual(analysis["provider"], "openrouter_api")
        self.assertEqual(analysis["openrouter_api"]["model"], "openai/gpt-5-mini")
        self.assertEqual(analysis["openrouter_api"]["site_url"], "https://example.com")

    def test_run_manual_import_action_uses_recommended_response_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            with mock.patch(
                "sciencemonitor.config_ui_actions.import_manual_response_and_generate",
                return_value={
                    "title": "人工中转文章总结已生成",
                    "message": "已导入响应并生成单篇总结。",
                    "path": str(root / "out" / "auto" / "article_summaries" / "sample.md"),
                    "extra_path": "",
                },
            ) as importer:
                result = _run_manual_import_action(root, {"manual_request_id": ["article_123"], "manual_response_file": [""]})

        importer.assert_called_once_with(root, request_id="article_123")
        self.assertEqual(result["kind"], "ok")
        self.assertEqual(result["title"], "人工中转文章总结已生成")
        self.assertIn("生成单篇总结", result["message"])

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

                def run_daily(self, report_date, days_back, max_per_source, hydrate=True, source_ids=None):
                    captured["report_date"] = report_date
                    captured["days_back"] = days_back
                    captured["max_per_source"] = max_per_source
                    captured["hydrate"] = hydrate
                    captured["source_ids"] = source_ids
                    return (
                        _FakeUpdateResult(),
                        root / "out" / "research_reports" / "2026-03-31 周报.md",
                        {"paper_count": 8, "journal_count": 3, "highlight_count": 4},
                    )

                def close(self):
                    captured["closed"] = True

            with mock.patch("sciencemonitor.config_ui_actions.ScienceMonitor", FakeMonitor):
                result = _run_report_action(
                    root,
                    {
                        "report_date": ["2026-03-31"],
                        "report_window_days_run": ["7"],
                        "run_update_before_report": ["on"],
                        "report_update_days_back": ["7"],
                        "report_max_per_source_run": ["25"],
                        "report_update_hydrate": ["on"],
                        "report_source_ids": ["jgr_space_physics, space_weather"],
                    },
                )

        self.assertEqual(result["kind"], "ok")
        self.assertEqual(result["title"], "周报生成完成")
        self.assertIn("周报覆盖 8 篇论文、3 本期刊", result["message"])
        self.assertEqual(captured["days_back"], 7)
        self.assertEqual(captured["max_per_source"], 25)
        self.assertTrue(captured["hydrate"])
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
                observed["runtime_override"] = kwargs["runtime_override"]
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

            with mock.patch("sciencemonitor.config_ui_actions.ScienceMonitor", FakeMonitor), mock.patch(
                "sciencemonitor.config_ui_actions.run_deep_read",
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
                        "deep_read_pdf_page_limit": ["0"],
                    },
                    {"deep_read_pdf": upload},
                )

        self.assertEqual(result["kind"], "ok")
        self.assertEqual(result["title"], "深度解读完成")
        self.assertIn("全文来源类型：pdf", result["message"])
        self.assertEqual(observed["doi"], "10.1000/example")
        self.assertEqual(observed["title"], "Example Paper")
        self.assertEqual(observed["runtime_override"]["deep_read"]["pdf_page_limit"], 0)
        self.assertTrue(str(observed["pdf_path"]).endswith(".pdf"))
        self.assertTrue(observed["closed"])

    def test_render_page_renders_markdown_result_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            report_path = root / "out" / "research_reports" / "latest.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("# 周报标题\n\n- 第一条\n- 第二条\n", encoding="utf-8")
            html = _render_page(
                project=root,
                runtime={
                    "features": {"weekly_report_enabled": True},
                    "cli_defaults": {"daily_days_back": 7, "daily_max_per_source": 20, "report_window_days": 7},
                    "deep_read": {"search_full_text_when_pdf_missing": True, "pdf_page_limit": 40},
                },
                analysis={"provider": "codex_local", "codex_local": {"model": ""}},
                paths={"output_root": "out", "effective_output_root": str(root / "out"), "local_output_root": "", "local_paths_config": ""},
                doctor={"warnings": [], "current_python": "/tmp/python", "provider_status": {}},
                status={},
                ui_state={
                    "counts": {"article_summaries": 0, "deep_reads": 0, "reports": 1, "manual_files": 0},
                    "journals": [],
                    "journal_groups": [],
                    "token_usage": "未记录",
                    "latest_report": str(report_path),
                },
            )
        self.assertIn("markdown-render", html)
        self.assertIn("<h1>周报标题</h1>", html)
        self.assertIn("<li>第一条</li>", html)


if __name__ == "__main__":
    unittest.main()
