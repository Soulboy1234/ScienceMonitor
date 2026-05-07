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
from sciencemonitor.llm import AnalysisEngine, AnalysisProviderInvalidOutput, AnalysisProviderTimeout, AnalysisQuotaExceeded
from sciencemonitor.llm_api_support import _parse_structured_output
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

    def test_ollama_article_invalid_json_can_be_repaired_from_raw_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "ollama_api"
            engine.config["provider"] = "ollama_api"
            row = {
                "doi": "10.1000/example",
                "fingerprint": "example",
                "title": "Storm-time ionospheric response",
                "abstract": "This paper studies ionospheric response during a geomagnetic storm.",
                "summary_source_kind": "crossref_abstract",
                "source_name": "Space Weather",
                "published_date": "2026-04-01",
                "authors": "A Author",
                "topic_labels": "空间天气",
                "url": "https://doi.org/10.1000/example",
            }
            detail_path = engine.tmp_root / "article_invalid_output.txt"
            detail_path.write_text(
                "\n".join(
                    [
                        "provider: ollama_api",
                        "detail: missing required fields: supplement, recommendation, one_sentence",
                        "",
                        "raw output:",
                        '{"chinese_title":"磁暴期间电离层响应","tags":"对象/电离层,事件/磁暴","body":"文章研究磁暴期间电离层响应。"}',
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                engine,
                "_run_structured",
                side_effect=AnalysisProviderInvalidOutput(
                    "ollama_api",
                    request_name="article_invalid_json",
                    detail="missing required fields",
                    detail_path=detail_path,
                ),
            ):
                analysis = engine.analyze_article(row, 0)

            self.assertEqual(analysis.chinese_title, "磁暴期间电离层响应")
            self.assertIn("对象/电离层", analysis.tags)
            self.assertIn("事件/磁暴", analysis.tags)
            self.assertEqual(analysis.supplement, "")

    def test_ollama_article_invalid_json_retries_with_short_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "ollama_api"
            engine.config["provider"] = "ollama_api"
            row = {
                "doi": "10.1000/retry",
                "fingerprint": "retry",
                "title": "Solar wind coupling",
                "abstract": "Solar wind coupling evidence. " * 400,
                "summary_source_kind": "crossref_abstract",
                "source_name": "Advances in Space Research",
                "published_date": "2026-04-01",
                "authors": "A Author",
                "topic_labels": "日地耦合",
                "url": "https://doi.org/10.1000/retry",
            }
            detail_path = engine.tmp_root / "article_retry_invalid_output.txt"
            detail_path.write_text(
                "raw output:\n"
                + json.dumps(
                    {
                        "model": "gemma4:26b",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "thinking": "我已经整理出 tags、body 和 one_sentence，但没有写入 content。",
                        },
                        "done": True,
                        "done_reason": "length",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            retry_payload = {
                "chinese_title": "太阳风耦合研究",
                "tags": ["对象/太阳风", "对象/磁层", "事件/磁暴"],
                "body": "文章研究太阳风耦合过程。",
                "supplement": "仅基于摘要。",
                "recommendation": "可作为背景阅读。",
                "one_sentence": "文章概括太阳风耦合过程。",
            }

            with mock.patch.object(
                engine,
                "_run_structured",
                side_effect=AnalysisProviderInvalidOutput(
                    "ollama_api",
                    request_name="article_invalid_json",
                    detail="invalid json",
                    detail_path=detail_path,
                ),
            ), mock.patch.object(engine, "_run_ollama_structured", return_value=retry_payload) as retry:
                analysis = engine.analyze_article(row, 0)

            self.assertEqual(analysis.chinese_title, "太阳风耦合研究")
            self.assertLess(len(retry.call_args.args[0]), 5000)

    def test_run_ollama_structured_posts_schema_and_records_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
                "keep_alive": "0",
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
            self.assertEqual(request_payload["keep_alive"], 0)
            self.assertNotIn("format", request_payload)
            self.assertEqual(request_payload["options"]["temperature"], 0)
            self.assertIn("只根据给定材料", request_payload["messages"][0]["content"])
            self.assertIn("JSON 字段契约", request_payload["messages"][1]["content"])
            events_path = root / "log" / "token_monitor" / "api_usage.jsonl"
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(events[0]["provider"], "ollama_api")
            self.assertEqual(events[0]["model"], "gemma4:26b")
            self.assertEqual(events[0]["total_tokens"], 20)

    def test_run_ollama_structured_uses_request_specific_system_prompts_and_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
                "keep_alive": "0",
                "num_ctx": 32768,
                "num_predict": 4096,
                "deep_read_num_predict": 8192,
            }
            observed_payloads: list[dict] = []

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
                observed_payloads.append(json.loads(req.data.decode("utf-8")))
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
                engine._run_ollama_structured("prompt", schema, "deep_read_sample")
                engine._run_ollama_structured("prompt", schema, "article_sample")

            deep_prompt = observed_payloads[0]["messages"][0]["content"]
            article_prompt = observed_payloads[1]["messages"][0]["content"]
            self.assertIn("全文或全文级长文本", deep_prompt)
            self.assertIn("不要退化为摘要复述", deep_prompt)
            self.assertNotIn("来源文本可能只是摘要", deep_prompt)
            self.assertIn("来源文本可能只是摘要", article_prompt)
            self.assertIn("不能假设还有全文", article_prompt)
            self.assertEqual(observed_payloads[0]["options"]["num_ctx"], 32768)
            self.assertEqual(observed_payloads[0]["options"]["num_predict"], 8192)
            self.assertEqual(observed_payloads[1]["options"]["num_predict"], 4096)
            self.assertEqual(observed_payloads[0]["keep_alive"], "1m")
            self.assertEqual(observed_payloads[1]["keep_alive"], 0)
            self.assertIs(observed_payloads[0]["think"], False)
            self.assertIs(observed_payloads[1]["think"], False)

    def test_ollama_deep_read_quality_mode_runs_evidence_before_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "ollama_api"
            engine.config["provider"] = "ollama_api"
            engine.config["ollama_api"]["deep_read_quality_mode"] = True
            calls: list[tuple[str, str]] = []
            dense = "这条判断包含具体对象、方法、证据边界和后续复核要求。" * 80

            def fake_run(prompt, schema, name):
                calls.append((name, prompt))
                if name.startswith("deep_read_evidence_v2_"):
                    return {
                        "research_problem": ["研究问题证据1", "研究问题证据2"],
                        "introduction_gap": "引言空白证据",
                        "method_chain": "方法链证据",
                        "hard_findings": ["硬结论1", "硬结论2"],
                        "secondary_findings": ["次级结论1", "次级结论2"],
                        "reasonable_inferences": ["推论1", "推论2"],
                        "open_questions": ["待验证1", "待验证2"],
                        "contribution_points": ["贡献1", "贡献2"],
                        "limitations": ["局限1", "局限2"],
                        "reproducibility_notes": ["复现线索1", "复现线索2"],
                        "relation_to_my_work_evidence": "间接相关证据",
                        "manual_review_points": "需要复核全文抽取缺损和公式。",
                    }
                return {
                    "chinese_title": "中文题目",
                    "tags": ["对象/磁层", "事件/磁暴", "仪器/GNSS"],
                    "paper_type": "研究论文",
                    "one_sentence_overview": "这篇文章针对磁层过程提出具体研究问题，并结合全文证据给出机制判断。",
                    "why": "作者要解决的问题是：已有研究对磁层过程的因果链解释不足，需要从引言空白出发重新组织证据。" + dense,
                    "how": "作者结合观测、方法和理论解释推进分析。\n1. 使用多源资料约束事件。\n2. 对比不同机制解释。\n3. 检查结果与已有工作的关系。",
                    "key_results": (
                        "硬结论：\n1. 硬结论一。\n2. 硬结论二。\n"
                        "次级结论：\n1. 次级结论一。\n2. 次级结论二。\n"
                        "合理推论：\n1. 合理推论一。\n2. 合理推论二。\n"
                        "需进一步研究讨论的结论：\n1. 待验证一。\n2. 待验证二。"
                    ),
                    "contribution": "1. 贡献一，说明理论链条。\n2. 贡献二，连接已有观测。\n3. 贡献三，指出后续验证方向。",
                    "limitations": "1. 论文自身仍有定量边界。\n2. 本次全文抽取可能缺少部分图表和公式。\n3. 部分机制解释需要人工复核。",
                    "reproducibility": "可复现性需要区分概念复核和定量复算；读者可以复核逻辑链条，但不能直接重复得到完整数值结果。",
                    "relation": "该研究与已有磁层-电离层耦合工作相关，属于机制解释层面的补充。",
                    "final_conclusion": "最终结论是这篇文章提供了可追踪的机制框架，但仍需要更多事件级证据约束。" + dense,
                    "relation_to_my_work": "间接相关。它可作为空间天气过程背景，不直接研究热层密度或卫星阻力。",
                    "follow_up_questions": "1. 后续问题一。\n2. 后续问题二。\n3. 后续问题三。",
                    "needs_manual_review": "需要人工复核全文抽取缺损、关键图表、公式定义和争议性机制解释。" + dense,
                    "knowledge_position": "适合作为磁层过程机制背景材料，而不是定量预报依据。",
                }

            with mock.patch.object(engine, "_run_ollama_structured", side_effect=fake_run):
                result = engine.analyze_deep_read(
                    {"title": "Example", "journal": "JGR: Space Physics", "doi": "10.1000/example"},
                    "Introduction\nThis paper identifies a gap.\n"
                    + ("The full text evidence is preserved. " * 800)
                    + "\n2. Data\nThe paper uses data and reports results.",
                )

            self.assertIsNotNone(result)
            self.assertEqual(len(calls), 2)
            self.assertTrue(calls[0][0].startswith("deep_read_evidence_v2_"))
            self.assertTrue(calls[1][0].startswith("deep_read_"))
            self.assertFalse(calls[1][0].startswith("deep_read_evidence_"))
            self.assertIn("证据预分析 v2", calls[1][1])
            self.assertIn("1. 研究问题证据1", calls[1][1])
            self.assertNotIn("['研究问题证据1'", calls[1][1])
            self.assertIn("全文分段核对材料", calls[1][1])

    def test_ollama_deep_read_final_context_prefers_scientific_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"]["deep_read_final_max_chars"] = 1800
            context = engine._ollama_deep_read_final_context_v2(
                "Abstract\nA compact abstract.\n\n"
                "1. Introduction\nThe introduction states the research gap.\n\n"
                "2. Data and Methods\nThe method uses observations and a model.\n\n"
                "3. Results\nThe results connect cause and effect.\n\n"
                "4. Conclusions\nThe conclusion states the boundary."
            )

            self.assertIn("摘要/引言", context)
            self.assertIn("方法/数据", context)
            self.assertIn("结果/讨论", context)
            self.assertIn("结论/总结", context)
            self.assertIn("research gap", context)

    def test_ollama_deep_read_normalizes_json_object_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            payload = {
                "chinese_title": "中文题目",
                "tags": ["对象/磁层", "事件/亚暴"],
                "paper_type": "理论论文",
                "one_sentence_overview": "本文通过电路模型解释亚暴。",
                "why": "为什么：需要解释太阳-月球（S-M）发电机。",
                "how": "如何",
                "key_results": json.dumps(
                    {
                        "硬结论": ["1. 硬结论一。", "2. 硬结论二。"],
                        "次级结论": ["1. 次级一。", "2. 次级二。"],
                        "合理推论": ["1. 推论一。", "2. 推论二。"],
                        "需进一步研究讨论的结论": ["1. 待验证一。", "2. 待验证二。"],
                    },
                    ensure_ascii=False,
                ),
                "contribution": ["贡献一。", "贡献二。"],
                "limitations": '{"论文自身局限":["1. 局限一。","2. 局限二。"],"证据边界":["1. 边界一。"]}',
                "reproducibility": '{"可复现内容":"可复核逻辑链。","不可复现内容":"缺少数值模型参数。"}',
                "relation": "已有工作关系，涉及粒子注入和焦热。",
                "final_conclusion": "最终结论",
                "relation_to_my_work": "间接相关",
                "follow_up_questions": ["如何验证？", "如何定量化？"],
                "needs_manual_review": "需要复核",
                "knowledge_position": "位置",
            }

            normalized = engine._normalize_ollama_deep_read_payload(payload)

            self.assertIn("硬结论：\n1. 硬结论一。\n2. 硬结论二。", normalized["key_results"])
            self.assertIn("证据边界：\n1. 边界一。", normalized["limitations"])
            self.assertIn("可复现内容：\n可复核逻辑链。", normalized["reproducibility"])
            self.assertIn("1. 如何验证？", normalized["follow_up_questions"])
            self.assertIn("太阳风-磁层（S-M）发电机", normalized["why"])
            self.assertIn("焦耳热", normalized["relation"])
            self.assertTrue(normalized["one_sentence_overview"].startswith("这篇文章通过"))
            self.assertNotIn('{"硬结论"', normalized["key_results"])
            self.assertNotIn("[", normalized["limitations"])

    def test_ollama_deep_read_evidence_parser_repairs_markdown_bullet_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            raw = """{
  "research_problem": ["研究问题"],
  "introduction_gap": ["引言空白"],
- "method_chain": ["方法链"],
  "hard_findings": ["硬结论一", "硬结论二"],
  "secondary_findings": ["次级结论"],
  "reasonable_inferences": ["合理推论"],
  "open_questions": ["待验证问题"],
  "contribution_points": ["贡献"],
  "limitations": ["局限"],
  "reproducibility_notes": ["复现线索"],
  "relation_to_my_work_evidence": ["间接相关"],
  "manual_review_points": ["复核图表"]
}"""

            payload = _parse_structured_output(
                "ollama_api",
                raw,
                schema=engine._ollama_deep_read_evidence_schema_v2(),
            )

            self.assertEqual(payload["method_chain"], ["方法链"])
            self.assertEqual(payload["hard_findings"], ["硬结论一", "硬结论二"])

    def test_ollama_deep_read_evidence_parser_drops_bare_array_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            raw = """{
  "research_problem": ["研究问题"],
  "introduction_gap": ["引言空白"],
  "method_chain": ["方法链"],
  "hard_findings": [
    "硬结论一",
    ually,
    "硬结论二"
  ],
  "secondary_findings": ["次级结论"],
  "reasonable_inferences": ["合理推论"],
  "open_questions": ["待验证问题"],
  "contribution_points": ["贡献"],
  "limitations": ["局限"],
  "reproducibility_notes": ["复现线索"],
  "relation_to_my_work_evidence": ["间接相关"],
  "manual_review_points": ["复核图表"]
}"""

            payload = _parse_structured_output(
                "ollama_api",
                raw,
                schema=engine._ollama_deep_read_evidence_schema_v2(),
            )

            self.assertEqual(payload["hard_findings"], ["硬结论一", "硬结论二"])

    def test_ollama_deep_read_final_parser_repairs_fence_latex_and_object_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            raw = r'''```json
{
  "chinese_title": "中文题目",
  "tags": ["对象/辐射带", "方法/机器学习", "指数/Dst"],
  "paper_type": "研究论文",
  "one_sentence_overview": "本文识别辐射带电子通量下降的关键驱动因子。",
  "why": "作者要解决的问题是：解释电子通量 $\le$ 阈值时的控制因素。",
  "how": "方法结合机器学习和事件分析。",
  "key_results": {
    "硬结论": ["通量变化与 $\Delta T$ 有关。", "控制参数包含 $\kappa$。"],
    "次级结论": ["模型稳定性需要复核。"]
  },
  "contribution": ["给出可解释特征排序。"],
  "limitations": {"论文自身局限": ["样本边界需要复核。"]},
  "reproducibility": "可复核方法链。",
  "relation": "与空间天气扰动研究间接相关。",
  "final_conclusion": "结论需要结合图表复核。",
  "relation_to_my_work": "间接相关。",
  "follow_up_questions": ["哪些事件最敏感？"],
  "needs_manual_review": ["复核公式 $\xi$ 和图表。"],
  "knowledge_position": "机器学习归因案例。"
}
```'''

            payload = _parse_structured_output("ollama_api", raw, schema=engine._deep_read_schema())
            normalized = engine._normalize_ollama_deep_read_payload(payload)

            self.assertIn("硬结论：\n1. 通量变化与", normalized["key_results"])
            self.assertIn("\\Delta", normalized["key_results"])
            self.assertIn("论文自身局限：\n1. 样本边界需要复核。", normalized["limitations"])
            self.assertIn("1. 哪些事件最敏感？", normalized["follow_up_questions"])
            self.assertIn("\\xi", normalized["needs_manual_review"])

    def test_ollama_deep_read_structured_retry_runs_after_unrepairable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            schema = {
                "name": "sample_schema",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }
            calls: list[tuple[str, str]] = []

            def fake_run(prompt, schema_arg, name):
                calls.append((name, prompt))
                if len(calls) == 1:
                    raise AnalysisProviderInvalidOutput(
                        "ollama_api",
                        request_name=name,
                        detail="still broken",
                        raw_preview='{"body": "unterminated',
                    )
                return {"body": "ok"}

            with mock.patch.object(engine, "_run_ollama_structured", side_effect=fake_run):
                payload = engine._run_ollama_deep_read_structured_with_repair(
                    "bad prompt",
                    schema,
                    "deep_read_sample",
                    stage="final",
                    retry_prompt="strict retry prompt",
                )

            self.assertEqual(payload["body"], "ok")
            self.assertEqual(calls[0], ("deep_read_sample", "bad prompt"))
            self.assertEqual(calls[1], ("deep_read_sample_json_retry", "strict retry prompt"))

    def test_ollama_deep_read_revision_invalid_json_keeps_final_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "ollama_api"
            engine.config["provider"] = "ollama_api"
            calls: list[str] = []

            def fake_run(prompt, schema, name):
                calls.append(name)
                if name.startswith("deep_read_evidence_v2_"):
                    return {
                        "research_problem": ["问题1", "问题2"],
                        "introduction_gap": ["空白1", "空白2"],
                        "method_chain": ["方法1", "方法2"],
                        "hard_findings": ["硬结论1", "硬结论2"],
                        "secondary_findings": ["次级1", "次级2"],
                        "reasonable_inferences": ["推论1", "推论2"],
                        "open_questions": ["问题1", "问题2"],
                        "contribution_points": ["贡献1", "贡献2"],
                        "limitations": ["局限1", "全文抽取缺损"],
                        "reproducibility_notes": ["复现1", "复现2"],
                        "relation_to_my_work_evidence": "间接相关。",
                        "manual_review_points": "需要复核图表和抽取缺损。",
                    }
                if name.startswith("deep_read_revision_"):
                    raise AnalysisProviderInvalidOutput(
                        "ollama_api",
                        request_name=name,
                        detail="broken revision json",
                    )
                return {
                    "chinese_title": "初稿题目",
                    "tags": ["对象/磁层", "事件/亚暴"],
                    "paper_type": "理论论文",
                    "one_sentence_overview": "短。",
                    "why": "短。",
                    "how": "短。",
                    "key_results": "硬结论：\n1. 一个结论。",
                    "contribution": "短。",
                    "limitations": "短。",
                    "reproducibility": "短。",
                    "relation": "短。",
                    "final_conclusion": "短。",
                    "relation_to_my_work": "直接相关。可用于热层密度和卫星阻力。",
                    "follow_up_questions": "短。",
                    "needs_manual_review": "短。",
                    "knowledge_position": "短。",
                }

            with mock.patch.object(engine, "_run_ollama_structured", side_effect=fake_run):
                result = engine.analyze_deep_read(
                    {"title": "Revision Failure", "journal": "JGR: Space Physics", "doi": "10.1000/revision-failure"},
                    "Introduction\nThis paper identifies a gap.\n2. Results\nThe paper reports results.",
                )

            self.assertIsNotNone(result)
            self.assertTrue(any(name.startswith("deep_read_revision_") for name in calls))
            self.assertIn("Ollama 修订阶段结构化输出无效", result.needs_manual_review)
            self.assertIn("间接相关", result.relation_to_my_work)

    def test_codex_deep_read_does_not_use_ollama_quality_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "codex_local"
            engine.config["provider"] = "codex_local"
            payload = {
                "chinese_title": "中文题目",
                "tags": ["对象/磁层", "事件/磁暴", "仪器/GNSS"],
                "paper_type": "研究论文",
                "one_sentence_overview": "一句话概述",
                "why": "为什么做",
                "how": "如何做",
                "key_results": "硬结论：\n1. 结果",
                "contribution": "贡献",
                "limitations": "局限",
                "reproducibility": "可复现性",
                "relation": "已有工作关系",
                "final_conclusion": "最终结论",
                "relation_to_my_work": "间接相关",
                "follow_up_questions": "问题",
                "needs_manual_review": "需要复核",
                "knowledge_position": "位置",
            }

            with mock.patch.object(engine, "_run_codex_structured", return_value=payload) as codex_run, mock.patch.object(
                engine,
                "_build_ollama_deep_read_final_prompt_v2",
                side_effect=AssertionError("Codex must not call Ollama-only prompt"),
            ) as ollama_prompt:
                result = engine.analyze_deep_read(
                    {"title": "Codex Example", "journal": "JGR: Space Physics", "doi": "10.1000/codex"},
                    "Introduction\nThis paper identifies a gap.\n2. Data\nThe paper uses data and reports results.",
                )

            self.assertIsNotNone(result)
            codex_run.assert_called_once()
            ollama_prompt.assert_not_called()

    def test_ollama_quality_mode_revises_sparse_or_overstated_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "ollama_api"
            engine.config["provider"] = "ollama_api"
            calls: list[str] = []

            def fake_run(prompt, schema, name):
                calls.append(name)
                if name.startswith("deep_read_evidence_v2_"):
                    return {
                        "research_problem": ["问题1", "问题2"],
                        "introduction_gap": ["空白1", "空白2"],
                        "method_chain": ["方法1", "方法2"],
                        "hard_findings": ["硬结论1", "硬结论2"],
                        "secondary_findings": ["次级1", "次级2"],
                        "reasonable_inferences": ["推论1", "推论2"],
                        "open_questions": ["问题1", "问题2"],
                        "contribution_points": ["贡献1", "贡献2"],
                        "limitations": ["局限1", "全文抽取缺损"],
                        "reproducibility_notes": ["复现1", "复现2"],
                        "relation_to_my_work_evidence": "间接相关。",
                        "manual_review_points": "需要复核图表和抽取缺损。",
                    }
                if name.startswith("deep_read_revision_"):
                    return {
                        "chinese_title": "修订题目",
                        "tags": ["对象/磁层", "事件/亚暴", "理论/电路模型"],
                        "paper_type": "理论论文",
                        "one_sentence_overview": "这篇文章给出机制框架，需要按证据边界理解。",
                        "why": "作者要解决的问题是：解释亚暴能量链条。",
                        "how": "1. 方法一。\n2. 方法二。\n3. 方法三。",
                        "key_results": (
                            "硬结论：\n1. 硬结论一。\n2. 硬结论二。\n"
                            "次级结论：\n1. 次级一。\n2. 次级二。\n"
                            "合理推论：\n1. 推论一。\n2. 推论二。\n"
                            "需进一步研究讨论的结论：\n1. 待验证一。\n2. 待验证二。"
                        ),
                        "contribution": "1. 贡献一。\n2. 贡献二。",
                        "limitations": "1. 理论边界。\n2. 全文抽取缺损。\n3. 缺少定量判据。",
                        "reproducibility": "可复现性有限，需要复核逻辑链条和公式定义。",
                        "relation": "与已有亚暴机制研究相关。",
                        "final_conclusion": "该文是机制框架，不是定量预报模型。",
                        "relation_to_my_work": "间接相关。可作为空间天气背景。",
                        "follow_up_questions": ["如何验证？", "如何定量化？"],
                        "needs_manual_review": "需要人工复核图表、公式、抽取缺损和争议性解释。",
                        "knowledge_position": "理论机制背景。",
                    }
                return {
                    "chinese_title": "初稿题目",
                    "tags": ["对象/磁层", "事件/亚暴"],
                    "paper_type": "理论论文",
                    "one_sentence_overview": "短。",
                    "why": "短。",
                    "how": "短。",
                    "key_results": "硬结论：\n1. 一个结论。",
                    "contribution": "短。",
                    "limitations": "短。",
                    "reproducibility": "短。",
                    "relation": "短。",
                    "final_conclusion": "短。",
                    "relation_to_my_work": "直接相关。可用于热层密度和卫星阻力。",
                    "follow_up_questions": "短。",
                    "needs_manual_review": "短。",
                    "knowledge_position": "短。",
                }

            with mock.patch.object(engine, "_run_ollama_structured", side_effect=fake_run):
                result = engine.analyze_deep_read(
                    {"title": "Revision Example", "journal": "JGR: Space Physics", "doi": "10.1000/revision"},
                    "Introduction\nThis paper identifies a gap.\n2. Results\nThe paper reports results.",
                )

            self.assertIsNotNone(result)
            self.assertEqual(len(calls), 3)
            self.assertTrue(calls[-1].startswith("deep_read_revision_"))
            self.assertIn("间接相关", result.relation_to_my_work)
            self.assertIn("1. 如何验证？", result.follow_up_questions)

    def test_ollama_deep_read_quality_mode_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "ollama_api"
            engine.config["provider"] = "ollama_api"
            engine.config["ollama_api"]["deep_read_quality_mode"] = False
            calls: list[str] = []

            def fake_run(prompt, schema, name):
                calls.append(name)
                return {
                    "chinese_title": "中文题目",
                    "tags": ["对象/磁层", "事件/磁暴", "仪器/GNSS"],
                    "paper_type": "研究论文",
                    "one_sentence_overview": "一句话概述",
                    "why": "为什么做",
                    "how": "如何做",
                    "key_results": "硬结论：\n1. 结果",
                    "contribution": "贡献",
                    "limitations": "局限",
                    "reproducibility": "可复现性",
                    "relation": "已有工作关系",
                    "final_conclusion": "最终结论",
                    "relation_to_my_work": "间接相关",
                    "follow_up_questions": "问题",
                    "needs_manual_review": "无",
                    "knowledge_position": "位置",
                }

            with mock.patch.object(engine, "_run_ollama_structured", side_effect=fake_run):
                result = engine.analyze_deep_read(
                    {"title": "Example", "journal": "JGR: Space Physics", "doi": "10.1000/example-disabled"},
                    "Introduction\nThis paper identifies a gap.\n2. Data\nThe paper uses data and reports results.",
                )

            self.assertIsNotNone(result)
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0].startswith("deep_read_"))
            self.assertFalse(calls[0].startswith("deep_read_evidence_"))

    def test_run_ollama_structured_extracts_fenced_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
            }

            class FakeResponse:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "message": {"content": "```json\n{\"body\":\"ok\"}\n```"},
                            "prompt_eval_count": 12,
                            "eval_count": 8,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")

            schema = {
                "name": "sample_schema",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }
            with mock.patch("sciencemonitor.llm_api_support.request.urlopen", return_value=FakeResponse()):
                payload = engine._run_ollama_structured("prompt", schema, "sample_fenced")

            self.assertEqual(payload["body"], "ok")

    def test_run_ollama_structured_repairs_invalid_latex_backslash_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
            }

            class FakeResponse:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "message": {"content": '{"body":"power $\\epsilon$ and energy $\\W$"}'},
                            "prompt_eval_count": 12,
                            "eval_count": 8,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")

            schema = {
                "name": "sample_schema",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }
            with mock.patch("sciencemonitor.llm_api_support.request.urlopen", return_value=FakeResponse()):
                payload = engine._run_ollama_structured("prompt", schema, "deep_read_latex_escape")

            self.assertIn("\\epsilon", payload["body"])

    def test_run_ollama_structured_repairs_trailing_commas_before_closing_arrays(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
            }

            class FakeResponse:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "message": {
                                "content": '{\n  "items": [\n    "one",\n    "two",\n  ],\n  "body": "ok"\n}'
                            },
                            "prompt_eval_count": 12,
                            "eval_count": 8,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")

            schema = {
                "name": "sample_schema",
                "schema": {
                    "type": "object",
                    "properties": {"items": {"type": "array", "items": {"type": "string"}}, "body": {"type": "string"}},
                    "required": ["items", "body"],
                    "additionalProperties": False,
                },
            }
            with mock.patch("sciencemonitor.llm_api_support.request.urlopen", return_value=FakeResponse()):
                payload = engine._run_ollama_structured("prompt", schema, "deep_read_evidence_v2_trailing_comma")

            self.assertEqual(payload["items"], ["one", "two"])
            self.assertEqual(payload["body"], "ok")

    def test_run_ollama_structured_repairs_missing_opening_quote_on_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
            }

            class FakeResponse:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "message": {
                                "content": '{\n  "body": "ok",\n  _open_questions": [\n    "how to validate?"\n  ]\n}'
                            },
                            "prompt_eval_count": 12,
                            "eval_count": 8,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")

            schema = {
                "name": "sample_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "body": {"type": "string"},
                        "_open_questions": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["body", "_open_questions"],
                    "additionalProperties": False,
                },
            }
            with mock.patch("sciencemonitor.llm_api_support.request.urlopen", return_value=FakeResponse()):
                payload = engine._run_ollama_structured("prompt", schema, "deep_read_evidence_v2_bad_key_quote")

            self.assertEqual(payload["body"], "ok")
            self.assertEqual(payload["_open_questions"], ["how to validate?"])

    def test_run_ollama_structured_converts_timeout_for_ui_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
            }
            schema = {
                "name": "sample_schema",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }

            with mock.patch(
                "sciencemonitor.llm.run_ollama_structured",
                side_effect=TimeoutError("ollama_api request timed out after 9s"),
            ):
                with self.assertRaises(AnalysisProviderTimeout) as ctx:
                    engine._run_ollama_structured("prompt", schema, "article_timeout")

            self.assertEqual(ctx.exception.provider, "ollama_api")
            self.assertEqual(ctx.exception.timeout_seconds, 9)
            self.assertEqual(ctx.exception.request_name, "article_timeout")
            self.assertIn("Ollama 本地模型", ctx.exception.ui_message())

    def test_run_ollama_structured_converts_invalid_json_for_article_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
            }
            schema = {
                "name": "sample_schema",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }

            class FakeResponse:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "message": {"content": '{"body": "broken'},
                            "prompt_eval_count": 12,
                            "eval_count": 8,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")

            with mock.patch("sciencemonitor.llm_api_support.request.urlopen", return_value=FakeResponse()):
                with self.assertRaises(AnalysisProviderInvalidOutput) as ctx:
                    engine._run_ollama_structured("prompt", schema, "article_invalid_json")

            self.assertEqual(ctx.exception.provider, "ollama_api")
            self.assertEqual(ctx.exception.request_name, "article_invalid_json")
            self.assertIn("Unterminated string", ctx.exception.detail)
            self.assertIn("结构化 JSON", ctx.exception.ui_message())
            self.assertIsNotNone(ctx.exception.detail_path)
            self.assertTrue(ctx.exception.detail_path.exists())
            self.assertIn('"body": "broken', ctx.exception.detail_path.read_text(encoding="utf-8"))

    def test_run_ollama_structured_converts_empty_content_to_diagnostic_invalid_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
                "keep_alive": 0,
            }
            schema = {
                "name": "sample_schema",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }

            class FakeResponse:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "model": "gemma4:26b",
                            "message": {"role": "assistant", "content": ""},
                            "done": True,
                            "done_reason": "load",
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")

            with mock.patch("sciencemonitor.llm_api_support.request.urlopen", return_value=FakeResponse()):
                with self.assertRaises(AnalysisProviderInvalidOutput) as ctx:
                    engine._run_ollama_structured("prompt", schema, "deep_read_empty")

            self.assertEqual(ctx.exception.provider, "ollama_api")
            self.assertIn("empty structured text content", ctx.exception.detail)
            self.assertIsNotNone(ctx.exception.detail_path)
            saved = ctx.exception.detail_path.read_text(encoding="utf-8")
            self.assertIn('"done_reason": "load"', saved)

    def test_run_ollama_structured_repairs_common_deep_read_field_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
                "keep_alive": 0,
            }
            response_payload = {
                "chinese_und_title": "极光亚暴作为一种电学放电现象",
                "tags": ["事件/亚暴", "对象/磁层"],
                "paper_type": "理论研究",
                "one_sentence_overview": "一句话总述",
                "why": "为什么做",
                "how": "如何做",
                "key_results": "硬结论：\n1. 结果",
                "contribution": "贡献",
                "limitations": "局限",
                "reproducibility": "可复现性",
                "relation": "关系",
                "final_conclusion": "结论",
                "relation_to_my_work": "间接相关",
                "follow_up_questions": "问题",
                "needs_manual_review": "需要复核",
                "knowledge_position": "知识位置",
            }

            class FakeResponse:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "message": {"content": json.dumps(response_payload, ensure_ascii=False)},
                            "prompt_eval_count": 12,
                            "eval_count": 8,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")

            with mock.patch("sciencemonitor.llm_api_support.request.urlopen", return_value=FakeResponse()):
                payload = engine._run_ollama_structured("prompt", engine._deep_read_schema(), "deep_read_alias")

            self.assertEqual(payload["chinese_title"], "极光亚暴作为一种电学放电现象")

    def test_run_ollama_structured_repairs_deep_read_follow_up_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.config["ollama_api"] = {
                "model": "gemma4:26b",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "timeout_seconds": 9,
                "keep_alive": 0,
            }
            response_payload = {
                "chinese_title": "区分赤道热层异常中的密度与风扰动",
                "tags": ["对象/热层/ETA", "仪器/CHAMP"],
                "paper_type": "研究论文",
                "one_sentence_overview": "一句话总述",
                "why": "为什么做",
                "how": "如何做",
                "key_results": "硬结论：\n1. 结果",
                "contribution": "贡献",
                "limitations": "局限",
                "reproducibility": "可复现性",
                "relation": "关系",
                "final_conclusion": "结论",
                "relation_to_my_work": "间接相关",
                "follow_up_args": "1. 如何用多星座验证 ADA？",
                "needs_manual_review": "需要复核",
                "knowledge_position": "知识位置",
            }

            class FakeResponse:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

                def read(self) -> bytes:
                    return json.dumps(
                        {
                            "message": {"content": json.dumps(response_payload, ensure_ascii=False)},
                            "prompt_eval_count": 12,
                            "eval_count": 8,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8")

            with mock.patch("sciencemonitor.llm_api_support.request.urlopen", return_value=FakeResponse()):
                payload = engine._run_ollama_structured(
                    "prompt",
                    engine._deep_read_schema(),
                    "deep_read_revision_alias",
                )

            self.assertEqual(payload["follow_up_questions"], "1. 如何用多星座验证 ADA？")

    def test_provider_status_checks_ollama_only_when_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "codex_local"
            engine.config["provider"] = "codex_local"

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
