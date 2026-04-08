from __future__ import annotations

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

from sciencemonitor.llm import AnalysisEngine
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

            self.assertIn("电离层/低纬", tags)
            self.assertIn("磁层", tags)
            self.assertIn("指数/ROTI", tags)
            self.assertIn("仪器/射电/S波段", tags)
            self.assertIn("仪器/月球重力场模型", tags)
            self.assertIn("电离层/电子密度", tags)

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

            self.assertIn("热层/风场", tags)
            self.assertIn("热层/密度", tags)
            self.assertIn("热层/成分", tags)
            self.assertIn("热层/温度", tags)

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

            self.assertIn("极区/对流边界", tags)
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
            self.assertIn("其他行星/月球", tags)

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
            self.assertNotEqual(key_a, key_b)
            self.assertNotEqual(key_a, key_c)

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


if __name__ == "__main__":
    unittest.main()
