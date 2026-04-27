from __future__ import annotations

import io
import json
import os
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

from sciencemonitor.config_ui import (
    _guard_no_conflicting_ui_task,
    _redirect_fragment_for_action,
    _render_page,
    _run_deep_read_action,
    _run_manual_import_action,
    _save_from_form,
)
from sciencemonitor.config_ui_actions import _run_report_action, _start_report_action
from sciencemonitor.config_ui_page_sections import _build_token_tick_values, _token_chart_height_percent, _token_chart_label_indices
from sciencemonitor.config_ui_runtime import read_config_ui_runtime_state, set_weekly_report_job_state, write_config_ui_runtime_state
from sciencemonitor.config_ui_report_jobs import _run_report_job_worker
from sciencemonitor.config_ui_state_summary import detect_token_usage, latest_manual_result_file
from sciencemonitor.deep_reads import DeepReadResult
from sciencemonitor.llm import AnalysisQuotaExceeded


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
            '"openai_api":{"api_key":"","api_key_env":"SCIENCEMONITOR_OPENAI_API_KEY","model":"gpt-5-mini","base_url":"https://api.openai.com/v1/responses","timeout_seconds":120},'
            '"openrouter_api":{"api_key":"","api_key_env":"SCIENCEMONITOR_OPENROUTER_API_KEY","model":"openai/gpt-5-mini","base_url":"https://openrouter.ai/api/v1/chat/completions","timeout_seconds":120},'
            '"ollama_api":{"model":"gemma4:26b","base_url":"http://127.0.0.1:11434/api/chat","timeout_seconds":300}}\n'
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
    def test_redirect_fragment_for_actions(self) -> None:
        self.assertEqual(_redirect_fragment_for_action("/run-report"), "weekly-report")
        self.assertEqual(_redirect_fragment_for_action("/run-deep-read"), "deep-read")
        self.assertEqual(_redirect_fragment_for_action("/manual-llm-create"), "manual-llm")
        self.assertEqual(_redirect_fragment_for_action("/manual-llm-import-upload"), "manual-llm")
        self.assertEqual(_redirect_fragment_for_action("/save-config"), "settings")
        self.assertEqual(_redirect_fragment_for_action("/unknown"), "")

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
                "token_usage": "今天 1,234（1次） / 本周 1,234（1次） / 本月 1,234（1次）",
                "token_usage_periods": {
                    "today": {"label": "今天", "tokens": 1234, "runs": 1},
                    "week": {"label": "本周", "tokens": 1234, "runs": 1},
                    "month": {"label": "本月", "tokens": 1234, "runs": 1},
                },
                "token_usage_chart": {
                    "max_tokens": 1234,
                    "providers": [{"key": "codex_local", "label": "Codex 本地", "color": "#d9482b"}],
                    "days": [
                        {
                            "date": "2026-03-12",
                            "label": "3月12日",
                            "short_label": "3/12",
                            "show_label": True,
                            "total_tokens": 0,
                            "runs": 0,
                            "providers": {"codex_local": {"tokens": 0, "label": "Codex 本地", "color": "#d9482b"}},
                        },
                        {
                            "date": "2026-04-10",
                            "label": "4月10日",
                            "short_label": "4/10",
                            "show_label": True,
                            "total_tokens": 1234,
                            "runs": 1,
                            "providers": {"codex_local": {"tokens": 1234, "label": "Codex 本地", "color": "#d9482b"}},
                        },
                    ],
                },
                "report_job": {
                    "status": "running",
                    "step": "生成单篇总结",
                    "message": "正在整理单篇总结。",
                    "elapsed_seconds": 12.4,
                    "estimated_total_seconds": 36.1,
                    "fetched_count": 9,
                    "kept_count": 4,
                    "source_index": 2,
                    "source_total": 6,
                    "current_source": "jgr_space_physics",
                    "summary_total": 4,
                    "summary_completed": 2,
                    "summary_current_title": "Example Paper",
                    "summary_provider": "codex_local",
                    "summary_model": "gpt-5.4",
                    "summary_reasoning_effort": "medium",
                    "summary_avg_tokens": 17790,
                },
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
        self.assertIn("环境检查：", html)
        self.assertIn("代码维护检查：", html)
        self.assertIn("运行统计", html)
        self.assertIn("总览", html)
        self.assertIn("周报", html)
        self.assertIn("深度解读", html)
        self.assertIn('<meta name="sciencemonitor-ui" content="config-ui">', html)
        self.assertIn('data-nav-target="weekly-report"', html)
        self.assertIn('data-nav-target="deep-read"', html)
        self.assertIn('action="/run-report"', html)
        self.assertIn('action="/run-deep-read"', html)
        self.assertIn("深度解读任务面板", html)
        self.assertLess(html.index("深度解读任务面板"), html.index("深度解读文章数量统计"))
        self.assertLess(html.index("深度解读文章数量统计"), html.index("最新深度解读报告"))
        self.assertIn("周报最新结果", html)
        self.assertIn("周报运行状态", html)
        self.assertIn("跳过已生成总结", html)
        self.assertLess(html.index('name="report_source_ids"'), html.index('name="run_update_before_report"'))
        self.assertIn("生成单篇总结", html)
        self.assertIn("来源进度：2/6", html)
        self.assertIn("单篇总结：2/4", html)
        self.assertIn("模型：gpt-5.4", html)
        self.assertIn("推理强度：medium", html)
        self.assertIn("平均单篇 token：17790", html)
        self.assertIn("Token 使用", html)
        self.assertIn("token-chart-column", html)
        self.assertIn("token-chart-axis-y", html)
        self.assertIn("token-chart-axis-y-ticks", html)
        self.assertIn("token-chart-axis-x", html)
        self.assertIn("token-chart-axis-labels", html)
        self.assertIn("token-chart-axis-slot", html)
        self.assertIn("token-chart-axis-label", html)
        self.assertIn('data-token-label-slot="0"', html)
        self.assertIn('data-token-label-slot="1"', html)
        self.assertIn("visible", html)
        self.assertIn("data-token-date=", html)
        self.assertIn("今天 1,234（1次）", html)
        self.assertIn("当前单篇：Example Paper", html)
        self.assertLess(html.index("LLM 状态"), html.index("运行状态检查"))
        self.assertIn("weekly-report-grid", html)
        self.assertIn("weekly-report-form-card", html)
        self.assertIn("weekly-report-journals-card", html)
        self.assertIn('class="form-stack"', html)
        self.assertIn("请求生成面板", html)
        self.assertIn('action="/manual-llm-create"', html)
        self.assertIn('action="/manual-llm-import-upload"', html)
        self.assertIn('name="deep_read_pdf_page_limit"', html)
        self.assertIn("分析后端与服务", html)
        self.assertIn("标签管理", html)
        self.assertIn("显示正式标签", html)
        self.assertIn("显示预选标签", html)
        self.assertIn("标签转正", html)
        self.assertIn('data-provider-select', html)
        self.assertNotIn('value="chatgpt_web_manual"', html)
        self.assertIn("OpenRouter API", html)
        self.assertIn("Ollama 本地", html)
        self.assertIn("data-tooltip=", html)
        self.assertNotIn('class="nav-meta"', html)
        self.assertIn("运行状态", html)
        self.assertIn("当前无运行任务", html)

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
                "token_usage": "今天 0（0次） / 本周 0（0次） / 本月 0（0次）",
                "token_usage_periods": {},
                "token_usage_chart": {"max_tokens": 0, "providers": [], "days": []},
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
        self.assertIn("人工中转待处理", html)
        self.assertIn("当前有 1 个请求待导入。", html)
        self.assertNotIn("ready 2", html)
        self.assertIn("ChatGPT 响应文件解读面板", html)
        self.assertIn("【待导入】Li（2026）- JGR.SP - Example Paper", html)
        self.assertNotIn("研究控制台。左侧切换模块，右侧查看状态和执行操作。", html)
        self.assertIn("人工中转最近活动", html)
        self.assertIn('action="/manual-llm-import-upload"', html)
        self.assertIn("真实输出目录（本机私有）", html)
        self.assertNotIn("公开默认路径", html)
        self.assertNotIn("deep_read_internal_id", html)
        self.assertNotIn("周报模式", html)
        self.assertIn("运行任务", html)

    def test_latest_manual_result_prefers_gpt_summary_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            summary_dir = root / "out" / "auto" / "article_summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            week_summary = summary_dir / "week.md"
            manual_summary = summary_dir / "manual.md"
            week_summary.write_text("- #热层/密度\n", encoding="utf-8")
            manual_summary.write_text("- #热层/密度 #信息来源/GPT总结\n", encoding="utf-8")
            os.utime(week_summary, (2_000_000_000, 2_000_000_000))
            os.utime(manual_summary, (1_900_000_000, 1_900_000_000))

            latest = latest_manual_result_file(root)

        self.assertEqual(pathlib.Path(latest).name, "manual.md")

    def test_latest_manual_result_falls_back_to_imported_manual_doi(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            request_dir = root / "data" / "chatgpt_web_manual" / "requests" / "article_abc"
            request_dir.mkdir(parents=True, exist_ok=True)
            (request_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "request_id": "article_abc",
                        "request_kind": "article_summary",
                        "last_imported_at": "2026-04-10T10:00:00",
                        "resource_hints": {"doi": "10.1029/2025JA034650"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            summary_dir = root / "out" / "auto" / "article_summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            summary = summary_dir / "manual-without-tag.md"
            summary.write_text("- [DOI](https://doi.org/10.1029/2025JA034650) #热层/密度\n", encoding="utf-8")

            latest = latest_manual_result_file(root)

        self.assertEqual(pathlib.Path(latest).name, "manual-without-tag.md")

    def test_detect_token_usage_summarizes_codex_logs_by_period(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            log_dir = root / "log" / "llm_tmp"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / "article_abc_codex.stderr.log"
            path.write_text("tokens used\n17,554\n", encoding="utf-8")

            usage = detect_token_usage(root)

        periods = usage["periods"]
        self.assertIn("今天", usage["summary_text"])
        self.assertIn("1次", usage["summary_text"])
        self.assertEqual(periods["today"]["tokens"], 17554)
        self.assertEqual(periods["week"]["runs"], 1)

    def test_token_chart_height_percent_uses_chart_scale_max(self) -> None:
        self.assertEqual(_token_chart_height_percent(463894, 500000), 93)
        self.assertEqual(_token_chart_height_percent(438700, 500000), 88)

    def test_token_chart_tick_values_use_adaptive_integer_scale(self) -> None:
        ticks = _build_token_tick_values(463894)
        self.assertEqual(ticks[0], 480000)
        self.assertEqual(ticks[-1], 0)
        self.assertTrue(5 <= len(ticks) <= 8)
        steps = [ticks[index] - ticks[index + 1] for index in range(len(ticks) - 1)]
        self.assertTrue(all(step == steps[0] for step in steps))
        self.assertEqual(steps[0] % 10000, 0)

    def test_token_chart_label_indices_are_uniform(self) -> None:
        self.assertEqual(_token_chart_label_indices(30), [0, 6, 12, 18, 24, 29])
        self.assertEqual(_token_chart_label_indices(5), [0, 1, 2, 3, 4])

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

    def test_save_from_form_supports_ollama_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            _save_from_form(
                root,
                {
                    "provider": ["ollama_api"],
                    "article_summaries_reasoning_effort": ["medium"],
                    "report_reasoning_effort": ["medium"],
                    "deep_reads_reasoning_effort": ["high"],
                    "codex_model": [""],
                    "codex_executable": [""],
                    "codex_sandbox": ["read-only"],
                    "codex_timeout_seconds": ["300"],
                    "ollama_model": ["gemma4:26b"],
                    "ollama_base_url": ["http://127.0.0.1:11434/api/chat"],
                    "ollama_timeout_seconds": ["300"],
                    "local_output_root": ["/tmp/private-vault"],
                },
            )
            analysis = json.loads((root / "config" / "analysis.json").read_text(encoding="utf-8"))

        self.assertEqual(analysis["provider"], "ollama_api")
        self.assertEqual(analysis["ollama_api"]["model"], "gemma4:26b")
        self.assertEqual(analysis["ollama_api"]["base_url"], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(analysis["ollama_api"]["timeout_seconds"], 300)

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

                def run_daily(
                    self,
                    report_date,
                    days_back,
                    max_per_source,
                    hydrate=True,
                    source_ids=None,
                    progress_callback=None,
                    reuse_existing_summaries=True,
                ):
                    captured["report_date"] = report_date
                    captured["days_back"] = days_back
                    captured["max_per_source"] = max_per_source
                    captured["hydrate"] = hydrate
                    captured["source_ids"] = source_ids
                    captured["progress_callback"] = progress_callback
                    captured["reuse_existing_summaries"] = reuse_existing_summaries
                    return (
                        _FakeUpdateResult(),
                        root / "out" / "research_reports" / "2026-03-31 周报.md",
                        {"paper_count": 8, "journal_count": 3, "highlight_count": 4},
                    )

                def close(self):
                    captured["closed"] = True

            with mock.patch("sciencemonitor.config_ui_report_jobs.ScienceMonitor", FakeMonitor):
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
        self.assertFalse(captured["reuse_existing_summaries"])
        self.assertEqual(captured["source_ids"], {"jgr_space_physics", "space_weather"})
        self.assertTrue(captured["closed"])

    def test_start_report_action_writes_running_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            write_config_ui_runtime_state(root, host="127.0.0.1", port=8765, url="http://127.0.0.1:8765/")
            started = {"value": False}

            class FakeThread:
                def __init__(self, target=None, args=(), name="", daemon=False):
                    self.target = target
                    self.args = args
                    self.name = name
                    self.daemon = daemon

                def start(self):
                    started["value"] = True

            with mock.patch("sciencemonitor.config_ui_report_jobs.Thread", FakeThread):
                result = _start_report_action(
                    root,
                    {
                        "report_date": ["2026-03-31"],
                        "report_window_days_run": ["7"],
                        "run_update_before_report": ["on"],
                        "report_update_days_back": ["7"],
                        "report_max_per_source_run": ["25"],
                        "report_update_hydrate": ["on"],
                        "report_source_ids": ["jgr_space_physics"],
                    },
                )

            report_job = read_config_ui_runtime_state(root).get("report_job", {})
            self.assertTrue(started["value"])
            self.assertEqual(result["title"], "周报任务已开始")
            self.assertEqual(report_job.get("status"), "running")
            self.assertEqual(report_job.get("step"), "准备启动")
            self.assertEqual(report_job.get("report_date"), "2026-03-31")
            self.assertEqual(report_job.get("window_days"), 7)

    def test_run_report_job_worker_accepts_progress_dict_callback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            write_config_ui_runtime_state(root, host="127.0.0.1", port=8765, url="http://127.0.0.1:8765/")

            def fake_execute(project, params, progress_callback=None):
                assert progress_callback is not None
                progress_callback({"stage": "fetching", "source_index": 1, "source_total": 3, "fetched_count": 5, "kept_count": 2})
                return {
                    "kind": "ok",
                    "title": "周报生成完成",
                    "message": "done",
                    "path": str(root / "out" / "research_reports" / "sample.md"),
                    "paper_count": "2",
                    "journal_count": "1",
                }

            with mock.patch("sciencemonitor.config_ui_report_jobs.execute_report_action", side_effect=fake_execute):
                _run_report_job_worker(
                    root,
                    {
                        "run_update": True,
                        "report_date": date(2026, 4, 6),
                        "window_days": 7,
                        "update_days_back": 7,
                        "max_per_source": 20,
                        "hydrate": True,
                        "source_ids": set(),
                    },
                )

            report_job = read_config_ui_runtime_state(root).get("report_job", {})
            self.assertEqual(report_job.get("status"), "success")
            self.assertEqual(report_job.get("paper_count"), 2)
            self.assertEqual(report_job.get("journal_count"), 1)

    def test_run_report_job_worker_marks_quota_pause_as_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            write_config_ui_runtime_state(root, host="127.0.0.1", port=8765, url="http://127.0.0.1:8765/")

            def fake_execute(project, params, progress_callback=None):
                assert progress_callback is not None
                progress_callback(
                    {
                        "stage": "summary_generation",
                        "summary_total": 32,
                        "summary_completed": 30,
                        "summary_current_index": 31,
                        "summary_current_title": "Example Paper",
                        "summary_provider": "codex_local",
                        "summary_reasoning_effort": "medium",
                    }
                )
                raise AnalysisQuotaExceeded(
                    "codex_local",
                    root / "log" / "llm_tmp" / "example.stderr.log",
                    retry_after="11:01 AM",
                )

            with mock.patch("sciencemonitor.config_ui_report_jobs.execute_report_action", side_effect=fake_execute):
                _run_report_job_worker(
                    root,
                    {
                        "run_update": True,
                        "report_date": date(2026, 4, 17),
                        "window_days": 7,
                        "update_days_back": 7,
                        "max_per_source": 20,
                        "hydrate": True,
                        "source_ids": set(),
                    },
                )

            report_job = read_config_ui_runtime_state(root).get("report_job", {})
            self.assertEqual(report_job.get("status"), "paused_quota")
            self.assertEqual(report_job.get("step"), "等待额度恢复")
            self.assertTrue(report_job.get("recoverable"))
            self.assertEqual(report_job.get("retry_after"), "11:01 AM")
            self.assertIn("30/32", str(report_job.get("message", "")))

    def test_guard_no_conflicting_ui_task_blocks_other_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_ui_project(root)
            write_config_ui_runtime_state(root, host="127.0.0.1", port=8765, url="http://127.0.0.1:8765/")
            set_weekly_report_job_state(
                root,
                {
                "status": "running",
                "step": "抓取与筛选文章",
                "message": "正在抓取最新论文。",
                },
            )

            with self.assertRaisesRegex(ValueError, "当前已有周报任务正在运行"):
                _guard_no_conflicting_ui_task(root, "/run-deep-read")

            _guard_no_conflicting_ui_task(root, "/save-config")

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
                    "token_usage": "今天 0（0次） / 本周 0（0次） / 本月 0（0次）",
                    "token_usage_chart": {"max_tokens": 0, "providers": [], "days": []},
                    "latest_report": str(report_path),
                },
            )
        self.assertIn("markdown-render", html)
        self.assertIn("<h1>周报标题</h1>", html)
        self.assertIn("<li>第一条</li>", html)


if __name__ == "__main__":
    unittest.main()
