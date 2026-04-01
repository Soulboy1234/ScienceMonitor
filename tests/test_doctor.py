from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.doctor import run_doctor


class DoctorTest(unittest.TestCase):
    def test_reports_skills_are_not_runtime_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
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
            report = run_doctor(root)
            self.assertFalse(report["skills_runtime_dependency"])
            self.assertIn("provider", report["provider_status"])


if __name__ == "__main__":
    unittest.main()
