from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
import json

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.config import sync_configs_from_project_markdown, write_project_config_markdown
from sciencemonitor.doctor import run_doctor


def _write_doctor_project(root: pathlib.Path) -> None:
    (root / "config" / "templates").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir()
    (root / "log").mkdir()
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    (root / "config" / "analysis.json").write_text(
        (ROOT / "config" / "analysis.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "config" / "focus_tags.json").write_text(
        (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for name in (
        "article_summary_template.md",
        "daily_report_template.md",
        "deep_reading_report_template.md",
    ):
        (root / "config" / "templates" / name).write_text(
            (ROOT / "config" / "templates" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    write_project_config_markdown(root)
    sync_configs_from_project_markdown(root)


class DoctorTest(unittest.TestCase):
    def test_reports_consistency_checks_for_valid_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_doctor_project(root)
            report = run_doctor(root)
            self.assertFalse(report["skills_runtime_dependency"])
            self.assertIn("provider", report["provider_status"])
            statuses = {item["id"]: item["status"] for item in report["consistency_checks"]}
            self.assertEqual(statuses["project_config_sync"], "ok")
            self.assertEqual(statuses["research_preferences"], "ok")
            self.assertEqual(statuses["article_summary_template"], "ok")
            self.assertEqual(statuses["daily_report_template"], "ok")
            self.assertEqual(statuses["deep_reading_report_template"], "ok")
            self.assertEqual(statuses["focus_tags"], "ok")

    def test_warns_when_runtime_template_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_doctor_project(root)
            (root / "config" / "templates" / "deep_reading_report_template.md").unlink()

            report = run_doctor(root)
            checks = {item["id"]: item for item in report["consistency_checks"]}

            self.assertEqual(checks["deep_reading_report_template"]["status"], "warning")
            self.assertTrue(any("缺少模板文件" in issue for issue in checks["deep_reading_report_template"]["issues"]))
            self.assertTrue(any("深度解读模板" in item for item in report["warnings"]))

    def test_warns_when_research_preferences_shape_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_doctor_project(root)
            (root / "config" / "research_preferences.json").write_text(
                json.dumps({"research_focus": "热层密度"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            report = run_doctor(root)
            checks = {item["id"]: item for item in report["consistency_checks"]}

            self.assertEqual(checks["research_preferences"]["status"], "warning")
            self.assertTrue(any("research_focus 必须是列表" in issue for issue in checks["research_preferences"]["issues"]))
            self.assertTrue(any("研究偏好配置" in item for item in report["warnings"]))

    def test_consistency_only_skips_runtime_environment_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_doctor_project(root)

            report = run_doctor(root, strict_runtime=False)

            self.assertFalse(any("PATH 首项不是 .venv/bin" in item for item in report["warnings"]))
            self.assertFalse(any("当前解释器不是项目 .venv/bin/python" in item for item in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
