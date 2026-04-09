from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.harness_audit import run_harness_audit
from sciencemonitor.harness_optimize import run_harness_optimize


class HarnessAuditTest(unittest.TestCase):
    def test_audit_reports_missing_public_harness_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write_common_structure(root)
            (root / "README.md").write_text("`./scripts/run_science_monitor.sh harness-check`\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("`./scripts/run_science_monitor.sh harness-check`\n", encoding="utf-8")
            (root / "docs" / "user_guides" / "harness_governance_overview.md").write_text(
                "## Harness\n`harness-check`\n",
                encoding="utf-8",
            )
            (root / "docs" / "user_guides" / "release_checklist.md").write_text(
                "./scripts/run_science_monitor.sh harness-check\n",
                encoding="utf-8",
            )
            (root / "docs" / "user_guides" / "python_module_map.md").write_text(
                "harness.py\n",
                encoding="utf-8",
            )
            report = run_harness_audit(root, write_report=False)
            self.assertFalse(report.passed)
            self.assertTrue(any("README" in item.area for item in report.findings))
            self.assertTrue(any("AGENTS" in item.area for item in report.findings))

    def test_optimize_repairs_doc_surface_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write_common_structure(root)
            (root / "README.md").write_text(
                "./scripts/run_science_monitor.sh maintenance-check --auto-repair\n"
                "./scripts/run_science_monitor.sh harness-check\n",
                encoding="utf-8",
            )
            (root / "AGENTS.md").write_text(
                "./scripts/run_science_monitor.sh harness-check\n"
                "docs/user_guides/harness_governance_overview.md\n",
                encoding="utf-8",
            )
            (root / "docs" / "user_guides" / "harness_governance_overview.md").write_text(
                "### 2. `harness-check`\n./scripts/run_science_monitor.sh harness-check\n"
                "- `doctor`：环境与配置是否可运行\n"
                "- `harness-check`：治理链路是否整体健康\n"
                "- `maintenance-check`：把以上内容收成“审核 -> 调整 -> 测试 -> 再审核”\n"
                "- `harness-check` 是治理 gate\n"
                "- `maintenance-check` 是维护循环\n",
                encoding="utf-8",
            )
            (root / "docs" / "user_guides" / "release_checklist.md").write_text(
                "### Harness gate\n\n```bash\n./scripts/run_science_monitor.sh harness-check\n```\n",
                encoding="utf-8",
            )
            (root / "docs" / "user_guides" / "python_module_map.md").write_text(
                "- [harness.py](../../src/sciencemonitor/harness.py)\n"
                "  统一 harness gate。\n",
                encoding="utf-8",
            )

            before = run_harness_audit(root, write_report=False)
            optimized = run_harness_optimize(root, write_report=False)
            after = optimized.after_audit

            self.assertGreater(len(before.findings), 0)
            self.assertTrue(optimized.improved)
            self.assertEqual(len(after.findings), 0)

    def _write_common_structure(self, root: pathlib.Path) -> None:
        (root / "docs" / "user_guides").mkdir(parents=True, exist_ok=True)
        (root / "src" / "sciencemonitor").mkdir(parents=True, exist_ok=True)
        (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("", encoding="utf-8")
        (root / "AGENTS.md").write_text("", encoding="utf-8")
        (root / "src" / "sciencemonitor" / "cli_support.py").write_text(
            'add_parser("harness-audit")\nadd_parser("harness-optimize")\n',
            encoding="utf-8",
        )
        (root / "src" / "sciencemonitor" / "harness.py").write_text(
            "from .harness_audit import run_harness_audit\nharness_audit = run_harness_audit\n",
            encoding="utf-8",
        )
        (root / ".github" / "workflows" / "ci.yml").write_text(
            "./scripts/run_science_monitor.sh harness-check\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
