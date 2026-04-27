from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class LauncherProbeTest(unittest.TestCase):
    def test_launcher_probe_uses_stable_meta_marker(self) -> None:
        shell_text = (ROOT / "scripts" / "launchers" / "start_panel.sh").read_text(encoding="utf-8")
        python_text = (ROOT / "scripts" / "launch_config_ui.py").read_text(encoding="utf-8")
        marker = '<meta name="sciencemonitor-ui" content="config-ui">'
        self.assertIn(marker, shell_text)
        self.assertIn(marker, python_text)


if __name__ == "__main__":
    unittest.main()
