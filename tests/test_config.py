from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.config import (
    data_root,
    llm_cache_root,
    load_master_plan_preferences,
    load_research_preferences_config,
    logs_root,
    output_root,
)
from sciencemonitor.config import (
    collect_project_config_sync_drift,
    load_runtime_config,
    project_config_markdown_path,
    sync_configs_from_project_markdown,
    write_project_config_markdown,
)


class ConfigOverrideTest(unittest.TestCase):
    def test_state_root_override_moves_data_and_log_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir) / "project"
            root.mkdir()
            state = pathlib.Path(tmpdir) / "state"
            old_state = os.environ.get("SCIENCEMONITOR_STATE_ROOT")
            old_data = os.environ.get("SCIENCEMONITOR_DATA_ROOT")
            old_log = os.environ.get("SCIENCEMONITOR_LOG_ROOT")
            try:
                os.environ["SCIENCEMONITOR_STATE_ROOT"] = str(state)
                os.environ.pop("SCIENCEMONITOR_DATA_ROOT", None)
                os.environ.pop("SCIENCEMONITOR_LOG_ROOT", None)
                self.assertEqual(data_root(root), (state / "data").resolve())
                self.assertEqual(logs_root(root), (state / "log").resolve())
                self.assertEqual(llm_cache_root(root), (state / "data" / "llm_cache").resolve())
            finally:
                if old_state is None:
                    os.environ.pop("SCIENCEMONITOR_STATE_ROOT", None)
                else:
                    os.environ["SCIENCEMONITOR_STATE_ROOT"] = old_state
                if old_data is None:
                    os.environ.pop("SCIENCEMONITOR_DATA_ROOT", None)
                else:
                    os.environ["SCIENCEMONITOR_DATA_ROOT"] = old_data
                if old_log is None:
                    os.environ.pop("SCIENCEMONITOR_LOG_ROOT", None)
                else:
                    os.environ["SCIENCEMONITOR_LOG_ROOT"] = old_log

    def test_explicit_data_and_log_overrides_take_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir) / "project"
            root.mkdir()
            state = pathlib.Path(tmpdir) / "state"
            data = pathlib.Path(tmpdir) / "custom-data"
            logs = pathlib.Path(tmpdir) / "custom-log"
            old_state = os.environ.get("SCIENCEMONITOR_STATE_ROOT")
            old_data = os.environ.get("SCIENCEMONITOR_DATA_ROOT")
            old_log = os.environ.get("SCIENCEMONITOR_LOG_ROOT")
            try:
                os.environ["SCIENCEMONITOR_STATE_ROOT"] = str(state)
                os.environ["SCIENCEMONITOR_DATA_ROOT"] = str(data)
                os.environ["SCIENCEMONITOR_LOG_ROOT"] = str(logs)
                self.assertEqual(data_root(root), data.resolve())
                self.assertEqual(logs_root(root), logs.resolve())
                self.assertEqual(llm_cache_root(root), data.resolve() / "llm_cache")
            finally:
                if old_state is None:
                    os.environ.pop("SCIENCEMONITOR_STATE_ROOT", None)
                else:
                    os.environ["SCIENCEMONITOR_STATE_ROOT"] = old_state
                if old_data is None:
                    os.environ.pop("SCIENCEMONITOR_DATA_ROOT", None)
                else:
                    os.environ["SCIENCEMONITOR_DATA_ROOT"] = old_data
                if old_log is None:
                    os.environ.pop("SCIENCEMONITOR_LOG_ROOT", None)
                else:
                    os.environ["SCIENCEMONITOR_LOG_ROOT"] = old_log

    def test_output_root_can_be_loaded_from_relative_paths_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir)
            root = workspace / "Documents" / "codex" / "ScienceMonitor"
            configured_output = workspace / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents" / "AI" / "ScienceMonitorOut"
            (root / "config").mkdir(parents=True)
            (root / "config" / "paths.json").write_text(
                json.dumps(
                    {
                        "output_root": "../../../Library/Mobile Documents/iCloud~md~obsidian/Documents/AI/ScienceMonitorOut"
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(output_root(root), configured_output.resolve())

    def test_output_root_env_override_takes_precedence_over_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = pathlib.Path(tmpdir)
            root = workspace / "project"
            override_output = workspace / "override-output"
            (root / "config").mkdir(parents=True)
            (root / "config" / "paths.json").write_text(
                json.dumps({"output_root": "configured-output"}),
                encoding="utf-8",
            )
            old_output = os.environ.get("SCIENCEMONITOR_OUTPUT_ROOT")
            try:
                os.environ["SCIENCEMONITOR_OUTPUT_ROOT"] = str(override_output)
                self.assertEqual(output_root(root), override_output.resolve())
            finally:
                if old_output is None:
                    os.environ.pop("SCIENCEMONITOR_OUTPUT_ROOT", None)
                else:
                    os.environ["SCIENCEMONITOR_OUTPUT_ROOT"] = old_output

    def test_load_runtime_config_creates_default_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir) / "project"
            (root / "config").mkdir(parents=True)
            runtime = load_runtime_config(root)
            self.assertEqual(runtime["cli_defaults"]["report_window_days"], 7)
            self.assertTrue((root / "config" / "runtime.json").exists())

    def test_write_project_config_markdown_creates_sync_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir) / "project"
            (root / "config").mkdir(parents=True)
            (root / "config" / "analysis.json").write_text(
                json.dumps({"provider": "codex_local"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "config" / "paths.json").write_text(
                json.dumps({"output_root": "ScienceMonitorOut"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            path = write_project_config_markdown(root)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(path, project_config_markdown_path(root))
            self.assertIn("## Sync: config/runtime.json", text)
            self.assertIn("## Sync: config/analysis.json", text)
            self.assertIn("## Sync: config/paths.json", text)
            self.assertIn("## Sync: config/research_preferences.json", text)
            self.assertIn("### 当前研究重心", text)

    def test_sync_configs_from_project_markdown_updates_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir) / "project"
            (root / "config").mkdir(parents=True)
            (root / "config" / "analysis.json").write_text(
                json.dumps({"provider": "codex_local"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "config" / "paths.json").write_text(
                json.dumps({"output_root": "ScienceMonitorOut"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            write_project_config_markdown(root)
            markdown_path = project_config_markdown_path(root)
            text = markdown_path.read_text(encoding="utf-8")
            text = text.replace(
                '"report_window_days": 7',
                '"report_window_days": 14',
                1,
            )
            text = text.replace(
                '"provider": "codex_local"',
                '"provider": "openai_api"',
                1,
            )
            text = text.replace(
                '"output_root": "ScienceMonitorOut"',
                '"output_root": "CustomOut"',
                1,
            )
            markdown_path.write_text(text, encoding="utf-8")
            updated = sync_configs_from_project_markdown(root)
            self.assertEqual(load_runtime_config(root)["cli_defaults"]["report_window_days"], 14)
            self.assertEqual(
                json.loads((root / "config" / "analysis.json").read_text(encoding="utf-8"))["provider"],
                "openai_api",
            )
            self.assertEqual(
                json.loads((root / "config" / "paths.json").read_text(encoding="utf-8"))["output_root"],
                "CustomOut",
            )
            self.assertEqual(len(updated), 4)

    def test_sync_configs_from_project_markdown_updates_research_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir) / "project"
            (root / "config").mkdir(parents=True)
            (root / "config" / "analysis.json").write_text(
                json.dumps({"provider": "codex_local"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "config" / "paths.json").write_text(
                json.dumps({"output_root": "ScienceMonitorOut"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            write_project_config_markdown(root)
            markdown_path = project_config_markdown_path(root)
            text = markdown_path.read_text(encoding="utf-8")
            text = text.replace("- 热层密度及其变化机制", "- 电离层不规则体与闪烁", 1)
            text = text.replace("- 主领域：space_physics", "- 主领域：artificial_intelligence", 1)
            text = text.replace("- 允许相关学科：是", "- 允许相关学科：否", 1)
            text = text.replace("- 优先相关学科：artificial_intelligence", "- 优先相关学科：machine_learning, data_assimilation", 1)
            markdown_path.write_text(text, encoding="utf-8")

            updated = sync_configs_from_project_markdown(root)
            preferences = load_research_preferences_config(root)

            self.assertIn(root / "config" / "research_preferences.json", updated)
            self.assertIn("电离层不规则体与闪烁", preferences["research_focus"])
            self.assertEqual(preferences["deep_read_scope"]["primary_domain"], "artificial_intelligence")
            self.assertFalse(preferences["deep_read_scope"]["allow_related_disciplines"])
            self.assertEqual(
                preferences["deep_read_scope"]["preferred_related_disciplines"],
                ["machine_learning", "data_assimilation"],
            )

    def test_load_master_plan_preferences_reads_config_research_preferences_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir) / "project"
            (root / "config").mkdir(parents=True)
            (root / "config" / "research_preferences.json").write_text(
                json.dumps(
                    {
                        "research_focus": ["热层密度"],
                        "priority_alerts": ["卫星影响"],
                        "priority_article_signals": ["orbit decay"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            profile = load_master_plan_preferences(root)
            self.assertIn("热层密度", profile.research_focus)
            self.assertIn("卫星影响", profile.priority_alerts)
            self.assertIn("orbit decay", profile.priority_alerts)

    def test_load_master_plan_preferences_falls_back_to_legacy_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir) / "project"
            (root / "config").mkdir(parents=True)
            (root / "config" / "research_preferences.md").write_text(
                "\n".join(
                    [
                        "# Research Preferences",
                        "",
                        "## 当前用户研究重心",
                        "- 热层密度",
                        "",
                        "## 文献调研中的特别提醒策略",
                        "- 卫星影响",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            profile = load_master_plan_preferences(root)
            self.assertIn("热层密度", profile.research_focus)
            self.assertIn("卫星影响", profile.priority_alerts)

    def test_collect_project_config_sync_drift_detects_research_preferences_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir) / "project"
            (root / "config").mkdir(parents=True)
            (root / "config" / "analysis.json").write_text(
                json.dumps({"provider": "codex_local"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "config" / "paths.json").write_text(
                json.dumps({"output_root": "ScienceMonitorOut"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            write_project_config_markdown(root)
            sync_configs_from_project_markdown(root)
            (root / "config" / "research_preferences.json").write_text(
                json.dumps({"research_focus": ["已漂移"]}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            issues = collect_project_config_sync_drift(root)

            self.assertTrue(any("research_preferences.json 与 PROJECT_CONFIG.md 的研究偏好同步段不一致" in item for item in issues))


if __name__ == "__main__":
    unittest.main()
