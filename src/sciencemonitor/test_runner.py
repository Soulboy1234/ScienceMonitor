from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .resource_checks import resolve_test_tmpdir


@dataclass(frozen=True)
class CommandCheckResult:
    name: str
    command: tuple[str, ...]
    passed: bool
    exit_code: int
    output: str
    skipped: bool = False


def run_pytest_suite(root: Path, test_args: tuple[str, ...] = ()) -> CommandCheckResult:
    local_python = root / ".venv" / "bin" / "python"
    python_bin = str(local_python if local_python.exists() else Path(sys.executable))
    command = (python_bin, "-m", "pytest", "-q", *test_args)
    env = os.environ.copy()
    if not env.get("SCIENCEMONITOR_PYTEST_PRESERVE_PATH_ENV"):
        for key in ("SCIENCEMONITOR_OUTPUT_ROOT", "SCIENCEMONITOR_DATA_ROOT", "SCIENCEMONITOR_LOG_ROOT"):
            env.pop(key, None)
    tmpdir = resolve_test_tmpdir(root)
    tmpdir.mkdir(parents=True, exist_ok=True)
    env.setdefault("SCIENCEMONITOR_TEST_TMPDIR", str(tmpdir))
    env["TMPDIR"] = str(tmpdir)
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    output = (completed.stdout or "") + ((completed.stderr or "") if completed.stderr else "")
    return CommandCheckResult(
        name="pytest",
        command=command,
        passed=completed.returncode == 0,
        exit_code=completed.returncode,
        output=output.strip() or "(no output)",
    )


def skipped_command_result(name: str, command: tuple[str, ...], reason: str) -> CommandCheckResult:
    return CommandCheckResult(
        name=name,
        command=command,
        passed=False,
        exit_code=0,
        output=reason,
        skipped=True,
    )


def render_command_check_summary(result: CommandCheckResult | None) -> str:
    if result is None:
        return "Command check summary:\n- status=skipped\n- reason=not requested"
    status = "skipped" if result.skipped else ("ok" if result.passed else "failed")
    return "\n".join(
        [
            "Command check summary:",
            f"- name={result.name}",
            f"- status={status}",
            f"- exit_code={result.exit_code}",
            f"- command={' '.join(result.command)}",
            "- output:",
            result.output.strip() or "(no output)",
        ]
    )
