#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT/.venv"
PYTHON_BIN="${PYTHON:-}"
REQUIREMENTS_FILE="$ROOT/scripts/requirements/requirements-local.txt"

link_pdf_tool() {
  local tool_name="$1"
  local resolved=""
  if command -v "$tool_name" >/dev/null 2>&1; then
    resolved="$(command -v "$tool_name")"
  fi
  if [[ -n "$resolved" ]]; then
    ln -sf "$resolved" "$VENV_DIR/bin/$tool_name"
    echo "Linked $tool_name -> $resolved"
    return 0
  fi
  return 1
}

install_pdf_tool_wrapper() {
  local tool_name="$1"
  local wrapper_path="$ROOT/scripts/${tool_name}_wrapper.py"
  cat >"$VENV_DIR/bin/$tool_name" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" "$wrapper_path" "\$@"
EOF
  chmod +x "$VENV_DIR/bin/$tool_name"
  echo "Installed local wrapper for $tool_name"
}

ensure_poppler_tools() {
  local missing=0
  for tool in pdftotext pdfinfo pdftoppm; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing=1
      break
    fi
  done

  if [[ "$missing" -eq 1 ]] && command -v brew >/dev/null 2>&1; then
    echo "Poppler tools not found. Attempting Homebrew install of poppler..."
    local brew_log="$ROOT/tmp/bootstrap_poppler.log"
    mkdir -p "$ROOT/tmp"
    if ! brew install poppler >"$brew_log" 2>&1; then
      echo "Homebrew install failed. Falling back to local Python wrappers. See $brew_log for details." >&2
    fi
  fi

  for tool in pdftotext pdfinfo pdftoppm; do
    if ! link_pdf_tool "$tool"; then
      install_pdf_tool_wrapper "$tool"
    fi
  done
}

ensure_playwright_browser() {
  if "$VENV_DIR/bin/python" - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("playwright") else 1)
PY
  then
    echo "Ensuring Playwright Chromium browser is available..."
    if ! "$VENV_DIR/bin/python" -m playwright install chromium >/dev/null 2>&1; then
      echo "Playwright Chromium install failed. UI visual review may not be available until it is installed manually." >&2
    fi
  fi
}

supports_required_python() {
  local candidate="$1"
  "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

if [[ -z "$PYTHON_BIN" ]]; then
  candidates=(
    "$VENV_DIR/bin/python"
  )
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      resolved="$candidate"
    elif command -v "$candidate" >/dev/null 2>&1; then
      resolved="$(command -v "$candidate")"
    else
      continue
    fi
    if supports_required_python "$resolved"; then
      PYTHON_BIN="$resolved"
      break
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "No compatible local Python interpreter found under $VENV_DIR." >&2
  echo "Please provide one explicitly with PYTHON=/path/to/python3.10+." >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE"
ensure_poppler_tools
ensure_playwright_browser

echo "Local environment is ready at: $VENV_DIR"
echo "Interpreter used: $PYTHON_BIN"
