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

from sciencemonitor.tag_governance import ensure_tag_governance_files
from sciencemonitor.tag_governance_review import run_tag_governance_review


class TagGovernanceReviewTest(unittest.TestCase):
    def test_tag_governance_review_passes_for_synced_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            ensure_tag_governance_files(root, refresh_pending=True)
            report = run_tag_governance_review(root)
            self.assertTrue(report.passed)
            self.assertEqual(report.issues, [])

    def test_tag_governance_review_detects_usage_count_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            ensure_tag_governance_files(root, refresh_pending=True)
            pending_path = root / "config" / "pending_tags.json"
            payload = json.loads(pending_path.read_text(encoding="utf-8"))
            payload["tags"]["新的候选标签"] = {
                "category": "research_object",
                "family": "it_coupling_extensions",
                "count": 2,
                "first_seen": "2026-04-11T00:00:00Z",
                "last_seen": "2026-04-11T00:00:00Z",
                "contexts": {"deep_read": 2},
                "selected": False,
                "note": "",
                "usage_count": 5,
                "usage_by_kind": {"article_summaries": 5, "deep_reads": 0},
            }
            pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report = run_tag_governance_review(root)
            self.assertFalse(report.passed)
            self.assertTrue(any(item.category == "usage_count_drift" for item in report.issues))

    def test_tag_governance_review_auto_syncs_when_formal_markdown_is_newer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            ensure_tag_governance_files(root, refresh_pending=True)
            formal_path = root / "config" / "tag" / "formal_tags.md"
            formal_path.write_text(
                "\n".join(
                    [
                        "# 正式标签",
                        "",
                        "## 应用",
                        "- 应用",
                        "  - 预测",
                        "  - 自定义测试标签",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            focus_path = root / "config" / "focus_tags.json"
            focus_stat = focus_path.stat()
            os.utime(formal_path, ns=(focus_stat.st_atime_ns, focus_stat.st_mtime_ns + 5_000_000))

            report = run_tag_governance_review(root)

            self.assertTrue(report.passed)
            payload = json.loads(focus_path.read_text(encoding="utf-8"))
            labels = {item["label"] for item in payload["tags"]}
            self.assertIn("应用/自定义测试标签", labels)

    def test_tag_governance_review_syncs_combined_formal_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            ensure_tag_governance_files(root, refresh_pending=True)
            formal_path = root / "config" / "tag" / "formal_tags.md"
            formal_path.write_text(
                "\n".join(
                    [
                        "# 正式标签",
                        "",
                        "## 应用与工具",
                        "- 应用",
                        "  - 空间天气",
                        "  - 预测",
                        "- 工具",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            focus_path = root / "config" / "focus_tags.json"
            focus_stat = focus_path.stat()
            os.utime(formal_path, ns=(focus_stat.st_atime_ns, focus_stat.st_mtime_ns + 5_000_000))

            report = run_tag_governance_review(root)

            self.assertTrue(report.passed)
            payload = json.loads(focus_path.read_text(encoding="utf-8"))
            by_label = {item["label"]: item for item in payload["tags"]}
            self.assertEqual(by_label["应用"]["category"], "application_impact")
            self.assertEqual(by_label["应用/空间天气"]["category"], "application_impact")
            self.assertEqual(by_label["应用/预测"]["category"], "application_impact")
            self.assertEqual(by_label["工具"]["category"], "model_method")

    def test_tag_governance_review_still_detects_drift_when_json_is_newer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            ensure_tag_governance_files(root, refresh_pending=True)
            focus_path = root / "config" / "focus_tags.json"
            payload = json.loads(focus_path.read_text(encoding="utf-8"))
            payload["tags"] = [item for item in payload["tags"] if item.get("label") != "综述"]
            focus_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            report = run_tag_governance_review(root)

            self.assertFalse(report.passed)
            self.assertTrue(any(item.category == "formal_drift" for item in report.issues))


if __name__ == "__main__":
    unittest.main()
