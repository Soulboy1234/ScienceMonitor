from __future__ import annotations

import os
import pathlib
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_TMPDIR = pathlib.Path(os.environ.get("SCIENCEMONITOR_TEST_TMPDIR", ROOT / "tmp" / "pytest")).expanduser()
TEST_TMPDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SCIENCEMONITOR_TEST_TMPDIR", str(TEST_TMPDIR))
os.environ["TMPDIR"] = str(TEST_TMPDIR)
tempfile.tempdir = str(TEST_TMPDIR)
