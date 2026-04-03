from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.golden_eval import run_golden_eval


class GoldenEvalTest(unittest.TestCase):
    def _prepare_temp_project(self, root: pathlib.Path) -> None:
        shutil.copytree(ROOT / "config", root / "config")

    def test_golden_eval_can_update_and_match_temp_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._prepare_temp_project(root)

            first = run_golden_eval(root, update=True)
            self.assertTrue(all(item.passed for item in first))
            self.assertTrue(all(item.updated for item in first))

            second = run_golden_eval(root)
            self.assertTrue(all(item.passed for item in second))
            self.assertTrue(all(not item.updated for item in second))

    def test_golden_eval_detects_fixture_drift_in_temp_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._prepare_temp_project(root)

            run_golden_eval(root, update=True)
            fixture_path = root / "evals" / "golden" / "article_summary.md"
            fixture_path.write_text("# drift\n", encoding="utf-8")

            results = run_golden_eval(root)
            failed = [item for item in results if not item.passed]
            self.assertTrue(failed)
            self.assertEqual(failed[0].name, "article_summary")
            self.assertIsNotNone(failed[0].diff_path)
            self.assertTrue(failed[0].diff_path.exists())


if __name__ == "__main__":
    unittest.main()
