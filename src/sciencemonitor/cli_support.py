from __future__ import annotations

import argparse
import sys
from datetime import date

from .chatgpt_web_manual import (
    import_manual_response,
    import_manual_response_from_recommended_file,
    list_manual_requests,
    render_manual_request_status,
)
from .config import article_index_root, article_summaries_root, output_root, reports_root
from .config_ui import serve_config_ui
from .deep_reads import run_deep_read
from .doctor import run_doctor
from .entropy import render_entropy_check_summary, run_entropy_check
from .golden_eval import render_golden_eval_summary, run_golden_eval
from .harness_audit import render_harness_audit_summary, run_harness_audit
from .harness import render_harness_check_summary, run_harness_check
from .harness_optimize import render_harness_optimize_summary, run_harness_optimize
from .maintenance import render_maintenance_summary, run_maintenance_cycle
from .pipeline import ScienceMonitor
from .real_case_eval import run_real_case_eval, run_real_case_fixture_eval
from .real_case_outputs import render_real_case_eval_summary, render_real_case_fixture_summary
from .source_audit import generate_source_audit
from .tag_candidates import filter_tag_candidates, write_tag_candidates_report


def build_parser(defaults: dict) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily literature monitor for space physics journals.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_daily_commands(subparsers, defaults)
    _add_analysis_commands(subparsers, defaults)
    _add_eval_and_maintenance_commands(subparsers)
    _add_support_commands(subparsers)
    return parser


def dispatch_command(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    command = str(args.command)
    handlers = {
        "sources": _handle_sources,
        "doctor": _handle_doctor,
        "config-ui": _handle_config_ui,
        "manual-llm-status": _handle_manual_llm_status,
        "manual-llm-import": _handle_manual_llm_import,
        "index": _handle_index,
        "deep-read": _handle_deep_read,
        "tag-candidates": _handle_tag_candidates,
        "golden-eval": _handle_golden_eval,
        "harness-audit": _handle_harness_audit,
        "harness-optimize": _handle_harness_optimize,
        "entropy-check": _handle_entropy_check,
        "real-eval": _handle_real_eval,
        "harness-check": _handle_harness_check,
        "maintenance-check": _handle_maintenance_check,
        "update": _handle_update,
        "report": _handle_report,
        "summaries": _handle_summaries,
        "audit": _handle_audit,
        "daily": _handle_daily,
    }
    handler = handlers.get(command)
    if handler is None:
        return 1
    return handler(args, monitor)


def _add_daily_commands(subparsers: argparse._SubParsersAction, defaults: dict) -> None:
    daily = subparsers.add_parser("daily", help="Run update + report.")
    daily.add_argument("--date", default=date.today().isoformat(), help="Report date in YYYY-MM-DD.")
    daily.add_argument("--days-back", type=int, default=int(defaults.get("daily_days_back", 7)), help="Fetch window length in days.")
    daily.add_argument("--max-per-source", type=int, default=int(defaults.get("daily_max_per_source", 20)), help="Maximum Crossref rows per source.")
    daily.add_argument("--source-ids", default="", help="Comma-separated source ids for a targeted run, e.g. jgr_space_physics,space_weather")

    update = subparsers.add_parser("update", help="Fetch and store papers only.")
    update.add_argument("--date", default=date.today().isoformat(), help="Report date in YYYY-MM-DD.")
    update.add_argument("--days-back", type=int, default=int(defaults.get("update_days_back", 7)), help="Fetch window length in days.")
    update.add_argument("--max-per-source", type=int, default=int(defaults.get("update_max_per_source", 20)), help="Maximum Crossref rows per source.")
    update.set_defaults(hydrate=bool(defaults.get("update_hydrate", True)))
    hydrate_group = update.add_mutually_exclusive_group()
    hydrate_group.add_argument("--hydrate", dest="hydrate", action="store_true", help="Fetch article pages to fill missing abstracts when needed.")
    hydrate_group.add_argument("--no-hydrate", dest="hydrate", action="store_false", help="Skip article page fetching for missing abstracts.")
    update.add_argument("--source-ids", default="", help="Comma-separated source ids for a targeted run, e.g. jgr_space_physics,space_weather")

    report = subparsers.add_parser("report", help="Generate the daily markdown report from stored papers.")
    report.add_argument("--date", default=date.today().isoformat(), help="Report date in YYYY-MM-DD.")
    report.add_argument("--window-days", type=int, default=int(defaults.get("report_window_days", 7)), help="Summarize the recent N-day window ending on the report date.")

    summaries = subparsers.add_parser("summaries", help="Generate per-paper markdown summaries from stored papers.")
    summaries.add_argument("--date", default=date.today().isoformat(), help="Report date in YYYY-MM-DD.")
    summaries.add_argument("--window-days", type=int, default=int(defaults.get("summaries_window_days", 7)), help="Write summaries for the recent N-day window ending on the report date.")

    audit = subparsers.add_parser("audit", help="Generate a per-source audit table for recent fetching coverage.")
    audit.add_argument("--date", default=date.today().isoformat(), help="Audit date in YYYY-MM-DD.")
    audit.add_argument("--window-days", type=int, default=int(defaults.get("audit_window_days", 7)), help="Audit the recent N-day window ending on the audit date.")
    audit.add_argument("--max-per-source", type=int, default=int(defaults.get("audit_max_per_source", 100)), help="Maximum number of candidate works to request per source during audit.")


def _add_analysis_commands(subparsers: argparse._SubParsersAction, defaults: dict) -> None:
    deep_read = subparsers.add_parser("deep-read", help="Generate a deep reading note from a PDF or fetched full text.")
    deep_read.add_argument("--doi", default="", help="Paper DOI.")
    deep_read.add_argument("--title", default="", help="Paper title when DOI is unavailable.")
    deep_read.add_argument("--pdf", default="", help="Optional local PDF path.")
    deep_read.add_argument("--journal", default="", help="Optional journal name.")
    deep_read.add_argument("--url", default="", help="Optional landing page URL.")

    tag_candidates = subparsers.add_parser("tag-candidates", help="Review open-vocabulary tag candidates collected during runtime.")
    tag_candidates.add_argument("--min-count", type=int, default=2, help="Only show tags used at least this many times.")
    tag_candidates.add_argument("--limit", type=int, default=50, help="Maximum number of tags to include in the report. Use 0 for all.")
    tag_candidates.add_argument("--no-write-report", action="store_true", help="Print the summary only and skip writing the markdown review report.")


def _add_eval_and_maintenance_commands(subparsers: argparse._SubParsersAction) -> None:
    golden_eval = subparsers.add_parser("golden-eval", help="Run stable golden-output regression checks.")
    golden_eval.add_argument("--update", action="store_true", help="Refresh golden fixtures to the current normalized outputs.")

    harness_audit = subparsers.add_parser("harness-audit", help="Audit whether the current harness still covers the project workflow.")
    harness_audit.add_argument("--no-write-report", action="store_true", help="Print the audit summary only and skip writing the markdown audit report.")

    harness_optimize = subparsers.add_parser("harness-optimize", help="Apply low-risk deterministic harness governance repairs and rerun harness audit.")
    harness_optimize.add_argument("--no-write-report", action="store_true", help="Print the optimize summary only and skip writing the markdown optimize report.")

    subparsers.add_parser("entropy-check", help="Check code-size budgets, oversized functions, and import-cycle entropy guards.")

    real_eval = subparsers.add_parser("real-eval", help="Run real-paper integration cases for summary retrieval.")
    real_eval.add_argument("--case-ids", default="", help="Comma-separated real case ids. Leave empty to run all tracked cases.")
    real_eval.add_argument("--limit", type=int, default=0, help="Only run the first N selected cases. Use 0 for all.")
    real_eval.add_argument("--include-report", action="store_true", help="Also generate a daily report for each case. Leave off when calibrating single-paper summaries.")
    real_eval.add_argument("--include-deep-read", action="store_true", help="Also generate a repo-local deep-read eval artifact for each selected case.")
    real_eval.add_argument("--check-fixtures", action="store_true", help="Compare generated real-case artifacts against approved fixtures under evals/real_cases/fixtures.")
    real_eval.add_argument("--update-fixtures", action="store_true", help="Refresh approved real-case fixtures from the current generated artifacts.")

    harness_check = subparsers.add_parser("harness-check", help="Run the standard eval governance gate: doctor + golden eval, and optionally real-case fixtures.")
    harness_check.add_argument("--include-real-eval", action="store_true", help="Also run real-case fixture checks after doctor and golden eval.")
    harness_check.add_argument("--real-case-ids", default="", help="Comma-separated real case ids for the real-eval portion of harness-check.")
    harness_check.add_argument("--limit", type=int, default=0, help="Only run the first N selected real cases during harness-check. Use 0 for all.")
    harness_check.add_argument("--include-report", action="store_true", help="Include daily report generation in the real-eval portion of harness-check.")
    harness_check.add_argument("--include-deep-read", action="store_true", help="Include repo-local deep-read eval generation in the real-eval portion of harness-check.")
    harness_check.add_argument("--update-golden", action="store_true", help="Refresh golden fixtures before finishing harness-check.")
    harness_check.add_argument("--update-real-fixtures", action="store_true", help="Refresh approved real-case fixtures during the real-eval portion of harness-check.")

    maintenance_check = subparsers.add_parser("maintenance-check", help="Run the maintenance loop: audit, safe adjustments, test, and final re-audit.")
    maintenance_check.add_argument("--auto-repair", action="store_true", help="Apply low-risk deterministic maintenance actions before testing.")
    maintenance_check.add_argument("--max-passes", type=int, default=2, help="Maximum maintenance passes when auto-repair is enabled.")
    maintenance_check.add_argument("--include-real-eval", action="store_true", help="Also include real-case fixture checks in the maintenance harness portion.")
    maintenance_check.add_argument("--real-case-ids", default="", help="Comma-separated real case ids for the maintenance harness portion.")
    maintenance_check.add_argument("--limit", type=int, default=0, help="Only run the first N selected real cases during maintenance. Use 0 for all.")
    maintenance_check.add_argument("--include-report", action="store_true", help="Include daily report generation in the maintenance real-eval portion.")
    maintenance_check.add_argument("--include-deep-read", action="store_true", help="Include repo-local deep-read generation in the maintenance real-eval portion.")
    maintenance_check.add_argument("--no-write-report", action="store_true", help="Skip writing the markdown maintenance report under log/maintenance/.")


def _add_support_commands(subparsers: argparse._SubParsersAction) -> None:
    config_ui = subparsers.add_parser("config-ui", help="Open a local configuration web UI.")
    config_ui.add_argument("--host", default="127.0.0.1", help="Host to bind the local config UI.")
    config_ui.add_argument("--port", type=int, default=8765, help="Port to bind the local config UI.")
    config_ui.add_argument("--no-browser", action="store_true", help="Do not auto-open the browser.")
    manual_status = subparsers.add_parser("manual-llm-status", help="List chatgpt_web_manual request bundles and their current status.")
    manual_status.add_argument("--limit", type=int, default=50, help="Maximum number of requests to show. Use 0 for all.")
    manual_status.add_argument("--pending-only", action="store_true", help="Only show requests still waiting for imported responses.")
    manual_import = subparsers.add_parser("manual-llm-import", help="Import a ChatGPT web response into a pending request bundle.")
    manual_import.add_argument("--request-id", required=True, help="Request id shown in manual-llm-status or the pending error message.")
    manual_import.add_argument(
        "--response-file",
        default="",
        help="Optional path to a text/markdown file containing the ChatGPT response. Use - to read from stdin. If omitted, uses the request's recommended file under data/chatgpt_web_manual/responses/.",
    )
    subparsers.add_parser("sources", help="List configured journal sources.")
    subparsers.add_parser("index", help="Repair Obsidian links and sync article index pages under the configured output root.")
    doctor = subparsers.add_parser("doctor", help="Check environment, paths, PDF tools, and control-plane consistency.")
    doctor.add_argument("--consistency-only", action="store_true", help="Only check config/template/tag consistency and skip machine-specific runtime dependency warnings.")


def _parse_source_ids(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def _handle_sources(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    del args
    for source in monitor.list_sources():
        print(f"{source.id:32} tier={source.tier:9} mode={source.mode:12} journal={source.journal_title}")
    return 0


def _handle_doctor(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    report = run_doctor(monitor.root, strict_runtime=not args.consistency_only)
    print(f"project_root={report['project_root']}")
    print(f"current_python={report['current_python']}")
    print(f"current_prefix={report['current_prefix']}")
    print(f"local_python={report['local_python']}")
    print(f"venv_active={report['venv_active']}")
    print(f"path_first={report['path_first']}")
    print(f"output_root={report['paths']['output_root']}")
    print(f"data_root={report['paths']['data_root']}")
    print(f"log_root={report['paths']['log_root']}")
    for tool_name, tool_path in report["tools"].items():
        print(f"{tool_name}={tool_path or 'MISSING'}")
    print(f"llm_provider={report['provider_status']['provider']}")
    print(f"codex_executable={report['provider_status']['codex_executable'] or 'MISSING'}")
    print(f"codex_available={report['provider_status']['codex_available']}")
    print(f"codex_model={report['provider_status']['codex_model'] or 'DEFAULT'}")
    print(f"openai_base_url={report['provider_status']['openai_base_url']}")
    print(f"openai_model={report['provider_status']['openai_model']}")
    print(f"openai_api_key_present={report['provider_status']['openai_api_key_present']}")
    print(f"openai_api_key_source={report['provider_status']['openai_api_key_source'] or 'NONE'}")
    print(f"chatgpt_web_manual_root={report['provider_status']['chatgpt_web_manual_root']}")
    print(f"chatgpt_web_manual_pending={report['provider_status']['chatgpt_web_manual_pending']}")
    print(f"chatgpt_web_manual_ready={report['provider_status']['chatgpt_web_manual_ready']}")
    print(f"chatgpt_web_manual_stale={report['provider_status']['chatgpt_web_manual_stale']}")
    print(f"skills_runtime_dependency={report['skills_runtime_dependency']}")
    for check in report.get("consistency_checks", []):
        print(f"check.{check['id']}={check['status']}")
    if report["warnings"]:
        print("warnings:")
        for item in report["warnings"]:
            print(f"- {item}")
        return 1
    print("warnings: none")
    return 0


def _handle_config_ui(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    serve_config_ui(monitor.root, host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def _handle_manual_llm_status(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    statuses = list_manual_requests(monitor.root, limit=args.limit, pending_only=bool(args.pending_only))
    print(render_manual_request_status(statuses))
    return 0


def _handle_manual_llm_import(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    if not args.response_file:
        result = import_manual_response_from_recommended_file(
            monitor.root,
            request_id=args.request_id,
        )
        print(f"Imported response for {result.request_id} ({result.request_kind or 'analysis'}) -> {result.response_json_path}")
        return 0
    if args.response_file == "-":
        response_text = sys.stdin.read()
    else:
        with open(args.response_file, "r", encoding="utf-8") as handle:
            response_text = handle.read()
    result = import_manual_response(
        monitor.root,
        request_id=args.request_id,
        response_text=response_text,
    )
    print(f"Imported response for {result.request_id} ({result.request_kind or 'analysis'}) -> {result.response_json_path}")
    return 0


def _handle_index(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    del args
    result = monitor.sync_output_library()
    print(f"Synced article index under {article_index_root()}/. output_root={output_root()}/ repaired_files={result.repaired_files} repaired_links={result.repaired_links} indexed_notes={result.indexed_notes} created_sub_indexes={result.created_sub_indexes}")
    print(f"Current summaries root: {article_summaries_root()}/")
    print(f"Current reports root: {reports_root()}/")
    return 0


def _handle_deep_read(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    result = run_deep_read(root=monitor.root, storage=monitor.storage, doi=args.doi, title=args.title, pdf_path=args.pdf, journal=args.journal, url=args.url)
    if result.success:
        print(f"Generated deep read {result.output_path} from {result.source_kind}.")
        if result.pdf_output_path:
            print(f"PDF resource: {result.pdf_output_path}")
        return 0
    print(result.message)
    return 2


def _handle_tag_candidates(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    candidates = filter_tag_candidates(monitor.root, min_count=args.min_count, limit=args.limit)
    if not args.no_write_report:
        report_path = write_tag_candidates_report(monitor.root, min_count=args.min_count, limit=args.limit)
        print(f"Wrote tag candidate review report to {report_path}.")
    if not candidates:
        print("No tag candidates matched the current filter.")
        return 0
    print(f"Matched {len(candidates)} tag candidates.")
    for item in candidates:
        contexts = ", ".join(f"{key}:{value}" for key, value in sorted(item.contexts.items())) or "-"
        print(f"- {item.tag} count={item.count} contexts={contexts} last_seen={item.last_seen or '-'}")
    return 0


def _handle_golden_eval(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    results = run_golden_eval(monitor.root, update=args.update)
    print(render_golden_eval_summary(results))
    return 0 if all(item.passed for item in results) else 1


def _handle_harness_audit(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    report = run_harness_audit(monitor.root, write_report=not bool(args.no_write_report))
    print(render_harness_audit_summary(report))
    return 0 if report.passed else 1


def _handle_harness_optimize(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    report = run_harness_optimize(monitor.root, write_report=not bool(args.no_write_report))
    print(render_harness_optimize_summary(report))
    return 0 if report.after_audit.passed else 1


def _handle_entropy_check(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    del args
    report = run_entropy_check(monitor.root)
    print(render_entropy_check_summary(report))
    return 0 if report.passed else 1


def _handle_real_eval(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    case_ids = _parse_source_ids(args.case_ids)
    if args.check_fixtures or args.update_fixtures:
        results, checks = run_real_case_fixture_eval(monitor.root, case_ids=case_ids or None, limit=args.limit, include_report=bool(args.include_report), include_deep_read=bool(args.include_deep_read), update=bool(args.update_fixtures))
        print(render_real_case_fixture_summary(results, checks))
        result_ok = (not results) or all(item.passed for item in results)
        checks_ok = bool(checks) and all(item.passed for item in checks)
        return 0 if result_ok and checks_ok else 1
    results = run_real_case_eval(monitor.root, case_ids=case_ids or None, limit=args.limit, include_report=bool(args.include_report), include_deep_read=bool(args.include_deep_read))
    print(render_real_case_eval_summary(results))
    return 0 if results and all(item.passed for item in results) else (0 if not results else 1)


def _handle_harness_check(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    real_case_ids = _parse_source_ids(args.real_case_ids)
    report = run_harness_check(monitor.root, include_real_eval=bool(args.include_real_eval), real_case_ids=real_case_ids or None, limit=args.limit, include_report=bool(args.include_report), include_deep_read=bool(args.include_deep_read), update_golden=bool(args.update_golden), update_real_fixtures=bool(args.update_real_fixtures))
    print(render_harness_check_summary(report))
    return 0 if report.passed else 1


def _handle_maintenance_check(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    real_case_ids = _parse_source_ids(args.real_case_ids)
    report = run_maintenance_cycle(monitor.root, auto_repair=bool(args.auto_repair), max_passes=args.max_passes, include_real_eval=bool(args.include_real_eval), real_case_ids=real_case_ids or None, limit=args.limit, include_report=bool(args.include_report), include_deep_read=bool(args.include_deep_read), write_report=not args.no_write_report)
    print(render_maintenance_summary(report))
    return 0 if report.passed else 1


def _handle_update(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    report_date = date.fromisoformat(args.date)
    result = monitor.update(report_date=report_date, days_back=args.days_back, max_per_source=args.max_per_source, hydrate=args.hydrate, source_ids=_parse_source_ids(args.source_ids))
    print(f"Fetched {result.fetched_count} candidate papers and kept {result.kept_count} records for {result.report_date.isoformat()}.")
    if result.error_count:
        print(f"Encountered {result.error_count} source errors.")
        for error in result.errors[:10]:
            print(f"- {error}")
    return 0


def _handle_report(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    report_date = date.fromisoformat(args.date)
    if not monitor.weekly_report_enabled():
        print("Weekly report generation is disabled. Enable it in the config UI or PROJECT_CONFIG.md first.")
        return 0
    report_path, stats = monitor.generate_windowed_report(report_date, window_days=args.window_days)
    print(f"Generated report {report_path} with {stats['paper_count']} papers across {stats['journal_count']} journals.")
    print(f"Article summaries were generated first under {article_summaries_root()}/ before the report.")
    return 0


def _handle_summaries(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    report_date = date.fromisoformat(args.date)
    summary_paths = monitor.generate_article_summary_files(report_date, window_days=args.window_days)
    print(f"Wrote {len(summary_paths)} article summaries under {article_summaries_root()}/.")
    return 0


def _handle_audit(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    del monitor
    report_date = date.fromisoformat(args.date)
    markdown_path, json_path, rows = generate_source_audit(report_date=report_date, window_days=args.window_days, max_per_source=args.max_per_source)
    print(f"Wrote source audit markdown to {markdown_path}.")
    print(f"Wrote source audit json to {json_path}.")
    print(f"Audit summary: sources={len(rows)} possible_missing={sum(1 for row in rows if row.possible_missing == '是')} review_needed={sum(1 for row in rows if row.possible_missing == '待核')}")
    return 0


def _handle_daily(args: argparse.Namespace, monitor: ScienceMonitor) -> int:
    report_date = date.fromisoformat(args.date)
    update_result, report_path, stats = monitor.run_daily(
        report_date=report_date,
        days_back=args.days_back,
        max_per_source=args.max_per_source,
        hydrate=True,
        source_ids=_parse_source_ids(args.source_ids),
    )
    if report_path is None:
        print(f"Fetched {update_result.fetched_count} candidates and kept {update_result.kept_count}. Weekly report generation is disabled, so only updates/summaries were produced.")
    else:
        print(f"Fetched {update_result.fetched_count} candidates, kept {update_result.kept_count}, and wrote {report_path}.")
        print(f"Report stats: papers={stats['paper_count']} journals={stats['journal_count']} highlights={stats['highlight_count']}")
        print(f"Article summaries were generated first under {article_summaries_root()}/ before the report.")
    if update_result.error_count:
        print(f"Encountered {update_result.error_count} source errors.")
        for error in update_result.errors[:10]:
            print(f"- {error}")
    return 0
