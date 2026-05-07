from __future__ import annotations

import pathlib
import sys
import threading
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.http import HTTPClient, ResponseTooLargeError


class _FakeHeaders(dict):
    def get_content_charset(self):
        return "utf-8"


class _FakeResponse:
    def __init__(self, body: bytes, *, content_length: str | None = None) -> None:
        self.body = body
        self.offset = 0
        self.headers = _FakeHeaders()
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


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

    def test_rejects_response_when_content_length_exceeds_limit(self) -> None:
        client = HTTPClient(timeout=5, max_response_bytes=4)
        response = _FakeResponse(b"ok", content_length="5")
        with mock.patch("sciencemonitor.http.request.urlopen", return_value=response):
            with self.assertRaises(ResponseTooLargeError):
                client.get_text("https://example.org/large")

    def test_rejects_response_when_stream_exceeds_limit(self) -> None:
        client = HTTPClient(timeout=5, max_response_bytes=4)
        response = _FakeResponse(b"12345")
        with mock.patch("sciencemonitor.http.request.urlopen", return_value=response):
            with self.assertRaises(ResponseTooLargeError):
                client.get_bytes("https://example.org/large")


if __name__ == "__main__":
    unittest.main()
