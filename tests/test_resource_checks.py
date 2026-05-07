from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.resource_checks import render_resource_check_summary, resolve_test_tmpdir, run_resource_precheck


class ResourceChecksTest(unittest.TestCase):
    def test_resolve_test_tmpdir_prefers_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            override = pathlib.Path(tmpdir) / "custom"
            with mock.patch.dict("os.environ", {"SCIENCEMONITOR_TEST_TMPDIR": str(override)}):
                self.assertEqual(resolve_test_tmpdir(ROOT), override)

    def test_resource_precheck_reports_low_disk_without_creating_tempdir(self) -> None:
        usage = shutil_usage(total=100, used=95, free=5)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            target = root / "missing" / "pytest"
            with mock.patch.dict("os.environ", {"SCIENCEMONITOR_TEST_TMPDIR": str(target)}), mock.patch(
                "sciencemonitor.resource_checks.shutil.disk_usage",
                return_value=usage,
            ):
                report = run_resource_precheck(root, min_free_mb=1)
        self.assertFalse(report.passed)
        self.assertFalse(target.exists())
        summary = render_resource_check_summary(report)
        self.assertIn("overall=failed", summary)
        self.assertIn("可用磁盘空间不足", summary)


def shutil_usage(*, total: int, used: int, free: int):
    return type("usage", (), {"total": total, "used": used, "free": free})()


if __name__ == "__main__":
    unittest.main()
