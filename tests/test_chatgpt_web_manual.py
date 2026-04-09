from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.chatgpt_web_manual import (
    ManualResponsePending,
    import_manual_response,
    import_manual_response_from_recommended_file,
    list_manual_requests,
)
from sciencemonitor.llm import AnalysisEngine


class ChatGPTWebManualTest(unittest.TestCase):
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

    def test_manual_provider_creates_request_bundle_then_uses_imported_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "chatgpt_web_manual"
            schema = {
                "name": "sample",
                "schema": {
                    "type": "object",
                    "properties": {
                        "body": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2},
                    },
                    "required": ["body", "tags"],
                    "additionalProperties": False,
                },
            }

            with self.assertRaises(ManualResponsePending) as exc:
                engine._run_structured(
                    "请输出结构化结果。",
                    schema,
                    "sample_request",
                    reasoning_effort="medium",
                    manual_context={
                        "request_kind": "article_summary",
                        "title": "Sample Paper",
                        "request_label": "sample_paper",
                        "resource_hints": {"title": "Sample Paper", "doi": "10.1234/sample"},
                    },
                )

            bundle = exc.exception.bundle
            self.assertTrue(bundle.request_dir.exists())
            self.assertTrue(bundle.prompt_path.exists())
            self.assertFalse((bundle.request_dir / "schema.json").exists())
            self.assertFalse((bundle.request_dir / "response_template.json").exists())
            self.assertFalse((bundle.request_dir / "context").exists())
            self.assertFalse((bundle.request_dir / "attachments").exists())
            self.assertTrue(bundle.response_filename.startswith("ScienceMonitor_sample_paper_article_summary_"))
            prompt_text = bundle.prompt_path.read_text(encoding="utf-8")
            self.assertIn("创建一个可下载 JSON 文件", prompt_text)
            self.assertIn(bundle.response_filename, prompt_text)
            self.assertIn("不要在聊天正文里展开完整 JSON", prompt_text)
            self.assertNotIn("第一个字符必须是", prompt_text)
            first_metadata = json.loads((bundle.request_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(first_metadata["request_label"], "sample_paper")
            self.assertEqual(first_metadata["response_filename"], bundle.response_filename)

            import_manual_response(
                root,
                request_id="sample_request",
                response_text='{"body":"ok","tags":["热层/密度"]}',
            )

            payload = engine._run_structured(
                "请输出结构化结果。",
                schema,
                "sample_request",
                reasoning_effort="medium",
                manual_context={"request_kind": "article_summary", "title": "Sample Paper"},
            )
            self.assertEqual(payload["body"], "ok")
            self.assertEqual(payload["tags"], ["热层/密度"])
            second_metadata = json.loads((bundle.request_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(second_metadata["request_label"], "sample_paper")
            self.assertEqual(second_metadata["response_filename"], bundle.response_filename)

    def test_manual_provider_accepts_direct_json_saved_under_recommended_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "chatgpt_web_manual"
            schema = {
                "name": "sample",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }

            with self.assertRaises(ManualResponsePending) as exc:
                engine._run_structured(
                    "请输出结构化结果。",
                    schema,
                    "direct_json_request",
                    manual_context={
                        "request_kind": "deep_read",
                        "title": "Direct JSON Paper",
                        "request_label": "direct_json_paper",
                    },
                )
            bundle = exc.exception.bundle
            bundle.response_json_path.write_text('{"body":"direct ok"}\n', encoding="utf-8")

            payload = engine._run_structured(
                "请输出结构化结果。",
                schema,
                "direct_json_request",
                manual_context={
                    "request_kind": "deep_read",
                    "title": "Direct JSON Paper",
                    "request_label": "direct_json_paper",
                },
            )
            self.assertEqual(payload["body"], "direct ok")

    def test_import_from_recommended_file_wraps_downloaded_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "chatgpt_web_manual"
            schema = {
                "name": "sample",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }

            with self.assertRaises(ManualResponsePending) as exc:
                engine._run_structured(
                    "请输出结构化结果。",
                    schema,
                    "downloaded_json_request",
                    manual_context={
                        "request_kind": "article_summary",
                        "title": "Downloaded JSON Paper",
                        "request_label": "downloaded_json_paper",
                    },
                )
            bundle = exc.exception.bundle
            bundle.response_json_path.write_text('{"body":"downloaded ok"}\n', encoding="utf-8")

            result = import_manual_response_from_recommended_file(root, request_id="downloaded_json_request")
            self.assertEqual(result.response_json_path, bundle.response_json_path)

            payload = engine._run_structured(
                "请输出结构化结果。",
                schema,
                "downloaded_json_request",
                manual_context={
                    "request_kind": "article_summary",
                    "title": "Downloaded JSON Paper",
                    "request_label": "downloaded_json_paper",
                },
            )
            self.assertEqual(payload["body"], "downloaded ok")

    def test_list_manual_requests_reports_pending_and_ready_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._prepare_root(tmpdir)
            engine = AnalysisEngine(root)
            engine.provider = "chatgpt_web_manual"
            schema = {
                "name": "sample",
                "schema": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
            }

            with self.assertRaises(ManualResponsePending):
                engine._run_structured(
                    "first",
                    schema,
                    "pending_request",
                    manual_context={"request_kind": "article_summary", "title": "Pending Paper"},
                )
            with self.assertRaises(ManualResponsePending):
                engine._run_structured(
                    "second",
                    schema,
                    "ready_request",
                    manual_context={"request_kind": "deep_read", "title": "Ready Paper"},
                )
            import_manual_response(root, request_id="ready_request", response_text='{"body":"done"}')

            statuses = {item.request_id: item for item in list_manual_requests(root, limit=0)}
            self.assertEqual(statuses["pending_request"].status, "pending")
            self.assertEqual(statuses["ready_request"].status, "ready")
            self.assertTrue(statuses["ready_request"].response_filename.endswith(".json"))


if __name__ == "__main__":
    unittest.main()
