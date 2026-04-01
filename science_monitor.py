#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
LOCAL_PYTHON = ROOT / ".venv" / "bin" / "python"


def _maybe_reexec_local_python() -> None:
    if os.environ.get("SCIENCEMONITOR_SKIP_REEXEC") == "1":
        return
    if not LOCAL_PYTHON.exists():
        return
    current = pathlib.Path(sys.executable).resolve()
    desired = LOCAL_PYTHON.resolve()
    if current == desired:
        return
    os.environ["SCIENCEMONITOR_SKIP_REEXEC"] = "1"
    os.environ["VIRTUAL_ENV"] = str(ROOT / ".venv")
    os.environ["PYTHONNOUSERSITE"] = "1"
    venv_bin = str(ROOT / ".venv" / "bin")
    path_entries = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    if not path_entries or path_entries[0] != venv_bin:
        os.environ["PATH"] = os.pathsep.join([venv_bin, *[item for item in path_entries if item != venv_bin]])
    os.execv(str(desired), [str(desired), __file__, *sys.argv[1:]])

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if __name__ == "__main__":
    _maybe_reexec_local_python()
    from sciencemonitor.cli import main  # noqa: E402

    raise SystemExit(main())
