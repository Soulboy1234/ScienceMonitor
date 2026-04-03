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

from sciencemonitor.entropy import run_entropy_check


class EntropyCheckTest(unittest.TestCase):
    def test_entropy_check_accepts_budgeted_modules_and_allowed_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "src" / "sciencemonitor"
            source_root.mkdir(parents=True, exist_ok=True)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (source_root / "__init__.py").write_text("", encoding="utf-8")
            (source_root / "a.py").write_text("from .b import ping\n\ndef alpha():\n    return ping()\n", encoding="utf-8")
            (source_root / "b.py").write_text("from .a import alpha\n\ndef ping():\n    return 'ok'\n", encoding="utf-8")
            (root / "config" / "maintenance_budget.json").write_text(
                json.dumps(
                    {
                        "global_limits": {
                            "default_module_max_lines": 20,
                            "default_function_max_lines": 10,
                            "package_total_max_lines": 50,
                        },
                        "allowed_import_cycles": [["a", "b"]],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_entropy_check(root)
            self.assertTrue(report.passed)
            self.assertFalse(report.issues)

    def test_entropy_check_detects_growth_and_unapproved_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "src" / "sciencemonitor"
            source_root.mkdir(parents=True, exist_ok=True)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (source_root / "__init__.py").write_text("", encoding="utf-8")
            (source_root / "a.py").write_text(
                "from .b import ping\n\n"
                "def alpha():\n"
                "    x = 1\n"
                "    y = 2\n"
                "    z = 3\n"
                "    return ping() + str(x + y + z)\n",
                encoding="utf-8",
            )
            (source_root / "b.py").write_text("from .a import alpha\n\ndef ping():\n    return 'ok'\n", encoding="utf-8")
            (root / "config" / "maintenance_budget.json").write_text(
                json.dumps(
                    {
                        "global_limits": {
                            "default_module_max_lines": 4,
                            "default_function_max_lines": 3,
                            "package_total_max_lines": 8,
                        },
                        "allowed_import_cycles": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_entropy_check(root)
            self.assertFalse(report.passed)
            categories = {issue.category for issue in report.issues}
            self.assertIn("module_lines", categories)
            self.assertIn("function_lines", categories)
            self.assertIn("import_cycle", categories)


if __name__ == "__main__":
    unittest.main()
