from __future__ import annotations

import json
import signal
import ssl
from contextlib import contextmanager
from typing import Any
from urllib import parse, request


DEFAULT_HEADERS = {
    "User-Agent": "ScienceMonitor/0.1 (+https://crossref.org/; mailto:science-monitor@example.com)",
    "Accept": "*/*",
}


class HTTPClient:
    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.ssl_context = ssl.create_default_context()

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        raw, charset = self._read_response_bytes(url, headers=headers)
        charset = charset or "utf-8"
        return raw.decode(charset, errors="replace")

    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        raw, _ = self._read_response_bytes(url, headers=headers)
        return raw

    def _read_response_bytes(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, str | None]:
        req = request.Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
        with self._deadline(self.timeout, url):
            resp = request.urlopen(req, timeout=self.timeout, context=self.ssl_context)
        with resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset()
        return raw, charset

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        final_url = url
        if params:
            final_url = f"{url}?{parse.urlencode(params)}"
        body = self.get_text(final_url, headers={"Accept": "application/json"})
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
        return hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")
