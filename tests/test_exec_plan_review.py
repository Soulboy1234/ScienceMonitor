from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.exec_plan_review import render_exec_plan_check_summary, run_exec_plan_check


def _write_file(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


VALID_TEMPLATE = """# 计划：示例

## 目的 / 大图景
- a

## 背景与定位
- a

## 工作范围
- a

## 非目标
- a

## 进度
- [ ] a

## 计划中的工作
- a

## 具体步骤
1. a

## 发现与意外
- a

## 决策记录
- a

## 结果与复盘
- a

## 验证
- `pytest`
"""


class ExecPlanReviewTest(unittest.TestCase):
    def test_exec_plan_check_passes_with_template_and_active_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_file(root / "config" / "templates" / "exec_plan_template.md", VALID_TEMPLATE)
            _write_file(root / "docs" / "exec_plans" / "active" / "plan.md", VALID_TEMPLATE)
            _write_file(root / "docs" / "exec_plans" / "completed" / "legacy.md", "# legacy\n")
            report = run_exec_plan_check(root)
        self.assertTrue(report.passed)
        self.assertIn("overall=ok", render_exec_plan_check_summary(report))
        self.assertIn("active_plan_status", render_exec_plan_check_summary(report))

    def test_exec_plan_check_fails_on_missing_section_in_active_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_file(root / "config" / "templates" / "exec_plan_template.md", VALID_TEMPLATE)
            _write_file(
                root / "docs" / "exec_plans" / "active" / "bad.md",
                VALID_TEMPLATE.replace("## 决策记录\n- a\n\n", ""),
            )
            report = run_exec_plan_check(root)
        self.assertFalse(report.passed)
        summary = render_exec_plan_check_summary(report)
        self.assertIn("缺少必需标题", summary)
