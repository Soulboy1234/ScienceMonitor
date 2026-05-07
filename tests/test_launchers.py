from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class LauncherProbeTest(unittest.TestCase):
    def test_launcher_probe_uses_public_healthz_marker(self) -> None:
        shell_text = (ROOT / "scripts" / "launchers" / "start_panel.sh").read_text(encoding="utf-8")
        stop_shell_text = (ROOT / "scripts" / "launchers" / "stop_panel.sh").read_text(encoding="utf-8")
        python_text = (ROOT / "scripts" / "launch_config_ui.py").read_text(encoding="utf-8")
        marker = "ScienceMonitor config UI OK"
        self.assertIn("/healthz", shell_text)
        self.assertIn("/healthz", stop_shell_text)
        self.assertIn("/healthz", python_text)
        self.assertIn(marker, shell_text)
        self.assertIn(marker, stop_shell_text)
        self.assertIn(marker, python_text)

    def test_launchers_use_tokenized_state_url_and_shutdown(self) -> None:
        shell_text = (ROOT / "scripts" / "launchers" / "start_panel.sh").read_text(encoding="utf-8")
        stop_shell_text = (ROOT / "scripts" / "launchers" / "stop_panel.sh").read_text(encoding="utf-8")
        python_text = (ROOT / "scripts" / "launch_config_ui.py").read_text(encoding="utf-8")
        self.assertIn("read_state_field url", shell_text)
        self.assertIn("read_state_field token", stop_shell_text)
        self.assertIn("shutdown-ui?token=", stop_shell_text)
        self.assertIn("_url_from_state", python_text)
        self.assertIn("_token_from_state", python_text)


if __name__ == "__main__":
    unittest.main()
