from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .article_summaries import generate_article_summary_results
from .config import config_templates_root, logs_root, project_root
from .deep_reads import run_deep_read
from .llm import AnalysisEngine
from .real_case_outputs import (
    RealCaseFixtureCheckResult,
    compare_real_case_fixtures,
)
from .reporting import build_report
from .storage import Storage
from .utils import clean_abstract_text


@dataclass(frozen=True)
class RealCaseEvalResult:
    case_id: str
    title: str
    passed: bool
    source_kind: str
    abstract_only: bool
    summary_path: Path | None
    report_path: Path | None
    deep_read_path: Path | None
    deep_read_pdf_path: Path | None
    metadata_path: Path | None
    message: str


def real_case_eval_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "evals" / "real_cases"


def real_case_eval_log_root(root: Path | None = None) -> Path:
    return logs_root(root) / "real_case_eval"


def real_case_fixture_root(root: Path | None = None) -> Path:
    return real_case_eval_root(root) / "fixtures"


def load_real_cases(root: Path | None = None) -> list[dict]:
    path = real_case_eval_root(root) / "cases.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("cases", []) if isinstance(payload, dict) else []


def run_real_case_eval(
    root: Path | None = None,
    *,
    case_ids: set[str] | None = None,
    limit: int = 0,
    include_report: bool = False,
    include_deep_read: bool = False,
) -> list[RealCaseEvalResult]:
    project = root or project_root()
    cases = load_real_cases(project)
    selected = [case for case in cases if not case_ids or case.get("id") in case_ids]
    if limit > 0:
        selected = selected[:limit]

    log_root = real_case_eval_log_root(project)
    log_root.mkdir(parents=True, exist_ok=True)
    template_path = config_templates_root(project) / "article_summary_template.md"
    analysis_engine = AnalysisEngine(project)
    provider_status = analysis_engine.provider_status()
    results: list[RealCaseEvalResult] = []
    storage = Storage(project / "data" / "science_monitor.db")

    try:
        for case in selected:
            case_id = str(case.get("id", "") or "")
            case_title = str(case.get("title", "") or "")
            case_log_root = log_root / case_id
            if case_log_root.exists():
                shutil.rmtree(case_log_root)
            case_log_root.mkdir(parents=True, exist_ok=True)
            summary_dir = case_log_root / "article_summaries"
            seed_row = _build_seed_row(case, project)

            try:
                summary_results = generate_article_summary_results(
                    rows=[seed_row],
                    template_path=template_path,
                    output_dir=summary_dir,
                    analysis_engine=analysis_engine,
                    root=project,
                    enable_live_fetch=True,
                    require_analysis=True,
                )
            except Exception as exc:
                results.append(
                    RealCaseEvalResult(
                        case_id=case_id,
                        title=case_title,
                        passed=False,
                        source_kind="error",
                        abstract_only=False,
                        summary_path=None,
                        report_path=None,
                        deep_read_path=None,
                        deep_read_pdf_path=None,
                        metadata_path=None,
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
                continue

            if not summary_results:
                results.append(
                    RealCaseEvalResult(
                        case_id=case_id,
                        title=case_title,
                        passed=False,
                        source_kind="missing",
                        abstract_only=False,
                        summary_path=None,
                        report_path=None,
                        deep_read_path=None,
                        deep_read_pdf_path=None,
                        metadata_path=None,
                        message="未生成单篇总结。",
                    )
                )
                continue

            summary = summary_results[0]
            source_kind = str(summary.row.get("summary_source_kind", "") or "missing")
            abstract_only = "信息来源/仅摘要" in summary.tags
            report_path: Path | None = None
            stats: dict = {}
            if include_report:
                report_date = _resolve_report_date(summary.row)
                report_markdown, stats = build_report(
                    report_date,
                    summary_results,
                    analysis_engine=analysis_engine,
                    root=project,
                    require_analysis=True,
                )
                report_path = case_log_root / f"{report_date.isoformat()}_daily_report.md"
                report_path.write_text(report_markdown, encoding="utf-8")

            deep_read_path: Path | None = None
            deep_read_pdf_path: Path | None = None
            deep_read_source_kind = ""
            deep_read_message = ""
            deep_read_success = not include_deep_read
            if include_deep_read:
                deep_read_result = run_deep_read(
                    root=project,
                    storage=storage,
                    doi=str(case.get("doi", "") or summary.row.get("doi", "") or ""),
                    title=str(case.get("title", "") or summary.row.get("title", "") or ""),
                    pdf_path=str(seed_row.get("local_pdf_path", "") or ""),
                    journal=str(case.get("journal", "") or summary.row.get("source_name", "") or ""),
                    url=str(case.get("url", "") or summary.row.get("url", "") or ""),
                    output_dir_override=case_log_root / "deep_reads",
                    pdf_dir_override=case_log_root / "deep_reads_pdf",
                    sync_library=False,
                    related_summary_override=summary.output_path,
                )
                deep_read_success = deep_read_result.success
                deep_read_path = deep_read_result.output_path
                deep_read_pdf_path = deep_read_result.pdf_output_path
                deep_read_source_kind = deep_read_result.source_kind
                deep_read_message = deep_read_result.message

            metadata_path = case_log_root / "metadata.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "case_id": case_id,
                        "title": summary.row["title"],
                        "doi": summary.row["doi"],
                        "url": summary.row["url"],
                        "journal": summary.row["source_name"],
                        "published_date": summary.row["published_date"],
                        "summary_source_kind": source_kind,
                        "summary_tags": summary.tags,
                        "abstract_only": abstract_only,
                        "source_text_cache_path": str(summary.row.get("source_text_cache_path", "") or ""),
                        "provider": analysis_engine.provider,
                        "codex_model": provider_status.get("codex_model", ""),
                        "openai_model": provider_status.get("openai_model", ""),
                        "article_reasoning_effort": provider_status.get("article_reasoning_effort", ""),
                        "article_llm_used": bool(summary.analysis),
                        "report_stats": stats,
                        "report_generated": include_report,
                        "deep_read_generated": bool(deep_read_path),
                        "deep_read_source_kind": deep_read_source_kind,
                        "deep_read_output_path": str(deep_read_path or ""),
                        "deep_read_pdf_output_path": str(deep_read_pdf_path or ""),
                        "deep_read_message": deep_read_message,
                        "asset_pdf": case.get("asset_pdf", ""),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            abstract_text = clean_abstract_text(str(summary.row.get("abstract", "") or ""))
            passed = source_kind != "missing" and bool(abstract_text) and deep_read_success
            if abstract_only:
                message = "未获得全文，已退回摘要生成单篇总结和周报。" if include_report else "未获得全文，已退回摘要生成单篇总结。"
            elif source_kind in {"html_full_text", "local_pdf_full_text"}:
                message = "全文级材料获取成功。"
            else:
                message = "未识别到明确的数据来源。"
            if include_deep_read:
                if deep_read_success:
                    message += " 深度解读已写入本地评测目录。"
                else:
                    message += f" 深度解读失败：{deep_read_message}"
            results.append(
                RealCaseEvalResult(
                    case_id=case_id,
                    title=str(summary.row["title"]),
                    passed=passed,
                    source_kind=source_kind,
                    abstract_only=abstract_only,
                    summary_path=summary.output_path,
                    report_path=report_path,
                    deep_read_path=deep_read_path,
                    deep_read_pdf_path=deep_read_pdf_path,
                    metadata_path=metadata_path,
                    message=message,
                )
            )
    finally:
        storage.close()
    return results


def run_real_case_fixture_eval(
    root: Path | None = None,
    *,
    case_ids: set[str] | None = None,
    limit: int = 0,
    include_report: bool = False,
    include_deep_read: bool = False,
    update: bool = False,
) -> tuple[list[RealCaseEvalResult], list[RealCaseFixtureCheckResult]]:
    results = run_real_case_eval(
        root=root,
        case_ids=case_ids,
        limit=limit,
        include_report=include_report,
        include_deep_read=include_deep_read,
    )
    project = root or project_root()
    checks = compare_real_case_fixtures(
        results,
        fixture_root=real_case_fixture_root(project),
        log_root=real_case_eval_log_root(project),
        update=update,
    )
    return results, checks


def _build_seed_row(case: dict, root: Path | None = None) -> dict:
    journal = str(case.get("journal", "") or "Unknown Journal")
    published_date = str(case.get("published_date", "") or date.today().isoformat())
    authors = case.get("authors", [])
    if not isinstance(authors, list):
        authors = []
    topic_labels = case.get("topic_labels", [])
    if not isinstance(topic_labels, list):
        topic_labels = []
    asset_pdf = str(case.get("asset_pdf", "") or "").strip()
    local_pdf_path = ""
    if asset_pdf:
        asset_path = Path(asset_pdf).expanduser()
        if not asset_path.is_absolute():
            asset_path = real_case_eval_root(root) / asset_path
        if asset_path.exists():
            local_pdf_path = str(asset_path.resolve())
    return {
        "fingerprint": f"real_case::{case.get('id', 'unknown')}",
        "source_id": f"real_case::{case.get('id', 'unknown')}",
        "source_name": journal,
        "journal_title": journal,
        "title": str(case.get("title", "") or ""),
        "abstract": str(case.get("abstract", "") or ""),
        "published_date": published_date,
        "doi": str(case.get("doi", "") or ""),
        "url": str(case.get("url", "") or ""),
        "authors": "\n".join(str(item).strip() for item in authors if str(item).strip()),
        "topics": "",
        "topic_labels": "\n".join(str(item).strip() for item in topic_labels if str(item).strip()),
        "relevance_score": float(case.get("relevance_score", 9.0) or 9.0),
        "tier": "real_case",
        "mode": "full",
        "disable_special_overrides": True,
        "raw_container_title": journal,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds"),
        "notes": str(case.get("notes", "") or ""),
        "local_pdf_path": local_pdf_path,
    }


def _resolve_report_date(row: dict) -> date:
    published = str(row.get("published_date", "") or "")
    try:
        return date.fromisoformat(published)
    except ValueError:
        return date.today()
