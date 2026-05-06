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
    candidate_review_report_path,
    filter_tag_candidates,
    render_tag_candidates_report,
    write_tag_candidates_report,
)
from sciencemonitor.tag_governance import (
    merge_tags_into_formal,
    promote_selected_pending_tags,
    reconcile_output_markdown_tags,
    refresh_pending_tag_files,
    resolve_existing_output_tag,
    sync_formal_tags_to_focus_tags_json,
)


class TagCandidatesTest(unittest.TestCase):
    def test_render_report_uses_pending_tag_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "data").mkdir()
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

            self.assertEqual(candidate_log_path(root), root / "config" / "pending_tags.json")
            self.assertEqual(candidate_review_report_path(root), root / "config" / "tag" / "pending_tags.md")
            filtered = filter_tag_candidates(root, min_count=2, limit=10)
            self.assertEqual([item.tag for item in filtered], [])

            markdown = render_tag_candidates_report(root, min_count=2, limit=10)
            self.assertIn("# 预选标签", markdown)
            self.assertIn("当前没有待审核的预选标签。", markdown)
            self.assertNotIn("新的候选标签", markdown)
            self.assertNotIn("一次性标签", markdown)

    def test_write_report_creates_markdown_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "data").mkdir()
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
            self.assertEqual(report_path, root / "config" / "tag" / "pending_tags.md")
            self.assertIn("当前没有待审核的预选标签。", report_path.read_text(encoding="utf-8"))

    def test_promote_checked_pending_tag_updates_formal_and_removes_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            sync_formal_tags_to_focus_tags_json(root)
            write_tag_candidates_report(root)
            pending_path = root / "config" / "tag" / "pending_tags.md"
            pending_json_path = root / "config" / "pending_tags.json"
            (root / "out" / "auto" / "article_summaries" / "sample.md").write_text(
                "- 标签： #新的候选标签\n",
                encoding="utf-8",
            )
            pending_json_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "description": "pending",
                        "tags": {
                            "新的候选标签": {
                                "category": "application_impact",
                                "count": 2,
                                "first_seen": "2026-04-02T00:00:00Z",
                                "last_seen": "2026-04-02T09:00:00Z",
                                "contexts": {"deep_read": 2},
                                "selected": False,
                                "usage_count": 1,
                                "usage_by_kind": {"article_summaries": 1, "deep_reads": 0},
                            }
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            write_tag_candidates_report(root)
            pending_path.write_text(
                pending_path.read_text(encoding="utf-8").replace("[ ] 新的候选标签", "[x] 新的候选标签"),
                encoding="utf-8",
            )

            result = promote_selected_pending_tags(root)

            self.assertEqual(result.promoted_tags, ["新的候选标签"])
            focus_payload = json.loads((root / "config" / "focus_tags.json").read_text(encoding="utf-8"))
            self.assertIn("新的候选标签", {item["label"] for item in focus_payload["tags"]})
            pending_payload = json.loads(pending_json_path.read_text(encoding="utf-8"))
            self.assertNotIn("新的候选标签", pending_payload["tags"])
            self.assertNotIn("新的候选标签", pending_path.read_text(encoding="utf-8"))

    def test_pending_markdown_renders_full_paths_sorted_by_usage_without_group_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "pending_tags.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "description": "pending",
                        "tags": {
                            "太阳与日球层/ParkerAlpha": {
                                "category": "research_object",
                                "count": 4,
                                "first_seen": "2026-04-02T00:00:00Z",
                                "last_seen": "2026-04-02T09:00:00Z",
                                "contexts": {"article_summary": 4},
                                "selected": False,
                                "usage_count": 4,
                                "usage_by_kind": {"article_summaries": 4, "deep_reads": 0},
                            },
                            "太阳与日球层/ICMEAlpha": {
                                "category": "research_object",
                                "count": 2,
                                "first_seen": "2026-04-02T00:00:00Z",
                                "last_seen": "2026-04-02T09:00:00Z",
                                "contexts": {"article_summary": 2},
                                "selected": True,
                                "usage_count": 2,
                                "usage_by_kind": {"article_summaries": 2, "deep_reads": 0},
                            },
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "out" / "auto" / "article_summaries" / "a.md").write_text(
                "- 标签： #太阳与日球层/ParkerAlpha\n",
                encoding="utf-8",
            )
            (root / "out" / "auto" / "article_summaries" / "b.md").write_text(
                "- 标签： #太阳与日球层/ParkerAlpha #太阳与日球层/ICMEAlpha\n",
                encoding="utf-8",
            )
            (root / "out" / "auto" / "article_summaries" / "c.md").write_text(
                "- 标签： #太阳与日球层/ParkerAlpha #太阳与日球层/ICMEAlpha\n",
                encoding="utf-8",
            )
            (root / "out" / "auto" / "article_summaries" / "d.md").write_text(
                "- 标签： #太阳与日球层/ParkerAlpha\n",
                encoding="utf-8",
            )

            report_path = write_tag_candidates_report(root)
            markdown = report_path.read_text(encoding="utf-8")

            self.assertIn("- [ ] 太阳与日球层/ParkerAlpha （4次）", markdown)
            self.assertIn("- [x] 太阳与日球层/ICMEAlpha （2次）", markdown)
            self.assertNotIn("（分组）", markdown)
            self.assertLess(markdown.index("太阳与日球层/ParkerAlpha"), markdown.index("太阳与日球层/ICMEAlpha"))

    def test_merge_tags_into_formal_adds_parent_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            merged = merge_tags_into_formal(root, ["测试父/测试子/测试孙"])

            self.assertIn("测试父", merged)
            self.assertIn("测试父/测试子", merged)
            self.assertIn("测试父/测试子/测试孙", merged)
            focus_payload = json.loads((root / "config" / "focus_tags.json").read_text(encoding="utf-8"))
            labels = {item["label"] for item in focus_payload["tags"]}
            self.assertIn("测试父", labels)
            self.assertIn("测试父/测试子", labels)
            self.assertIn("测试父/测试子/测试孙", labels)
            formal_markdown = (root / "config" / "tag" / "formal_tags.md").read_text(encoding="utf-8")
            self.assertIn("- 测试父", formal_markdown)
            self.assertIn("- 测试孙", formal_markdown)
            self.assertNotIn("`测试父`", formal_markdown)

    def test_merge_tags_into_formal_preserves_existing_markdown_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "tag" / "formal_tags.md").write_text(
                "\n".join(
                    [
                        "# 正式标签",
                        "",
                        "## 研究对象",
                        "- 对象",
                        "  - 电离层",
                        "  - 热层",
                        "    - 风场",
                        "    - 密度",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            merge_tags_into_formal(root, ["对象/热层/温度"])

            formal_markdown = (root / "config" / "tag" / "formal_tags.md").read_text(encoding="utf-8")
            self.assertIn("\t- 电离层", formal_markdown)
            self.assertIn("\t- 热层", formal_markdown)
            self.assertIn("\t\t- 风场", formal_markdown)
            self.assertLess(formal_markdown.index("\t- 电离层"), formal_markdown.index("\t- 热层"))
            self.assertLess(formal_markdown.index("\t\t- 风场"), formal_markdown.index("\t\t- 密度"))
            self.assertLess(formal_markdown.index("\t\t- 密度"), formal_markdown.index("\t\t- 温度"))
            self.assertNotIn("  - 电离层", formal_markdown)

    def test_sync_formal_tags_accepts_tab_indentation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "tag" / "formal_tags.md").write_text(
                "\n".join(
                    [
                        "# 正式标签",
                        "",
                        "## 研究对象",
                        "- 对象",
                        "\t- 热层",
                        "\t\t- 风场",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            sync_formal_tags_to_focus_tags_json(root)

            focus_payload = json.loads((root / "config" / "focus_tags.json").read_text(encoding="utf-8"))
            labels = {item["label"] for item in focus_payload["tags"]}
            self.assertIn("对象", labels)
            self.assertIn("对象/热层", labels)
            self.assertIn("对象/热层/风场", labels)

    def test_sync_formal_tags_keeps_tab_indented_siblings_at_same_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "tag" / "formal_tags.md").write_text(
                "\n".join(
                    [
                        "# 正式标签",
                        "",
                        "## 指数 / 控制量",
                        "\t- 指数",
                        "\t\t- IMF",
                        "\t\t\t- Bx",
                        "\t\t\t- By",
                        "\t\t\t- Bz",
                        "\t\t- Dst",
                        "\t\t- Kp",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            sync_formal_tags_to_focus_tags_json(root)

            focus_payload = json.loads((root / "config" / "focus_tags.json").read_text(encoding="utf-8"))
            labels = {item["label"] for item in focus_payload["tags"]}
            self.assertIn("指数/IMF/Bx", labels)
            self.assertIn("指数/IMF/By", labels)
            self.assertIn("指数/IMF/Bz", labels)
            self.assertIn("指数/Dst", labels)
            self.assertIn("指数/Kp", labels)
            self.assertNotIn("指数/IMF/Bx/By", labels)
            self.assertNotIn("指数/IMF/Dst", labels)

    def test_sync_formal_tags_accepts_short_category_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "tag" / "formal_tags.md").write_text(
                "\n".join(
                    [
                        "# 正式标签",
                        "",
                        "## 事件",
                        "- 事件",
                        "  - 磁暴",
                        "",
                        "## 指数",
                        "- 指数",
                        "  - Dst",
                        "",
                        "## 应用",
                        "- 应用",
                        "  - 预测",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            sync_formal_tags_to_focus_tags_json(root)

            focus_payload = json.loads((root / "config" / "focus_tags.json").read_text(encoding="utf-8"))
            labels = {item["label"] for item in focus_payload["tags"]}
            self.assertIn("事件/磁暴", labels)
            self.assertIn("指数/Dst", labels)
            self.assertIn("应用/预测", labels)

    def test_sync_formal_tags_strips_ai_summary_suffix_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "tag" / "formal_tags.md").write_text(
                "\n".join(
                    [
                        "# 正式标签",
                        "",
                        "## 研究对象",
                        "- 对象",
                        "  - 测试标签【AI总结】",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            sync_formal_tags_to_focus_tags_json(root)

            payload = json.loads((root / "config" / "focus_tags.json").read_text(encoding="utf-8"))
            labels = {item["label"] for item in payload["tags"]}
            self.assertIn("对象/测试标签", labels)
            self.assertNotIn("对象/测试标签【AI总结】", labels)

    def test_merge_tags_into_formal_reassigns_existing_slash_tags_by_parent_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "tag" / "formal_tags.md").write_text(
                "\n".join(
                    [
                        "# 正式标签",
                        "",
                        "## 研究对象",
                        "- 太阳风",
                        "  - 高速流",
                        "- 磁暴",
                        "  - 恢复相",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            merge_tags_into_formal(root, [])

            focus_payload = json.loads((root / "config" / "focus_tags.json").read_text(encoding="utf-8"))
            category_by_label = {item["label"]: item["category"] for item in focus_payload["tags"]}
            self.assertEqual(category_by_label["太阳风"], "event_driver")
            self.assertEqual(category_by_label["太阳风/高速流"], "event_driver")
            self.assertEqual(category_by_label["磁暴"], "event_driver")
            self.assertEqual(category_by_label["磁暴/恢复相"], "event_driver")

    def test_resolve_existing_output_tag_prefers_alias_before_suffix_fallback(self) -> None:
        formal = {
            "对象/重力波",
            "对象/潮汐",
            "对象/日地耦合",
            "对象/热层/风场",
            "仪器/MMS",
        }
        self.assertEqual(resolve_existing_output_tag("重力波/潮汐", formal), ["对象/重力波", "对象/潮汐"])
        self.assertEqual(resolve_existing_output_tag("日地耦合", formal), ["对象/日地耦合"])
        self.assertEqual(resolve_existing_output_tag("卫星/MMS", formal), ["仪器/MMS"])
        self.assertEqual(resolve_existing_output_tag("热层/风", formal), ["对象/热层/风场"])

    def test_reconcile_output_markdown_tags_rewrites_formal_mappable_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = pathlib.Path(tmpdir)
            path = base / "sample.md"
            path.write_text(
                "- [DOI](https://doi.org/10.1000/example) #磁暴 #热层/密度 #研究星球/地球 #卫星/MMS #重力波/潮汐\n",
                encoding="utf-8",
            )

            result = reconcile_output_markdown_tags(
                base,
                formal_labels={
                    "事件/磁暴",
                    "对象/热层/密度",
                    "仪器/MMS",
                    "对象/重力波",
                    "对象/潮汐",
                },
            )

            self.assertEqual(result.scanned_files, 1)
            self.assertEqual(len(result.modified_entries), 1)
            rewritten = path.read_text(encoding="utf-8")
            self.assertIn("#事件/磁暴", rewritten)
            self.assertIn("#对象/热层/密度", rewritten)
            self.assertIn("#仪器/MMS", rewritten)
            self.assertIn("#对象/重力波", rewritten)
            self.assertIn("#对象/潮汐", rewritten)
            self.assertIn("#研究星球/地球", rewritten)
            self.assertEqual(result.remaining_nonformal_counts, {"研究星球/地球": 1})

    def test_refresh_pending_tag_files_seeds_nonformal_tags_from_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            sync_formal_tags_to_focus_tags_json(root)
            (root / "out" / "auto" / "article_summaries" / "sample.md").write_text(
                "- 标签： #研究星球/地球 #事件/磁暴\n",
                encoding="utf-8",
            )

            refresh_pending_tag_files(root)

            pending_payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))
            self.assertIn("研究星球/地球", pending_payload["tags"])
            self.assertNotIn("事件/磁暴", pending_payload["tags"])

    def test_refresh_pending_tag_files_drops_tags_that_can_be_mapped_to_formal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "tag" / "formal_tags.md").write_text(
                "\n".join(
                    [
                        "# 正式标签",
                        "",
                        "## 应用与工具",
                        "- 应用",
                        "  - 空间天气",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            sync_formal_tags_to_focus_tags_json(root)
            (root / "config" / "pending_tags.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "description": "pending",
                        "tags": {
                            "空间天气": {
                                "category": "application_impact",
                                "count": 3,
                                "first_seen": "",
                                "last_seen": "",
                                "contexts": {},
                                "selected": False,
                                "usage_count": 0,
                                "usage_by_kind": {"article_summaries": 0, "deep_reads": 0},
                            }
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "out" / "auto" / "article_summaries" / "sample.md").write_text(
                "- 标签： #应用/空间天气\n",
                encoding="utf-8",
            )

            refresh_pending_tag_files(root)

            pending_payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))
            self.assertNotIn("空间天气", pending_payload["tags"])

    def test_refresh_pending_tag_files_drops_zero_usage_pending_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "config" / "pending_tags.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "description": "pending",
                        "tags": {
                            "历史候选标签": {
                                "category": "research_object",
                                "count": 5,
                                "first_seen": "2026-04-02T00:00:00Z",
                                "last_seen": "2026-04-02T09:00:00Z",
                                "contexts": {"article_summary": 5},
                                "selected": False,
                                "usage_count": 0,
                                "usage_by_kind": {"article_summaries": 0, "deep_reads": 0},
                            }
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            refresh_pending_tag_files(root)

            pending_payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))
            self.assertEqual(pending_payload["tags"], {})
            markdown = (root / "config" / "tag" / "pending_tags.md").read_text(encoding="utf-8")
            self.assertIn("当前没有待审核的预选标签。", markdown)

    def test_promote_selected_pending_tags_applies_review_actions_and_ai_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            sync_formal_tags_to_focus_tags_json(root)
            (root / "config" / "pending_tags.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "description": "pending",
                        "tags": {
                            "对象/测试行星环境": {
                                "category": "research_object",
                                "family": "it_coupling_extensions",
                                "count": 1,
                                "first_seen": "",
                                "last_seen": "",
                                "contexts": {},
                                "selected": False,
                                "note": "",
                                "usage_count": 1,
                                "usage_by_kind": {"article_summaries": 1, "deep_reads": 0},
                            },
                            "对象/测试长尾地球": {
                                "category": "research_object",
                                "family": "it_coupling_extensions",
                                "count": 1,
                                "first_seen": "",
                                "last_seen": "",
                                "contexts": {},
                                "selected": False,
                                "note": "",
                                "usage_count": 1,
                                "usage_by_kind": {"article_summaries": 1, "deep_reads": 0},
                            },
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "config" / "tag" / "pending_tags.md").write_text(
                "\n".join(
                    [
                        "# 预选标签",
                        "",
                        "## C. 电离层-热层-耦合扩展家族",
                        "- [x] 对象/测试行星环境 （1次）",
                        "- [ ] 对象/测试长尾地球 （1次） - 删除",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            kept = root / "out" / "auto" / "article_summaries" / "kept.md"
            dropped = root / "out" / "auto" / "article_summaries" / "dropped.md"
            kept.write_text("- 标签： #对象/测试行星环境\n", encoding="utf-8")
            dropped.write_text("- 标签： #对象/测试长尾地球\n", encoding="utf-8")

            result = promote_selected_pending_tags(root)

            self.assertEqual(result.promoted_tags, ["对象/测试行星环境"])
            self.assertTrue(kept.exists())
            self.assertIn("#对象/测试行星环境", kept.read_text(encoding="utf-8"))
            self.assertTrue(dropped.exists())
            self.assertIn(dropped, result.protected_files)
            self.assertNotIn("#对象/测试长尾地球", dropped.read_text(encoding="utf-8"))
            formal_markdown = (root / "config" / "tag" / "formal_tags.md").read_text(encoding="utf-8")
            self.assertIn("测试行星环境【AI总结】", formal_markdown)
            payload = json.loads((root / "config" / "focus_tags.json").read_text(encoding="utf-8"))
            labels = {item["label"] for item in payload["tags"]}
            self.assertIn("对象/测试行星环境", labels)
            self.assertNotIn("对象/测试行星环境【AI总结】", labels)
            pending_payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))
            self.assertNotIn("对象/测试行星环境", pending_payload["tags"])
            self.assertNotIn("对象/测试长尾地球", pending_payload["tags"])

    def test_promote_selected_pending_tags_supports_note_targets_and_preserves_question_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir()
            (root / "config" / "tag").mkdir(parents=True, exist_ok=True)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True, exist_ok=True)
            (root / "config" / "focus_tags.json").write_text(
                (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            sync_formal_tags_to_focus_tags_json(root)
            (root / "config" / "pending_tags.json").write_text(
                json.dumps(
                    {
                        "version": 2,
                        "description": "pending",
                        "tags": {
                            "对象/源标签A": {
                                "category": "research_object",
                                "family": "it_coupling_extensions",
                                "count": 1,
                                "first_seen": "",
                                "last_seen": "",
                                "contexts": {},
                                "selected": False,
                                "note": "",
                                "usage_count": 1,
                                "usage_by_kind": {"article_summaries": 1, "deep_reads": 0},
                            },
                            "对象/源标签B": {
                                "category": "research_object",
                                "family": "it_coupling_extensions",
                                "count": 1,
                                "first_seen": "",
                                "last_seen": "",
                                "contexts": {},
                                "selected": False,
                                "note": "",
                                "usage_count": 1,
                                "usage_by_kind": {"article_summaries": 1, "deep_reads": 0},
                            },
                            "对象/源标签C": {
                                "category": "research_object",
                                "family": "it_coupling_extensions",
                                "count": 1,
                                "first_seen": "",
                                "last_seen": "",
                                "contexts": {},
                                "selected": False,
                                "note": "",
                                "usage_count": 1,
                                "usage_by_kind": {"article_summaries": 1, "deep_reads": 0},
                            },
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "config" / "tag" / "pending_tags.md").write_text(
                "\n".join(
                    [
                        "# 预选标签",
                        "",
                        "## C. 电离层-热层-耦合扩展家族",
                        "- [ ] 对象/源标签A （1次）- 对象/热层",
                        "- [ ] 对象/源标签B （1次）对象/太阳",
                        "- [ ] 对象/源标签C （1次）- 具体是什么？",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "out" / "auto" / "article_summaries" / "a.md").write_text("- 标签： #对象/源标签A\n", encoding="utf-8")
            (root / "out" / "auto" / "article_summaries" / "b.md").write_text("- 标签： #对象/源标签B\n", encoding="utf-8")
            (root / "out" / "auto" / "article_summaries" / "c.md").write_text("- 标签： #对象/源标签C\n", encoding="utf-8")

            promote_selected_pending_tags(root)

            self.assertIn("#对象/热层", (root / "out" / "auto" / "article_summaries" / "a.md").read_text(encoding="utf-8"))
            self.assertIn("#对象/太阳", (root / "out" / "auto" / "article_summaries" / "b.md").read_text(encoding="utf-8"))
            self.assertIn("#对象/源标签C", (root / "out" / "auto" / "article_summaries" / "c.md").read_text(encoding="utf-8"))

            pending_payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))
            self.assertNotIn("对象/源标签A", pending_payload["tags"])
            self.assertNotIn("对象/源标签B", pending_payload["tags"])
            self.assertIn("对象/源标签C", pending_payload["tags"])
            self.assertNotIn("对象/太阳", pending_payload["tags"])


if __name__ == "__main__":
    unittest.main()
