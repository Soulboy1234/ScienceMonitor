from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.test_runner import run_pytest_suite


class TestRunnerTest(unittest.TestCase):
    def test_run_pytest_suite_clears_path_overrides_by_default(self) -> None:
        captured_env: dict[str, str] = {}

        def fake_run(*args, **kwargs):
            captured_env.update(kwargs["env"])
            return mock.Mock(returncode=0, stdout="ok", stderr="")

        with mock.patch.dict(
            "os.environ",
            {
                "SCIENCEMONITOR_OUTPUT_ROOT": "out",
                "SCIENCEMONITOR_DATA_ROOT": "data_override",
                "SCIENCEMONITOR_LOG_ROOT": "log_override",
            },
        ), mock.patch("sciencemonitor.test_runner.subprocess.run", side_effect=fake_run):
            result = run_pytest_suite(ROOT, ("tests/test_config.py",))

        self.assertTrue(result.passed)
        self.assertNotIn("SCIENCEMONITOR_OUTPUT_ROOT", captured_env)
        self.assertNotIn("SCIENCEMONITOR_DATA_ROOT", captured_env)
        self.assertNotIn("SCIENCEMONITOR_LOG_ROOT", captured_env)
        self.assertIn("SCIENCEMONITOR_TEST_TMPDIR", captured_env)


if __name__ == "__main__":
    unittest.main()
