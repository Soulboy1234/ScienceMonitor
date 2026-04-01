#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT/.venv/bin/python"
REQUIREMENTS_FILE="$ROOT/scripts/requirements/requirements-local.txt"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Local Python environment not found: $PYTHON_BIN" >&2
  echo "Create it first with: python3 -m venv .venv && ./.venv/bin/pip install -r scripts/requirements/requirements-local.txt" >&2
  exit 1
fi

export VIRTUAL_ENV="$ROOT/.venv"
export PATH="$ROOT/.venv/bin:$PATH"
export PYTHONNOUSERSITE=1

exec "$PYTHON_BIN" "$ROOT/science_monitor.py" "$@"
