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
            self.assertIn("GNSS/ROTI", tags)
            self.assertIn("射电/S波段", tags)
            self.assertIn("月球/重力场", tags)
            self.assertIn("电子密度", tags)

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

            self.assertIn("热层/风", tags)
            self.assertIn("热层/密度", tags)
            self.assertIn("热层/成分", tags)
            self.assertIn("热层/温度", tags)

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
                    "saturnian",
                    "Uranus",
                ]
            )

            self.assertIn("研究星球/地球", tags)
            self.assertIn("研究星球/月球", tags)
            self.assertIn("研究星球/土星", tags)
            self.assertIn("研究星球/天王星", tags)


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


if __name__ == "__main__":
    unittest.main()
