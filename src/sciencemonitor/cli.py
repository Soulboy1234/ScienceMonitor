from __future__ import annotations

import argparse

from .cli_support import build_parser, dispatch_command
from .config import load_runtime_config, sync_configs_from_project_markdown
from .pipeline import ScienceMonitor


def parse_args() -> argparse.Namespace:
    sync_configs_from_project_markdown()
    runtime = load_runtime_config()
    defaults = runtime.get("cli_defaults", {})
    parser = build_parser(defaults)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    monitor = ScienceMonitor()
    try:
        return dispatch_command(args, monitor)
    except RuntimeError as exc:
        print(str(exc))
        return 2
    finally:
        monitor.close()
