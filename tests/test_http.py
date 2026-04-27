from __future__ import annotations

import pathlib
import sys
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.http import HTTPClient


class HTTPClientTest(unittest.TestCase):
    def test_signal_deadline_disabled_in_worker_thread(self) -> None:
        client = HTTPClient(timeout=5)
        result: dict[str, bool] = {}

        def _worker() -> None:
            result["supported"] = client._supports_signal_deadline()

        thread = threading.Thread(target=_worker)
        thread.start()
        thread.join()
        self.assertFalse(result["supported"])


if __name__ == "__main__":
    unittest.main()
