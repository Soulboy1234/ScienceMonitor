from __future__ import annotations

import argparse
from datetime import date

from .config import (
    article_index_root,
    article_summaries_root,
    load_runtime_config,
    output_root,
    reports_root,
    sync_configs_from_project_markdown,
)
from .config_ui import serve_config_ui
from .doctor import run_doctor
from .deep_reads import run_deep_read
from .pipeline import ScienceMonitor
from .source_audit import generate_source_audit


def parse_args() -> argparse.Namespace:
    sync_configs_from_project_markdown()
    runtime = load_runtime_config()
    defaults = runtime.get("cli_defaults", {})
    parser = argparse.ArgumentParser(description="Daily literature monitor for space physics journals.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily = subparsers.add_parser("daily", help="Run update + report.")
    daily.add_argument("--date", default=date.today().isoformat(), help="Report date in YYYY-MM-DD.")
    daily.add_argument("--days-back", type=int, default=int(defaults.get("daily_days_back", 7)), help="Fetch window length in days.")
    daily.add_argument("--max-per-source", type=int, default=int(defaults.get("daily_max_per_source", 20)), help="Maximum Crossref rows per source.")
    daily.add_argument(
        "--source-ids",
        default="",
        help="Comma-separated source ids for a targeted run, e.g. jgr_space_physics,space_weather",
    )

    update = subparsers.add_parser("update", help="Fetch and store papers only.")
    update.add_argument("--date", default=date.today().isoformat(), help="Report date in YYYY-MM-DD.")
    update.add_argument("--days-back", type=int, default=int(defaults.get("update_days_back", 7)), help="Fetch window length in days.")
    update.add_argument("--max-per-source", type=int, default=int(defaults.get("update_max_per_source", 20)), help="Maximum Crossref rows per source.")
    update.set_defaults(hydrate=bool(defaults.get("update_hydrate", True)))
    update_hydrate_group = update.add_mutually_exclusive_group()
    update_hydrate_group.add_argument(
        "--hydrate",
        dest="hydrate",
        action="store_true",
        help="Fetch article pages to fill missing abstracts when needed.",
    )
    update_hydrate_group.add_argument(
        "--no-hydrate",
        dest="hydrate",
        action="store_false",
        help="Skip article page fetching for missing abstracts.",
    )
    update.add_argument(
        "--source-ids",
        default="",
        help="Comma-separated source ids for a targeted run, e.g. jgr_space_physics,space_weather",
    )

    report = subparsers.add_parser("report", help="Generate the daily markdown report from stored papers.")
    report.add_argument("--date", default=date.today().isoformat(), help="Report date in YYYY-MM-DD.")
    report.add_argument(
        "--window-days",
        type=int,
        default=int(defaults.get("report_window_days", 7)),
        help="Summarize the recent N-day window ending on the report date.",
    )

    summaries = subparsers.add_parser("summaries", help="Generate per-paper markdown summaries from stored papers.")
    summaries.add_argument("--date", default=date.today().isoformat(), help="Report date in YYYY-MM-DD.")
    summaries.add_argument(
        "--window-days",
        type=int,
        default=int(defaults.get("summaries_window_days", 7)),
        help="Write summaries for the recent N-day window ending on the report date.",
    )

    audit = subparsers.add_parser("audit", help="Generate a per-source audit table for recent fetching coverage.")
    audit.add_argument("--date", default=date.today().isoformat(), help="Audit date in YYYY-MM-DD.")
    audit.add_argument(
        "--window-days",
        type=int,
        default=int(defaults.get("audit_window_days", 7)),
        help="Audit the recent N-day window ending on the audit date.",
    )
    audit.add_argument(
        "--max-per-source",
        type=int,
        default=int(defaults.get("audit_max_per_source", 100)),
        help="Maximum number of candidate works to request per source during audit.",
    )

    deep_read = subparsers.add_parser("deep-read", help="Generate a deep reading note from a PDF or fetched full text.")
    deep_read.add_argument("--doi", default="", help="Paper DOI.")
    deep_read.add_argument("--title", default="", help="Paper title when DOI is unavailable.")
    deep_read.add_argument("--pdf", default="", help="Optional local PDF path.")
    deep_read.add_argument("--journal", default="", help="Optional journal name.")
    deep_read.add_argument("--url", default="", help="Optional landing page URL.")

    config_ui = subparsers.add_parser("config-ui", help="Open a local configuration web UI.")
    config_ui.add_argument("--host", default="127.0.0.1", help="Host to bind the local config UI.")
    config_ui.add_argument("--port", type=int, default=8765, help="Port to bind the local config UI.")
    config_ui.add_argument("--no-browser", action="store_true", help="Do not auto-open the browser.")

    subparsers.add_parser("sources", help="List configured journal sources.")
    subparsers.add_parser("index", help="Repair Obsidian links and sync article index pages under the configured output root.")
    subparsers.add_parser("doctor", help="Check environment, paths, PDF tools, and LLM backend readiness.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    monitor = ScienceMonitor()
    source_ids = {item.strip() for item in getattr(args, "source_ids", "").split(",") if item.strip()}

    try:
        if args.command == "sources":
            for source in monitor.list_sources():
                print(
                    f"{source.id:32} tier={source.tier:9} mode={source.mode:12} journal={source.journal_title}"
                )
            return 0

        if args.command == "doctor":
            report = run_doctor(monitor.root)
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
            print(f"skills_runtime_dependency={report['skills_runtime_dependency']}")
            if report["warnings"]:
                print("warnings:")
                for item in report["warnings"]:
                    print(f"- {item}")
                return 1
            print("warnings: none")
            return 0

        if args.command == "config-ui":
            serve_config_ui(monitor.root, host=args.host, port=args.port, open_browser=not args.no_browser)
            return 0

        if args.command == "index":
            result = monitor.sync_output_library()
            print(
                f"Synced article index under {article_index_root()}/. output_root={output_root()}/ repaired_files={result.repaired_files} repaired_links={result.repaired_links} indexed_notes={result.indexed_notes} created_sub_indexes={result.created_sub_indexes}"
            )
            print(f"Current summaries root: {article_summaries_root()}/")
            print(f"Current reports root: {reports_root()}/")
            return 0

        if args.command == "deep-read":
            result = run_deep_read(
                root=monitor.root,
                storage=monitor.storage,
                doi=args.doi,
                title=args.title,
                pdf_path=args.pdf,
                journal=args.journal,
                url=args.url,
            )
            if result.success:
                print(f"Generated deep read {result.output_path} from {result.source_kind}.")
                if result.pdf_output_path:
                    print(f"PDF resource: {result.pdf_output_path}")
                return 0
            print(result.message)
            return 2

        report_date = date.fromisoformat(args.date)

        if args.command == "update":
            result = monitor.update(
                report_date=report_date,
                days_back=args.days_back,
                max_per_source=args.max_per_source,
                hydrate=args.hydrate,
                source_ids=source_ids,
            )
            print(
                f"Fetched {result.fetched_count} candidate papers and kept {result.kept_count} records for {result.report_date.isoformat()}."
            )
            if result.error_count:
                print(f"Encountered {result.error_count} source errors.")
                for error in result.errors[:10]:
                    print(f"- {error}")
            return 0

        if args.command == "report":
            if not monitor.weekly_report_enabled():
                print("Weekly report generation is disabled. Enable it in the config UI or PROJECT_CONFIG.md first.")
                return 0
            report_path, stats = monitor.generate_windowed_report(report_date, window_days=args.window_days)
            print(
                f"Generated report {report_path} with {stats['paper_count']} papers across {stats['journal_count']} journals."
            )
            print(f"Article summaries were generated first under {article_summaries_root()}/ before the report.")
            return 0

        if args.command == "summaries":
            summary_paths = monitor.generate_article_summary_files(report_date, window_days=args.window_days)
            print(f"Wrote {len(summary_paths)} article summaries under {article_summaries_root()}/.")
            return 0

        if args.command == "audit":
            markdown_path, json_path, rows = generate_source_audit(
                report_date=report_date,
                window_days=args.window_days,
                max_per_source=args.max_per_source,
            )
            print(f"Wrote source audit markdown to {markdown_path}.")
            print(f"Wrote source audit json to {json_path}.")
            print(
                f"Audit summary: sources={len(rows)} possible_missing={sum(1 for row in rows if row.possible_missing == '是')} review_needed={sum(1 for row in rows if row.possible_missing == '待核')}"
            )
            return 0

        if args.command == "daily":
            update_result, report_path, stats = monitor.run_daily(
                report_date=report_date,
                days_back=args.days_back,
                max_per_source=args.max_per_source,
                source_ids=source_ids,
            )
            if report_path is None:
                print(
                    f"Fetched {update_result.fetched_count} candidates and kept {update_result.kept_count}. Weekly report generation is disabled, so only updates/summaries were produced."
                )
            else:
                print(
                    f"Fetched {update_result.fetched_count} candidates, kept {update_result.kept_count}, and wrote {report_path}."
                )
                print(
                    f"Report stats: papers={stats['paper_count']} journals={stats['journal_count']} highlights={stats['highlight_count']}"
                )
                print(f"Article summaries were generated first under {article_summaries_root()}/ before the report.")
            if update_result.error_count:
                print(f"Encountered {update_result.error_count} source errors.")
                for error in update_result.errors[:10]:
                    print(f"- {error}")
            return 0
    finally:
        monitor.close()

    return 1
