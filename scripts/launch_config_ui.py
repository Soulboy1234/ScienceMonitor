#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
BASE_PORT = 8765
MAX_PORT_OFFSET = 9
DEFAULT_SUPPORT_ROOT = Path.home() / "Library" / "Application Support" / "ScienceMonitorLauncher"
LOG_PATH = Path(os.environ.get("SCIENCEMONITOR_CONFIG_UI_LOG_PATH", DEFAULT_SUPPORT_ROOT / "config_ui_launcher.log")).expanduser()
STATE_PATH = Path(os.environ.get("SCIENCEMONITOR_CONFIG_UI_STATE_PATH", DEFAULT_SUPPORT_ROOT / "config_ui_state.json")).expanduser()
ENTRYPOINT = PROJECT_ROOT / "science_monitor.py"
TITLE_MARKER = "<title>ScienceMonitor Config UI</title>"


def _log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((HOST, port)) == 0


def _is_sciencemonitor_ui(port: int) -> bool:
    try:
        with urlopen(f"http://{HOST}:{port}/", timeout=1.0) as response:
            html = response.read(4096).decode("utf-8", errors="ignore")
            return TITLE_MARKER in html
    except URLError:
        return False
    except Exception:
        return False


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _get_running_port_from_state() -> int | None:
    state = _load_state()
    try:
        port = int(state.get("port", 0))
    except Exception:
        return None
    if port > 0 and _is_sciencemonitor_ui(port):
        return port
    return None


def _choose_port() -> int:
    state_port = _get_running_port_from_state()
    if state_port is not None:
        return state_port
    for offset in range(MAX_PORT_OFFSET + 1):
        port = BASE_PORT + offset
        if _port_in_use(port):
            if _is_sciencemonitor_ui(port):
                return port
            continue
        return port
    return BASE_PORT


def _spawn_server(port: int) -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    environment["SCIENCEMONITOR_SKIP_REEXEC"] = "1"
    environment["PATH"] = ":".join(
        [
            str(PROJECT_ROOT / ".venv" / "bin"),
            str(Path.home() / "miniconda" / "bin"),
            "/usr/bin",
            "/bin",
            environment.get("PATH", ""),
        ]
    )
    command = [
        sys.executable,
        str(ENTRYPOINT),
        "config-ui",
        "--host",
        HOST,
        "--port",
        str(port),
        "--no-browser",
    ]
    log_handle = LOG_PATH.open("a", encoding="utf-8")
    subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _wait_until_ready(port: int, timeout_seconds: float = 15.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_sciencemonitor_ui(port):
            return True
        time.sleep(0.5)
    return False


def _find_running_port() -> int | None:
    state_port = _get_running_port_from_state()
    if state_port is not None:
        return state_port
    for offset in range(MAX_PORT_OFFSET + 1):
        port = BASE_PORT + offset
        if _is_sciencemonitor_ui(port):
            return port
    return None


def _request_shutdown(port: int) -> bool:
    try:
        request = Request(f"http://{HOST}:{port}/shutdown-ui", method="POST", data=b"")
        with urlopen(request, timeout=2.0) as response:
            response.read(2048)
    except Exception as exc:
        _log(f"shutdown request failed on port {port}: {type(exc).__name__}: {exc}")
        return False

    deadline = time.time() + 10.0
    while time.time() < deadline:
        if not _is_sciencemonitor_ui(port):
            return True
        time.sleep(0.2)
    return False


def _find_running_pids() -> list[int]:
    try:
        result = subprocess.run(
            ["ps", "-Ao", "pid=,command="],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        _log(f"failed to inspect processes: {type(exc).__name__}: {exc}")
        return []

    matches: list[int] = []
    marker = f"{ENTRYPOINT} config-ui"
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or marker not in line or "launch_config_ui.py" in line:
            continue
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid != os.getpid():
            matches.append(pid)
    return matches


def _terminate_pid(pid: int) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except Exception as exc:
        _log(f"failed to terminate pid {pid}: {type(exc).__name__}: {exc}")
        return False

    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except Exception:
            break
        time.sleep(0.2)
    return False


def _launch() -> int:
    try:
        _log(f"launch request via {sys.executable}")
        port = _choose_port()
        _log(f"selected port {port}")
        if not _is_sciencemonitor_ui(port):
            _log(f"spawning config ui on port {port}")
            _spawn_server(port)
        else:
            _log(f"reusing existing config ui on port {port}")
        if not _wait_until_ready(port):
            _log(f"failed to start ui on port {port}")
            print("ERROR: config-ui did not become ready", file=sys.stderr)
            return 1
        url = f"http://{HOST}:{port}/"
        _log(f"ui ready: {url}")
        print(url)
        return 0
    except Exception as exc:
        _log(f"launcher exception: {type(exc).__name__}: {exc}")
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _status() -> int:
    port = _find_running_port()
    if port is None:
        print("STOPPED")
        return 1
    print(f"http://{HOST}:{port}/")
    return 0


def _stop() -> int:
    port = _find_running_port()
    pids = _find_running_pids()
    if port is None and not pids:
        _log("stop request: ui already stopped")
        print("STOPPED")
        return 0
    if port is not None:
        _log(f"stop request on port {port}")
        if _request_shutdown(port):
            _log(f"ui stopped on port {port}")
            print("STOPPED")
            return 0
        _log(f"graceful shutdown failed on port {port}, falling back to process termination")

    if not pids:
        pids = _find_running_pids()
    if not pids:
        _log("no matching config-ui pid found during fallback stop")
        print("ERROR: failed to stop config-ui", file=sys.stderr)
        return 1

    all_stopped = True
    for pid in pids:
        if _terminate_pid(pid):
            _log(f"terminated config-ui pid {pid}")
        else:
            _log(f"failed to terminate config-ui pid {pid}")
            all_stopped = False
    if all_stopped:
        print("STOPPED")
        return 0
    print("ERROR: failed to stop config-ui", file=sys.stderr)
    return 1


def _launch_open() -> int:
    status = _launch()
    if status != 0:
        return status
    port = _find_running_port()
    if port is None:
        _log("launch-open could not locate running port after launch")
        print("ERROR: running port missing after launch", file=sys.stderr)
        return 1
    url = f"http://{HOST}:{port}/"
    try:
        opened = webbrowser.open(url)
        _log(f"launch-open browser_open={opened} url={url}")
    except Exception as exc:
        _log(f"launch-open browser error: {type(exc).__name__}: {exc}")
    return 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "launch"
    if command == "launch":
        return _launch()
    if command == "launch-open":
        return _launch_open()
    if command == "status":
        return _status()
    if command == "stop":
        return _stop()
    print(f"ERROR: unsupported command {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
