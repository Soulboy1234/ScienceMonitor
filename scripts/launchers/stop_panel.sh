#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SUPPORT_ROOT="$HOME/Library/Application Support/ScienceMonitorLauncher"
LOG_PATH="$SUPPORT_ROOT/config_ui_launcher.log"
STATE_PATH="$SUPPORT_ROOT/config_ui_state.json"
HOST="127.0.0.1"
BASE_PORT=8765
MAX_PORT_OFFSET=9
TITLE_MARKER="<title>ScienceMonitor Config UI</title>"

mkdir -p "$SUPPORT_ROOT"
cd "$PROJECT_ROOT" || exit 0

timestamp() {
  /bin/date '+%Y-%m-%d %H:%M:%S'
}

log() {
  echo "[$(timestamp)] $1" >> "$LOG_PATH"
}

read_state_field() {
  local field="$1"
  if [ ! -f "$STATE_PATH" ]; then
    return 1
  fi
  /usr/bin/python3 - "$STATE_PATH" "$field" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
field = sys.argv[2]
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)
value = payload.get(field)
if value is None:
    raise SystemExit(1)
print(value)
PY
}

clear_state() {
  /bin/rm -f "$STATE_PATH"
}

is_ui() {
  local port="$1"
  local html
  html=$(/usr/bin/curl -fsS --max-time 2 "http://$HOST:$port/" 2>/dev/null || true)
  [[ "$html" == *"$TITLE_MARKER"* ]]
}

find_running_port() {
  local state_port port
  state_port="$(read_state_field port 2>/dev/null || true)"
  if [[ "$state_port" =~ ^[0-9]+$ ]] && is_ui "$state_port"; then
    echo "$state_port"
    return 0
  fi
  for ((offset=0; offset<=MAX_PORT_OFFSET; offset++)); do
    port=$((BASE_PORT + offset))
    if is_ui "$port"; then
      echo "$port"
      return 0
    fi
  done
  return 1
}

request_shutdown() {
  local port="$1"
  /usr/bin/curl -fsS --max-time 2 -X POST "http://$HOST:$port/shutdown-ui" >/dev/null 2>&1
}

wait_until_stopped() {
  local port="$1"
  local tries=40
  while [ "$tries" -gt 0 ]; do
    if ! is_ui "$port"; then
      return 0
    fi
    /bin/sleep 0.25
    tries=$((tries - 1))
  done
  return 1
}

find_running_pids() {
  /bin/ps -Ao pid=,command= | /usr/bin/awk '/science_monitor.py config-ui/ && $0 !~ /launch_config_ui.py/ {print $1}'
}

terminate_pid() {
  local pid="$1"
  /bin/kill -TERM "$pid" >/dev/null 2>&1 || return 1
  local tries=25
  while [ "$tries" -gt 0 ]; do
    if ! /bin/kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    /bin/sleep 0.2
    tries=$((tries - 1))
  done
  return 1
}

show_failure() {
  /usr/bin/osascript -e 'display dialog "关闭操作面板失败，请查看日志：~/Library/Application Support/ScienceMonitorLauncher/config_ui_launcher.log" buttons {"好的"} default button "好的" with icon stop'
}

notify_success() {
  /usr/bin/osascript -e 'display notification "控制面板后台服务已关闭" with title "ScienceMonitor"' >/dev/null 2>&1 || true
}

log "stop applet request"

PORT="$(find_running_port 2>/dev/null || true)"
if [[ "$PORT" =~ ^[0-9]+$ ]]; then
  log "stop request on port $PORT"
  if request_shutdown "$PORT" && wait_until_stopped "$PORT"; then
    clear_state
    log "ui stopped on port $PORT"
    notify_success
    exit 0
  fi
  log "graceful shutdown failed on port $PORT"
fi

PIDS="$(find_running_pids)"
if [ -z "$PIDS" ]; then
  clear_state
  log "stop request: ui already stopped"
  notify_success
  exit 0
fi

ALL_STOPPED=1
while IFS= read -r PID; do
  [ -n "$PID" ] || continue
  if terminate_pid "$PID"; then
    log "terminated config-ui pid $PID"
  else
    log "failed to terminate config-ui pid $PID"
    ALL_STOPPED=0
  fi
done <<< "$PIDS"

if [ "$ALL_STOPPED" -eq 1 ]; then
  clear_state
  notify_success
  exit 0
fi

show_failure
exit 0
