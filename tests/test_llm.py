from __future__ import annotations

import json
import pathlib
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor import llm as llm_module
from sciencemonitor.llm import AnalysisEngine, AnalysisQuotaExceeded
from sciencemonitor.tags import infer_preferred_tags_from_text


class LLMTagNormalizationTest(unittest.TestCase):
    def test_normalizes_hierarchical_tags_from_focus_tag_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "log").mkdir()
            (root / "config" / "analysis.json").write_text(
                (ROOT / "config" / "analysis.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            engine = AnalysisEngine(root)
            tags = engine._normalize_tags(
                [
                    "低纬电离层",
                    "磁层状态",
                    "ROTI",
                    "频段/S波段",
                    "月球重力场",
                    "物理量/电子密度",
                ]
            )

            self.assertIn("对象/电离层/低纬", tags)
            self.assertIn("对象/磁层", tags)
            self.assertIn("指数/ROTI", tags)
            self.assertIn("仪器/射电/S波段", tags)
            self.assertIn("对象/其他行星/月球", tags)
            self.assertIn("对象/电离层/电子密度", tags)

    def test_normalizes_thermosphere_tags_hierarchically(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "log").mkdir()
            (root / "config" / "analysis.json").write_text(
                (ROOT / "config" / "analysis.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            engine = AnalysisEngine(root)
            tags = engine._normalize_tags(
                [
                    "热层风",
                    "中性密度",
                    "O/N2",
                    "热层温度",
                    "热层",
                ]
            )

            self.assertIn("对象/热层/风场", tags)
            self.assertIn("对象/热层/密度", tags)
            self.assertIn("对象/热层/成分", tags)
            self.assertIn("对象/热层/温度", tags)

    def test_normalizes_polar_convection_under_polar_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "log").mkdir()
            (root / "config" / "analysis.json").write_text(
                (ROOT / "config" / "analysis.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            engine = AnalysisEngine(root)
            tags = engine._normalize_tags(
                [
                    "高纬过程/极区对流",
                    "polar convection boundary",
                ]
            )

            self.assertIn("对象/极区/对流边界", tags)
            self.assertNotIn("高纬过程/极区对流", tags)
            self.assertNotIn("极区/对流", tags)

    def test_normalizes_research_body_tags_hierarchically(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "log").mkdir()
            (root / "config" / "analysis.json").write_text(
                (ROOT / "config" / "analysis.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            engine = AnalysisEngine(root)
            tags = engine._normalize_tags(
                [
                    "Earth",
                    "月球",
                ]
            )

            self.assertNotIn("研究星球/地球", tags)
            self.assertNotIn("对象/Earth", tags)
            self.assertIn("对象/其他行星/月球", tags)

    def test_fallback_planet_rules_use_formal_object_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "log").mkdir()
            (root / "config" / "analysis.json").write_text(
                (ROOT / "config" / "analysis.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            engine = AnalysisEngine(root)
            mars_tags = engine._normalize_tags(["martian"])
            saturn_tags = engine._normalize_tags(["saturnian"])

            self.assertIn("对象/其他行星/火星", mars_tags)
            self.assertIn("对象/其他行星/土星", saturn_tags)
            self.assertNotIn("其他行星/火星", mars_tags)
            self.assertNotIn("其他行星/土星", saturn_tags)

    def test_substorm_is_not_inferred_from_background_or_references_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "log").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            tags = infer_preferred_tags_from_text(
                title_text="Spatial Feature of the Multi-Day Thermospheric Mass Density Oscillations",
                body_text="Typical space weather events such as geomagnetic storms and substorms can drive thermospheric circulation. Ohtani et al. studied storm-substorm relationship.",
                root=root,
                max_tags=20,
            )
            self.assertNotIn("亚暴", tags)


class LLMProviderResolutionTest(unittest.TestCase):
    def _prepare_root(self, tmpdir: str) -> pathlib.Path:
        root = pathlib.Path(tmpdir)
        (root / "config").mkdir()
        (root / "data").mkdir()
        (root / "log").mkdir()
        (root / "config" / "analysis.json").write_text(
            (ROOT / "config" / "analysis.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (root / "config" / "focus_tags.json").write_text(
            (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return root

    def test_openai_api_key_prefers_configured_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            settings = engine.config["openai_api"]
            with mock.patch.dict(
                os.environ,
                {"SCIENCEMONITOR_OPENAI_API_KEY": "env-token", "OPENAI_API_KEY": ""},
                clear=False,
            ):
                self.assertEqual(engine._resolve_openai_api_key(settings), "env-token")
                self.assertEqual(engine._resolve_openai_api_key_source(settings), "SCIENCEMONITOR_OPENAI_API_KEY")

    def test_codex_executable_falls_back_to_codex_app_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            fallback = pathlib.Path(tmpdir) / "Codex.app" / "Contents" / "Resources" / "codex"
            fallback.parent.mkdir(parents=True)
            fallback.write_text("#!/bin/sh\n", encoding="utf-8")
            fallback.chmod(0o755)

            engine = AnalysisEngine(root)
            with mock.patch("sciencemonitor.llm.shutil.which", return_value=None), mock.patch.object(
                llm_module,
                "DEFAULT_CODEX_EXECUTABLE_CANDIDATES",
                (fallback,),
            ):
                self.assertEqual(engine._resolve_codex_executable({}, strict=False), str(fallback))

    def test_openai_api_key_falls_back_to_openai_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            settings = engine.config["openai_api"]
            with mock.patch.dict(
                os.environ,
                {"SCIENCEMONITOR_OPENAI_API_KEY": "", "OPENAI_API_KEY": "fallback-token"},
                clear=False,
            ):
                self.assertEqual(engine._resolve_openai_api_key(settings), "fallback-token")
                self.assertEqual(engine._resolve_openai_api_key_source(settings), "OPENAI_API_KEY")

    def test_openai_base_url_rejects_insecure_remote_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            with self.assertRaises(RuntimeError):
                engine._resolve_openai_base_url({"base_url": "http://example.com/v1/responses"})

    def test_article_cache_key_changes_with_source_kind_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            base_row = {
                "doi": "10.1000/example",
                "fingerprint": "example",
                "abstract": "short abstract",
                "summary_source_kind": "crossref_abstract",
            }
            key_a = engine._article_cache_key(base_row)
            key_b = engine._article_cache_key({**base_row, "summary_source_kind": "local_pdf_full_text"})
            key_c = engine._article_cache_key({**base_row, "abstract": "full text excerpt"})
            key_d = engine._article_cache_key({**base_row, "title": "Updated Example Paper"})
            self.assertNotEqual(key_a, key_b)
            self.assertNotEqual(key_a, key_c)
            self.assertNotEqual(key_a, key_d)

    def test_article_prompt_uses_source_text_wording_for_full_text_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            row = {
                "title": "Example Paper",
                "abstract": "Full text excerpt with methods and results.",
                "source_name": "JGR: Space Physics",
                "published_date": "2026-03-14",
                "authors": "A Author",
                "topic_labels": "",
                "summary_source_kind": "local_pdf_full_text",
            }
            prompt = engine._build_article_prompt(row)
            self.assertIn("资料来源：本地PDF全文整理稿", prompt)
            self.assertIn("来源文本：Full text excerpt with methods and results.", prompt)
            self.assertNotIn("摘要：", prompt)

    def test_usage_limit_raises_recoverable_quota_exception(self) -> None:
        stderr_path = ROOT / "log" / "llm_tmp" / "sample.stderr.log"
        stderr_text = (
            "ERROR: You've hit your usage limit. Upgrade to Pro.\n"
            "ERROR: You've hit your usage limit. try again at 11:01 AM.\n"
        )

        with self.assertRaises(AnalysisQuotaExceeded) as ctx:
            llm_module._summarize_codex_failure(1, stderr_text, stderr_path)

        self.assertEqual(ctx.exception.provider, "codex_local")
        self.assertEqual(ctx.exception.retry_after, "11:01 AM")
        self.assertIn("usage limit", str(ctx.exception).lower())

    def test_run_codex_structured_passes_reasoning_effort_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["codex_local"]["model"] = "gpt-5.4"
            observed: dict[str, object] = {}

            def fake_run(cmd, **kwargs):
                observed["cmd"] = cmd
                output_path = pathlib.Path(cmd[cmd.index("--output-last-message") + 1])
                output_path.write_text('{"body":"ok"}', encoding="utf-8")
                return mock.Mock(returncode=0)

            with mock.patch.object(engine, "_resolve_codex_executable", return_value="/tmp/codex"), mock.patch(
                "sciencemonitor.llm.subprocess.run",
                side_effect=fake_run,
            ):
                payload = engine._run_codex_structured(
                    "prompt",
                    {"schema": {"type": "object", "properties": {"body": {"type": "string"}}, "required": ["body"], "additionalProperties": False}},
                    "sample",
                    reasoning_effort="medium",
                )

            self.assertEqual(payload["body"], "ok")
            self.assertIn("--model", observed["cmd"])
            self.assertIn("gpt-5.4", observed["cmd"])
            self.assertIn("-c", observed["cmd"])
            self.assertIn('model_reasoning_effort="medium"', observed["cmd"])

    def test_article_cache_key_changes_with_reasoning_effort(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            base_row = {
                "doi": "10.1000/example",
                "fingerprint": "example",
                "abstract": "short abstract",
                "summary_source_kind": "crossref_abstract",
            }
            engine_medium = AnalysisEngine(root)
            engine_medium.config["article_summaries"]["reasoning_effort"] = "medium"
            engine_high = AnalysisEngine(root)
            engine_high.config["article_summaries"]["reasoning_effort"] = "high"
            self.assertNotEqual(engine_medium._article_cache_key(base_row), engine_high._article_cache_key(base_row))

    def test_run_ollama_structured_posts_schema_and_records_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
            }
            observed: dict[str, object] = {}

            class FakeResponse:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "message": {"content": json.dumps({"body": "ok"}, ensure_ascii=False)},
                            "prompt_eval_count": 12,
                            "eval_count": 8,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")

            def fake_urlopen(req, timeout):
                observed["url"] = req.full_url
                observed["timeout"] = timeout
                observed["payload"] = json.loads(req.data.decode("utf-8"))
                return FakeResponse()

            schema = {
                "name": "sample_schema",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }
            with mock.patch("sciencemonitor.llm_api_support.request.urlopen", side_effect=fake_urlopen):
                payload = engine._run_ollama_structured("prompt", schema, "sample")

            self.assertEqual(payload["body"], "ok")
            self.assertEqual(observed["url"], "http://127.0.0.1:11434/api/chat")
            self.assertEqual(observed["timeout"], 9)
            request_payload = observed["payload"]
            self.assertEqual(request_payload["model"], "gemma4:26b")
            self.assertFalse(request_payload["stream"])
            self.assertEqual(request_payload["format"], schema["schema"])
            events_path = root / "log" / "token_monitor" / "api_usage.jsonl"
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(events[0]["provider"], "ollama_api")
            self.assertEqual(events[0]["model"], "gemma4:26b")
            self.assertEqual(events[0]["total_tokens"], 20)

    def test_provider_status_checks_ollama_only_when_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)

            with mock.patch("sciencemonitor.llm.check_ollama_available", return_value=True) as checker:
                status = engine.provider_status()
            self.assertFalse(status["ollama_available"])
            checker.assert_not_called()

            engine.provider = "ollama_api"
            engine.config["provider"] = "ollama_api"
            with mock.patch("sciencemonitor.llm.check_ollama_available", return_value=True) as checker:
                status = engine.provider_status()
            self.assertTrue(status["ollama_available"])
            checker.assert_called_once()


if __name__ == "__main__":
    unittest.main()
