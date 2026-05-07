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

from sciencemonitor.article_index import sync_out_library
from sciencemonitor.article_index_paths import resolve_note_target_path


class ArticleIndexTest(unittest.TestCase):
    def test_resolve_note_target_path_rejects_traversal_and_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            library = root / "out"
            library.mkdir()
            inside = library / "inside.md"
            inside.write_text("inside", encoding="utf-8")
            outside = root / "outside.md"
            outside.write_text("outside", encoding="utf-8")

            self.assertEqual(resolve_note_target_path("inside", library_root=library), inside.resolve())
            self.assertIsNone(resolve_note_target_path("../outside", library_root=library))
            self.assertIsNone(resolve_note_target_path(str(outside), library_root=library))

    def test_resolve_note_target_path_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            library = root / "out"
            library.mkdir()
            outside = root / "outside.md"
            outside.write_text("outside", encoding="utf-8")
            link = library / "link.md"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symlink not supported")

            self.assertIsNone(resolve_note_target_path("link", library_root=library))

    def test_sync_out_library_repairs_links_and_updates_sub_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "out" / "manual").mkdir(parents=True)
            (root / "out" / "manual" / "attachment_file").mkdir(parents=True)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True)
            (root / "out" / "article_index" / "sub_index").mkdir(parents=True)

            (root / "out" / "manual" / "A.md").write_text(
                "参考 [[B]]、[[paper.pdf|PDF]] 和 [[missing.pdf|PDF]]\n",
                encoding="utf-8",
            )
            (root / "out" / "manual" / "B.md").write_text("正文\n", encoding="utf-8")
            (root / "out" / "manual" / "attachment_file" / "paper.pdf").write_text("fake\n", encoding="utf-8")
            (root / "out" / "auto" / "article_summaries" / "Sun 2026 - SW - ICME边界研究.md").write_text(
                "\n".join(
                    [
                        "----",
                        "- [DOI](https://doi.org/10.1000/icme) #太阳与日球层",
                        "- _Sun, A. (2026). ICME boundaries. Space Weather. https://doi.org/10.1000/icme_",
                        "- 文章讨论 near-Earth ICME boundary 与 solar wind 结构整合。",
                        "- 「补充信息」",
                        "\t1. 可继续关注边界目录和业务化影响。",
                        "- 「文中引用」",
                        "\t1. 暂留空。",
                        "- 「好句子」",
                        "\t1. 暂留空。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "out" / "article_index" / "index.md").write_text(
                "- [[1.1 - 行星际磁场影响]]\n",
                encoding="utf-8",
            )
            (root / "out" / "article_index" / "sub_index" / "1.1 - 行星际磁场影响.md").write_text(
                "1. [[Classic 2001 - SW - 示例]]\n",
                encoding="utf-8",
            )

            result = sync_out_library(root)

            self.assertGreaterEqual(result.repaired_links, 1)

            repaired_manual = (root / "out" / "manual" / "A.md").read_text(encoding="utf-8")
            self.assertIn("[[manual/B|B]]", repaired_manual)
            self.assertIn("[[manual/attachment_file/paper.pdf|PDF]]", repaired_manual)
            self.assertIn("[[missing.pdf|PDF]]", repaired_manual)

            repaired_index = (root / "out" / "article_index" / "index.md").read_text(encoding="utf-8")
            self.assertIn(
                "[[article_index/sub_index/1.1 - 行星际磁场影响|1.1 - 行星际磁场影响]]",
                repaired_index,
            )

            sub_index_text = (root / "out" / "article_index" / "sub_index" / "1.1 - 行星际磁场影响.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "[[auto/article_summaries/Sun 2026 - SW - ICME边界研究|Sun 2026 - SW - ICME边界研究]]",
                sub_index_text,
            )

    def test_sync_out_library_removes_false_planet_classification_and_cleans_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "out" / "manual").mkdir(parents=True)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True)
            (root / "out" / "article_index" / "sub_index").mkdir(parents=True)

            earth_note = root / "out" / "manual" / "Liu 2017 - SW - 热层综述 - 重要.md"
            earth_note.write_text(
                "\n".join(
                    [
                        "----",
                        "- [[paper.pdf|PDF]] #综述 #热层/密度 #对象/其他行星/月球",
                        "- _Liu, A. (2017). Important review. Space Weather. https://doi.org/10.1000/review_",
                        "- 这篇文章讨论地球热层密度与太阳风-磁层驱动。",
                        "- 「补充信息」",
                        "\t1. This result may matter for future lunar missions, but the paper itself is about Earth.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            moon_note = root / "out" / "manual" / "Moon 2026 - JGR.SP - 月球电离层观测.md"
            moon_note.write_text(
                "\n".join(
                    [
                        "----",
                        "- [[moon.pdf|PDF]] #研究星球/月球 #电离层",
                        "- _Moon, B. (2026). Lunar ionosphere. JGR: Space Physics. https://doi.org/10.1000/moon_",
                        "- 利用 Danuri 观测月球电离层。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            (root / "out" / "article_index" / "sub_index" / "2.1 - 综述.md").write_text(
                "1. [[manual/Liu 2017 - SW - 热层综述 - 重要|Liu 2017 - SW - 热层综述 - 重要]]\n",
                encoding="utf-8",
            )
            (root / "out" / "article_index" / "sub_index" / "6.1 - 月球.md").write_text(
                "\n".join(
                    [
                        "1. [[manual/Liu 2017 - SW - 热层综述 - 重要|Liu 2017 - SW - 热层综述 - 重要]]",
                        "2. [[manual/Moon 2026 - JGR.SP - 月球电离层观测|Moon 2026 - JGR.SP - 月球电离层观测]]",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            sync_out_library(root)

            earth_text = earth_note.read_text(encoding="utf-8")
            self.assertNotIn("#对象/其他行星/月球", earth_text)

            moon_text = moon_note.read_text(encoding="utf-8")
            self.assertIn("#对象/其他行星/月球", moon_text)

            summary_page = (root / "out" / "article_index" / "sub_index" / "2.1 - 综述.md").read_text(encoding="utf-8")
            self.assertIn(
                "[[manual/Liu 2017 - SW - 热层综述 - 重要|Liu 2017 - SW - 热层综述]]",
                summary_page,
            )

            moon_page = (root / "out" / "article_index" / "sub_index" / "6.1 - 月球.md").read_text(encoding="utf-8")
            self.assertNotIn("Liu 2017 - SW - 热层综述 - 重要", moon_page)
            self.assertIn("[[manual/Moon 2026 - JGR.SP - 月球电离层观测|Moon 2026 - JGR.SP - 月球电离层观测]]", moon_page)

    def test_sync_out_library_does_not_add_planet_tags_to_auto_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True)
            (root / "out" / "article_index" / "sub_index").mkdir(parents=True)

            note = root / "out" / "auto" / "article_summaries" / "Duling 2026 - JGR.SP - Ganymede aurora.md"
            note.write_text(
                "\n".join(
                    [
                        "----",
                        "- [DOI](https://doi.org/10.1029/2025JA034982) #对象/极区/极光 #仪器/JunoUVS",
                        "- 本研究利用 Juno UVS 观测 Ganymede aurora。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            sync_out_library(root)

            text = note.read_text(encoding="utf-8")
            self.assertNotIn("#对象/其他行星/木星", text)

    def test_sync_out_library_repairs_legacy_summary_links_after_title_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "out" / "auto" / "article_summaries").mkdir(parents=True)
            (root / "out" / "research_reports").mkdir(parents=True)
            (root / "out" / "article_index" / "sub_index").mkdir(parents=True)

            summary_path = root / "out" / "auto" / "article_summaries" / "Chang 2026 - EPS - 月幔电阻率揭示深部非均一与局部熔融.md"
            summary_path.write_text(
                "\n".join(
                    [
                        "----",
                        "- [DOI](https://doi.org/10.1186/s40623-026-02412-z) #对象/其他行星/月球",
                        "- _Chang, P.-Y. (2026). Example. Earth, Planets and Space. https://doi.org/10.1186/s40623-026-02412-z_",
                        "- 示例正文。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            report_path = root / "out" / "research_reports" / "2026-03-16 周报.md"
            report_path.write_text(
                "[[out/article_summaries/Chang 2026 - EPS - 多台站月面磁测揭示月幔非均一与深部局部熔融|Moon mantle]]\n",
                encoding="utf-8",
            )

            sync_out_library(root)

            repaired_report = report_path.read_text(encoding="utf-8")
            self.assertIn(
                "[[auto/article_summaries/Chang 2026 - EPS - 月幔电阻率揭示深部非均一与局部熔融|Moon mantle]]",
                repaired_report,
            )

    def test_sync_out_library_keeps_legacy_sub_index_source_when_output_delete_not_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sub_index_dir = root / "out" / "article_index" / "sub_index"
            sub_index_dir.mkdir(parents=True)
            source = sub_index_dir / "太阳与日球层.md"
            target = sub_index_dir / "7 - 太阳与日球层.md"
            source.write_text("旧页内容\n", encoding="utf-8")

            sync_out_library(root)

            self.assertTrue(source.exists())
            self.assertTrue(target.exists())
            self.assertIn("旧页内容\n", target.read_text(encoding="utf-8"))

    def test_sync_out_library_removes_legacy_sub_index_source_when_output_delete_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "config" / "runtime.json").write_text(
                json.dumps(
                    {
                        "safety": {
                            "allow_output_deletions": True,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            sub_index_dir = root / "out" / "article_index" / "sub_index"
            sub_index_dir.mkdir(parents=True)
            source = sub_index_dir / "太阳与日球层.md"
            target = sub_index_dir / "7 - 太阳与日球层.md"
            source.write_text("旧页内容\n", encoding="utf-8")

            sync_out_library(root)

            self.assertFalse(source.exists())
            self.assertTrue(target.exists())
            self.assertIn("旧页内容\n", target.read_text(encoding="utf-8"))

    def test_sync_out_library_repairs_manual_asset_links_with_normalized_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "out" / "manual" / "attachment_file").mkdir(parents=True)
            (root / "out" / "article_index" / "sub_index").mkdir(parents=True)

            note_path = root / "out" / "manual" / "A.md"
            note_path.write_text(
                "参考 [[[R-Quick] Example.pdf|PDF]]\n",
                encoding="utf-8",
            )
            asset_path = root / "out" / "manual" / "attachment_file" / "[R-Qucik] Example_withMarginNotes.pdf"
            asset_path.write_text("fake\n", encoding="utf-8")

            sync_out_library(root)

            repaired = note_path.read_text(encoding="utf-8")
            self.assertIn(
                "[[manual/attachment_file/[R-Qucik] Example_withMarginNotes.pdf|PDF]]",
                repaired,
            )

    def test_sync_out_library_repairs_my_work_links_after_folder_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "out" / "my_work" / "papers").mkdir(parents=True)
            (root / "out" / "article_index" / "sub_index").mkdir(parents=True)

            note_path = root / "out" / "my_work" / "README.md"
            note_path.write_text(
                "\n".join(
                    [
                        "[[myWork/research_overview|研究总览]]",
                        "[[myWork/papers/Li (2020) - JGR.SP - 冬季夜间增强形成机制|Li (2020)]]",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "out" / "my_work" / "research_overview.md").write_text("正文\n", encoding="utf-8")
            (root / "out" / "my_work" / "papers" / "Li (2020) - JGR.SP - 冬季夜间增强形成机制.md").write_text(
                "正文\n",
                encoding="utf-8",
            )

            sync_out_library(root)

            repaired = note_path.read_text(encoding="utf-8")
            self.assertIn("[[my_work/research_overview|研究总览]]", repaired)
            self.assertIn(
                "[[my_work/papers/Li (2020) - JGR.SP - 冬季夜间增强形成机制|Li (2020)]]",
                repaired,
            )


if __name__ == "__main__":
    unittest.main()
