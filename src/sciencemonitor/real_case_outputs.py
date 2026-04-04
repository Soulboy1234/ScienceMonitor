from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RealCaseFixtureCheckResult:
    case_id: str
    artifact_name: str
    fixture_path: Path
    actual_path: Path
    passed: bool
    updated: bool
    diff_path: Path | None
    message: str


def compare_real_case_fixtures(
    results: list["RealCaseEvalResult"],
    *,
    fixture_root: Path,
    log_root: Path,
    update: bool = False,
) -> list[RealCaseFixtureCheckResult]:
    fixture_root.mkdir(parents=True, exist_ok=True)
    checks: list[RealCaseFixtureCheckResult] = []
    for result in results:
        if not result.passed:
            continue
        case_fixture_root = fixture_root / result.case_id
        case_fixture_root.mkdir(parents=True, exist_ok=True)
        case_log_root = log_root / result.case_id / "fixture_compare"
        actual_root = case_log_root / "actual"
        diff_root = case_log_root / "diffs"
        actual_root.mkdir(parents=True, exist_ok=True)
        diff_root.mkdir(parents=True, exist_ok=True)
        artifact_specs = _build_real_case_artifact_specs(result)
        for artifact_name, source_path, normalized_text in artifact_specs:
            checks.append(
                _compare_fixture_artifact(
                    result,
                    artifact_name,
                    source_path,
                    normalized_text,
                    case_fixture_root=case_fixture_root,
                    actual_root=actual_root,
                    diff_root=diff_root,
                    update=update,
                )
            )
    return checks


def render_real_case_eval_summary(results: list["RealCaseEvalResult"]) -> str:
    lines = [
        "Real case eval summary:",
        f"- cases={len(results)}",
        f"- passed={sum(1 for item in results if item.passed)}",
        f"- failed={sum(1 for item in results if not item.passed)}",
    ]
    for item in results:
        status = "ok" if item.passed else "failed"
        abstract_flag = "abstract-only" if item.abstract_only else "full-text"
        lines.append(f"- {item.case_id}: {status} source={item.source_kind} mode={abstract_flag}")
        if item.summary_path:
            lines.append(f"  summary={item.summary_path}")
        if item.report_path:
            lines.append(f"  report={item.report_path}")
        if item.deep_read_path:
            lines.append(f"  deep_read={item.deep_read_path}")
        if item.deep_read_pdf_path:
            lines.append(f"  deep_read_pdf={item.deep_read_pdf_path}")
        if item.metadata_path:
            lines.append(f"  metadata={item.metadata_path}")
        lines.append(f"  note={item.message}")
    return "\n".join(lines)


def render_real_case_fixture_summary(
    results: list["RealCaseEvalResult"],
    checks: list[RealCaseFixtureCheckResult],
) -> str:
    lines = [render_real_case_eval_summary(results), "", "Real case fixture summary:"]
    lines.append(f"- artifacts={len(checks)}")
    lines.append(f"- passed={sum(1 for item in checks if item.passed)}")
    lines.append(f"- updated={sum(1 for item in checks if item.updated)}")
    lines.append(f"- failed={sum(1 for item in checks if not item.passed)}")
    for item in checks:
        status = "updated" if item.updated else ("ok" if item.passed else "drift")
        lines.append(f"- {item.case_id}/{item.artifact_name}: {status}")
        lines.append(f"  fixture={item.fixture_path}")
        lines.append(f"  actual={item.actual_path}")
        lines.append(f"  note={item.message}")
        if item.diff_path:
            lines.append(f"  diff={item.diff_path}")
    return "\n".join(lines)


def _compare_fixture_artifact(
    result: "RealCaseEvalResult",
    artifact_name: str,
    source_path: Path,
    normalized_text: str,
    *,
    case_fixture_root: Path,
    actual_root: Path,
    diff_root: Path,
    update: bool,
) -> RealCaseFixtureCheckResult:
    fixture_path = case_fixture_root / f"{artifact_name}{source_path.suffix}"
    actual_path = actual_root / f"{artifact_name}{source_path.suffix}"
    diff_path = diff_root / f"{artifact_name}.diff"
    actual_path.write_text(normalized_text, encoding="utf-8")
    if update:
        fixture_path.write_text(normalized_text, encoding="utf-8")
        if diff_path.exists():
            diff_path.unlink()
        return RealCaseFixtureCheckResult(
            case_id=result.case_id,
            artifact_name=artifact_name,
            fixture_path=fixture_path,
            actual_path=actual_path,
            passed=True,
            updated=True,
            diff_path=None,
            message="updated fixture",
        )
    if not fixture_path.exists():
        if diff_path.exists():
            diff_path.unlink()
        return RealCaseFixtureCheckResult(
            case_id=result.case_id,
            artifact_name=artifact_name,
            fixture_path=fixture_path,
            actual_path=actual_path,
            passed=False,
            updated=False,
            diff_path=None,
            message="missing fixture",
        )
    expected = fixture_path.read_text(encoding="utf-8")
    if expected == normalized_text:
        if diff_path.exists():
            diff_path.unlink()
        return RealCaseFixtureCheckResult(
            case_id=result.case_id,
            artifact_name=artifact_name,
            fixture_path=fixture_path,
            actual_path=actual_path,
            passed=True,
            updated=False,
            diff_path=None,
            message="matched fixture",
        )
    diff_text = "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            normalized_text.splitlines(keepends=True),
            fromfile=str(fixture_path),
            tofile=str(actual_path),
        )
    )
    diff_path.write_text(diff_text, encoding="utf-8")
    return RealCaseFixtureCheckResult(
        case_id=result.case_id,
        artifact_name=artifact_name,
        fixture_path=fixture_path,
        actual_path=actual_path,
        passed=False,
        updated=False,
        diff_path=diff_path,
        message="output drift detected",
    )


def _build_real_case_artifact_specs(result: "RealCaseEvalResult") -> list[tuple[str, Path, str]]:
    specs: list[tuple[str, Path, str]] = []
    if result.summary_path and result.summary_path.exists():
        specs.append(("summary", result.summary_path, _normalize_eval_markdown(result.summary_path.read_text(encoding="utf-8"))))
    if result.report_path and result.report_path.exists():
        specs.append(("report", result.report_path, _normalize_eval_markdown(result.report_path.read_text(encoding="utf-8"))))
    if result.deep_read_path and result.deep_read_path.exists():
        specs.append(("deep_read", result.deep_read_path, _normalize_eval_markdown(result.deep_read_path.read_text(encoding="utf-8"))))
    if result.metadata_path and result.metadata_path.exists():
        metadata_payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        normalized_status = {
            "case_id": metadata_payload.get("case_id", ""),
            "summary_source_kind": metadata_payload.get("summary_source_kind", ""),
            "abstract_only": bool(metadata_payload.get("abstract_only", False)),
            "report_generated": bool(metadata_payload.get("report_generated", False)),
            "deep_read_generated": bool(metadata_payload.get("deep_read_generated", False)),
            "deep_read_source_kind": metadata_payload.get("deep_read_source_kind", ""),
        }
        specs.append(
            (
                "status",
                result.metadata_path.with_name("status.json"),
                json.dumps(normalized_status, ensure_ascii=False, indent=2) + "\n",
            )
        )
    return specs


def _normalize_eval_markdown(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"记录时间戳:\s*.+", "记录时间戳: <TIMESTAMP>", normalized)
    normalized = re.sub(r"- 生成时间：.+", "- 生成时间：<TIMESTAMP>", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return normalized + "\n"
