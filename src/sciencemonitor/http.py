from __future__ import annotations

import json
import signal
import ssl
import threading
from contextlib import contextmanager
from typing import Any
from urllib import parse, request


DEFAULT_HEADERS = {
    "User-Agent": "ScienceMonitor/0.1 (+https://crossref.org/; mailto:science-monitor@example.com)",
    "Accept": "*/*",
}
DEFAULT_MAX_RESPONSE_BYTES = 25 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024


class ResponseTooLargeError(RuntimeError):
    pass


class HTTPClient:
    def __init__(self, timeout: int = 15, max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES) -> None:
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self.ssl_context = ssl.create_default_context()

    def get_text(self, url: str, headers: dict[str, str] | None = None, *, max_bytes: int | None = None) -> str:
        raw, charset = self._read_response_bytes(url, headers=headers, max_bytes=max_bytes)
        charset = charset or "utf-8"
        return raw.decode(charset, errors="replace")

    def get_bytes(self, url: str, headers: dict[str, str] | None = None, *, max_bytes: int | None = None) -> bytes:
        raw, _ = self._read_response_bytes(url, headers=headers, max_bytes=max_bytes)
        return raw

    def _read_response_bytes(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> tuple[bytes, str | None]:
        limit = self.max_response_bytes if max_bytes is None else max_bytes
        req = request.Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
        with self._deadline(self.timeout, url):
            resp = request.urlopen(req, timeout=self.timeout, context=self.ssl_context)
        with resp:
            content_length = resp.headers.get("Content-Length")
            if content_length:
                try:
                    declared = int(content_length)
                except ValueError:
                    declared = -1
                if declared > limit:
                    raise ResponseTooLargeError(f"Response from {url} is {declared} bytes, limit is {limit} bytes")
            raw = self._read_limited(resp, limit, url)
            charset = resp.headers.get_content_charset()
        return raw, charset

    def _read_limited(self, resp, limit: int, url: str) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ResponseTooLargeError(f"Response from {url} exceeded {limit} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    def get_json(self, url: str, params: dict[str, Any] | None = None, *, max_bytes: int | None = None) -> dict[str, Any]:
        final_url = url
        if params:
            final_url = f"{url}?{parse.urlencode(params)}"
        body = self.get_text(final_url, headers={"Accept": "application/json"}, max_bytes=max_bytes)
        return json.loads(body)

    @contextmanager
    def _deadline(self, seconds: int, url: str):
        if not self._supports_signal_deadline():
            yield
            return

        previous_handler = signal.getsignal(signal.SIGALRM)

        def _raise_timeout(signum, frame):  # pragma: no cover - depends on OS signal delivery timing.
            raise TimeoutError(f"Timed out after {seconds}s while requesting {url}")

        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, max(float(seconds), 0.1))
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _supports_signal_deadline(self) -> bool:
        return (
            hasattr(signal, "SIGALRM")
            and hasattr(signal, "setitimer")
            and threading.current_thread() is threading.main_thread()
        )
