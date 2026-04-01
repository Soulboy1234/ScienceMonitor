#!/bin/bash
set -u

PROJECT_ROOT="/Users/liwenbo/Documents/codex/ScienceMonitor"
RUNNER="$PROJECT_ROOT/scripts/run_science_monitor.sh"
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

write_state() {
  local port="$1"
  local pid="$2"
  local url="http://$HOST:$port/"
  cat >"$STATE_PATH" <<EOF
{"host":"$HOST","port":$port,"pid":$pid,"url":"$url","source":"applet-shell"}
EOF
}

is_ui() {
  local port="$1"
  local html
  html=$(/usr/bin/curl -fsS --max-time 2 "http://$HOST:$port/" 2>/dev/null || true)
  [[ "$html" == *"$TITLE_MARKER"* ]]
}

port_in_use() {
  local port="$1"
  /usr/sbin/lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

choose_port() {
  local state_port port
  state_port="$(read_state_field port 2>/dev/null || true)"
  if [[ "$state_port" =~ ^[0-9]+$ ]] && is_ui "$state_port"; then
    echo "$state_port"
    return 0
  fi
  for ((offset=0; offset<=MAX_PORT_OFFSET; offset++)); do
    port=$((BASE_PORT + offset))
    if port_in_use "$port"; then
      if is_ui "$port"; then
        echo "$port"
        return 0
      fi
      continue
    fi
    echo "$port"
    return 0
  done
  echo "$BASE_PORT"
}

spawn_server() {
  local port="$1"
  (
    cd "$PROJECT_ROOT" || exit 1
    export SCIENCEMONITOR_CONFIG_UI_STATE_PATH="$STATE_PATH"
    export SCIENCEMONITOR_SKIP_REEXEC=1
    nohup "$RUNNER" config-ui --host "$HOST" --port "$port" --no-browser >>"$LOG_PATH" 2>&1 </dev/null &
    echo $!
  )
}

wait_until_ready() {
  local port="$1"
  local tries=30
  while [ "$tries" -gt 0 ]; do
    if is_ui "$port"; then
      return 0
    fi
    /bin/sleep 0.5
    tries=$((tries - 1))
  done
  return 1
}

open_url() {
  local url="$1"
  /usr/bin/open "$url" >/dev/null 2>&1
}

show_failure() {
  /usr/bin/osascript -e 'display dialog "启动操作面板失败，请查看日志：~/Library/Application Support/ScienceMonitorLauncher/config_ui_launcher.log" buttons {"好的"} default button "好的" with icon stop'
}

show_manual_open() {
  local url="$1"
  /usr/bin/osascript -e "display dialog \"控制面板已启动，请手动打开：$url\" buttons {\"好的\"} default button \"好的\" with icon note"
}

log "start applet request"

if [ ! -x "$RUNNER" ]; then
  log "runner missing: $RUNNER"
  show_failure
  exit 0
fi

PORT="$(choose_port)"
PID="$(read_state_field pid 2>/dev/null || echo 0)"

if is_ui "$PORT"; then
  log "reusing existing config ui on port $PORT"
else
  log "spawning config ui on port $PORT"
  PID="$(spawn_server "$PORT" 2>>"$LOG_PATH")"
fi

if ! wait_until_ready "$PORT"; then
  log "failed to start ui on port $PORT"
  show_failure
  exit 0
fi

write_state "$PORT" "${PID:-0}"
URL="http://$HOST:$PORT/"
log "ui ready: $URL"

if ! open_url "$URL"; then
  log "browser open failed: $URL"
  show_manual_open "$URL"
else
  log "browser open requested: $URL"
fi

exit 0
