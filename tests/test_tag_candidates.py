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

from sciencemonitor.tag_candidates import (
    candidate_log_path,
    filter_tag_candidates,
    render_tag_candidates_report,
    write_tag_candidates_report,
)


class TagCandidatesTest(unittest.TestCase):
    def test_render_report_uses_runtime_candidate_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "log").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "data" / "tag_candidates.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "candidates": {
                            "新的候选标签": {
                                "count": 3,
                                "first_seen": "2026-04-02T00:00:00Z",
                                "last_seen": "2026-04-02T09:00:00Z",
                                "contexts": {"deep_read": 2, "article_summary": 1},
                            },
                            "一次性标签": {
                                "count": 1,
                                "first_seen": "2026-04-02T08:00:00Z",
                                "last_seen": "2026-04-02T08:00:00Z",
                                "contexts": {"deep_read": 1},
                            },
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(candidate_log_path(root), root / "data" / "tag_candidates.json")
            filtered = filter_tag_candidates(root, min_count=2, limit=10)
            self.assertEqual([item.tag for item in filtered], ["新的候选标签"])

            markdown = render_tag_candidates_report(root, min_count=2, limit=10)
            self.assertIn("新的候选标签", markdown)
            self.assertNotIn("一次性标签", markdown)
            self.assertIn("article_summary:1, deep_read:2", markdown)

    def test_write_report_creates_markdown_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "log").mkdir()
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "data" / "tag_candidates.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "candidates": {
                            "新的候选标签": {
                                "count": 2,
                                "first_seen": "2026-04-02T00:00:00Z",
                                "last_seen": "2026-04-02T09:00:00Z",
                                "contexts": {"deep_read": 2},
                            }
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report_path = write_tag_candidates_report(root, min_count=2, limit=10)
            self.assertTrue(report_path.exists())
            self.assertIn("新的候选标签", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
