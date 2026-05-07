from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import project_root

DEFAULT_MIN_FREE_MB = 512


@dataclass(frozen=True)
class ResourceCheckIssue:
    category: str
    path: Path
    available_bytes: int
    required_bytes: int
    message: str


@dataclass(frozen=True)
class ResourceCheckReport:
    passed: bool
    min_free_bytes: int
    test_tmpdir: Path
    checks: dict[str, bool]
    issues: list[ResourceCheckIssue]


def resolve_test_tmpdir(root: Path | None = None) -> Path:
    override = os.environ.get("SCIENCEMONITOR_TEST_TMPDIR", "").strip()
    if override:
        return Path(override).expanduser()
    return (root or project_root()) / "tmp" / "pytest"


def run_resource_precheck(
    root: Path | None = None,
    *,
    min_free_mb: int = DEFAULT_MIN_FREE_MB,
) -> ResourceCheckReport:
    project = root or project_root()
    min_free_bytes = max(0, int(min_free_mb)) * 1024 * 1024
    test_tmpdir = resolve_test_tmpdir(project)
    checks: dict[str, bool] = {}
    issues: list[ResourceCheckIssue] = []

    _check_free_space("project_root", project, min_free_bytes, checks, issues)
    tmp_base = _nearest_existing_parent(test_tmpdir)
    _check_free_space("test_tmpdir", tmp_base, min_free_bytes, checks, issues)

    return ResourceCheckReport(
        passed=not issues,
        min_free_bytes=min_free_bytes,
        test_tmpdir=test_tmpdir,
        checks=checks,
        issues=issues,
    )


def render_resource_check_summary(report: ResourceCheckReport) -> str:
    lines = [
        "Resource precheck summary:",
        f"- min_free_mb={report.min_free_bytes // (1024 * 1024)}",
        f"- test_tmpdir={report.test_tmpdir}",
        f"- checks={sum(1 for ok in report.checks.values() if ok)}/{len(report.checks)}",
        f"- overall={'ok' if report.passed else 'failed'}",
    ]
    if report.issues:
        lines.append("- violations:")
        for issue in report.issues:
            available_mb = issue.available_bytes // (1024 * 1024)
            required_mb = issue.required_bytes // (1024 * 1024)
            lines.append(f"  - {issue.category}: {issue.message} ({available_mb} MiB < {required_mb} MiB at {issue.path})")
    else:
        lines.append("- violations: none")
    return "\n".join(lines)


def _check_free_space(
    category: str,
    path: Path,
    required_bytes: int,
    checks: dict[str, bool],
    issues: list[ResourceCheckIssue],
) -> None:
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        checks[category] = False
        issues.append(
            ResourceCheckIssue(
                category=category,
                path=path,
                available_bytes=0,
                required_bytes=required_bytes,
                message=f"无法读取磁盘空间：{exc}",
            )
        )
        return
    passed = usage.free >= required_bytes
    checks[category] = passed
    if not passed:
        issues.append(
            ResourceCheckIssue(
                category=category,
                path=path,
                available_bytes=usage.free,
                required_bytes=required_bytes,
                message="可用磁盘空间不足，跳过高写入量检查以避免级联误报",
            )
        )


def _nearest_existing_parent(path: Path) -> Path:
    current = path.expanduser()
    while not current.exists() and current.parent != current:
        current = current.parent
    return current
