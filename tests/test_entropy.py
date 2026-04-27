from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.entropy import _collect_import_cycles, _collect_module_line_counts, _collect_unused_imports


class EntropyUnusedImportTest(unittest.TestCase):
    def test_module_line_counts_ignore_blank_and_comment_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = pathlib.Path(tmpdir)
            (source_root / "module_a.py").write_text(
                "import io\n\n# note\n\ndef hello():\n    return 'ok'\n",
                encoding="utf-8",
            )
            counts = _collect_module_line_counts(source_root)

        self.assertEqual(counts, {"module_a.py": 3})

    def test_collect_unused_imports_reports_plain_unused_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = pathlib.Path(tmpdir)
            (source_root / "module_a.py").write_text(
                "import io\n\n\ndef hello():\n    return 'ok'\n",
                encoding="utf-8",
            )
            unused = _collect_unused_imports(source_root)

        self.assertEqual(unused, {"module_a.py": ["io"]})

    def test_collect_unused_imports_ignores_compatibility_reexport_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = pathlib.Path(tmpdir)
            (source_root / "module_b.py").write_text(
                "\n".join(
                    [
                        "# Compatibility re-export for public module API.",
                        "from .helpers import render_summary",
                        "",
                        "def hello():",
                        "    return 'ok'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            unused = _collect_unused_imports(source_root)

        self.assertEqual(unused, {})

    def test_collect_import_cycles_ignores_lazy_function_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = pathlib.Path(tmpdir)
            (source_root / "module_a.py").write_text(
                "\n".join(
                    [
                        "from __future__ import annotations",
                        "",
                        "def lazy():",
                        "    from .module_b import value",
                        "    return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (source_root / "module_b.py").write_text(
                "\n".join(
                    [
                        "from __future__ import annotations",
                        "from .module_a import lazy",
                        "",
                        "value = 1",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            cycles = _collect_import_cycles(source_root)

        self.assertEqual(cycles, [])


if __name__ == "__main__":
    unittest.main()
