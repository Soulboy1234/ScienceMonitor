from __future__ import annotations

import os
import pathlib
import sys
import tempfile


def _running_pytest() -> bool:
    return any("pytest" in pathlib.Path(arg).name for arg in sys.argv)


if _running_pytest():
    root = pathlib.Path(__file__).resolve().parent
    tmpdir = pathlib.Path(os.environ.get("SCIENCEMONITOR_TEST_TMPDIR", root / "tmp" / "pytest")).expanduser()
    try:
        tmpdir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    else:
        os.environ.setdefault("SCIENCEMONITOR_TEST_TMPDIR", str(tmpdir))
        os.environ["TMPDIR"] = str(tmpdir)
        tempfile.tempdir = str(tmpdir)
