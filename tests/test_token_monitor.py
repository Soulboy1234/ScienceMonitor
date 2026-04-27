from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.token_monitor import load_token_usage_snapshot, record_api_usage


class TokenMonitorTest(unittest.TestCase):
    def test_load_token_usage_snapshot_builds_files_from_codex_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            llm_tmp = root / "log" / "llm_tmp"
            llm_tmp.mkdir(parents=True, exist_ok=True)
            (llm_tmp / "article_alpha_codex.stderr.log").write_text("tokens used\n17,554\n", encoding="utf-8")

            snapshot = load_token_usage_snapshot(root)

            self.assertEqual(snapshot["periods"]["today"]["tokens"], 17554)
            self.assertEqual(snapshot["periods"]["week"]["runs"], 1)
            self.assertEqual(snapshot["chart"]["providers"][0]["key"], "codex_local")
            self.assertEqual(snapshot["chart"]["days"][0]["date"], (date.today() - timedelta(days=27)).isoformat())
            self.assertEqual(snapshot["chart"]["days"][-1]["date"], (date.today() + timedelta(days=2)).isoformat())
            self.assertTrue((root / "log" / "token_monitor" / "codex_usage.json").exists())
            self.assertTrue((root / "log" / "token_monitor" / "daily_usage.json").exists())
            self.assertTrue((root / "log" / "token_monitor" / "latest_snapshot.json").exists())

    def test_record_api_usage_is_folded_into_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            record_api_usage(
                root,
                provider="openai_api",
                model="gpt-5-mini",
                raw_usage={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
                request_name="article_demo",
            )

            snapshot = load_token_usage_snapshot(root)
            api_events_path = root / "log" / "token_monitor" / "api_usage.jsonl"

            self.assertEqual(snapshot["periods"]["today"]["tokens"], 150)
            self.assertIn("openai_api", snapshot["providers"])
            self.assertTrue(api_events_path.exists())
            events = [json.loads(line) for line in api_events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(events[0]["total_tokens"], 150)
            self.assertEqual(events[0]["provider"], "openai_api")

    def test_record_ollama_usage_is_folded_into_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            record_api_usage(
                root,
                provider="ollama_api",
                model="gemma4:26b",
                raw_usage={"input_tokens": 40, "output_tokens": 10, "total_tokens": 50},
                request_name="article_ollama",
            )

            snapshot = load_token_usage_snapshot(root)

            self.assertEqual(snapshot["periods"]["today"]["tokens"], 50)
            self.assertIn("ollama_api", snapshot["providers"])
            chart_providers = [item["key"] for item in snapshot["chart"]["providers"]]
            self.assertIn("ollama_api", chart_providers)

    def test_load_token_usage_snapshot_rebuilds_when_schema_version_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            llm_tmp = root / "log" / "llm_tmp"
            llm_tmp.mkdir(parents=True, exist_ok=True)
            (llm_tmp / "article_alpha_codex.stderr.log").write_text("tokens used\n17,554\n", encoding="utf-8")

            stale_snapshot = root / "log" / "token_monitor" / "latest_snapshot.json"
            stale_snapshot.parent.mkdir(parents=True, exist_ok=True)
            stale_snapshot.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "generated_on": "2026-04-11",
                        "chart_days": 30,
                        "source_signature": {
                            "codex_log_count": 1,
                            "codex_latest_mtime_ns": (llm_tmp / "article_alpha_codex.stderr.log").stat().st_mtime_ns,
                            "codex_total_size": (llm_tmp / "article_alpha_codex.stderr.log").stat().st_size,
                            "api_events_exists": False,
                            "api_events_mtime_ns": 0,
                            "api_events_size": 0,
                        },
                        "summary_text": "今天 17,554 / 本周 17,554 / 本月 17,554",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            snapshot = load_token_usage_snapshot(root)

            self.assertEqual(snapshot["schema_version"], 3)
            self.assertIn("1次", str(snapshot["summary_text"]))


if __name__ == "__main__":
    unittest.main()
