from __future__ import annotations

import cgi
import json
import os
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlparse, unquote

from .chatgpt_web_manual import (
    list_manual_requests,
)
from .config import (
    config_ui_state_path,
    local_path_config_path,
    load_runtime_config,
    output_root,
    path_config_path,
    project_root,
    runtime_config_path,
    sync_configs_from_project_markdown,
    write_project_config_markdown,
)
from .config_ui_actions import (
    _int_field,
    _run_deep_read_action,
    _run_manual_create_action,
    _run_manual_import_action,
    _run_manual_import_upload_action,
    _run_report_action,
    _text_field,
)
from .config_ui_page import (
    render_error_page as _render_error_page,
    render_page as _render_page,
    render_shutdown_page as _render_shutdown_page,
)
from .config_ui_support import (
    collect_config_ui_state,
)
from .doctor import run_doctor
from .llm import DEFAULT_ANALYSIS_CONFIG


def serve_config_ui(
    root: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    project = root or project_root()
    server = ThreadingHTTPServer((host, port), _build_handler(project))
    url = f"http://{host}:{port}/"
    _write_config_ui_state(project, host=host, port=port, url=url)
    print(f"ScienceMonitor config UI is running at {url}")
    print("Press Ctrl-C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _clear_config_ui_state(project)


def _build_handler(project: Path):
    class ConfigUIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            _handle_get_request(self, project)

        def do_POST(self) -> None:  # noqa: N802
            _handle_post_request(self, project)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send_html(self, payload: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_local_file(self, parsed) -> None:
            _serve_local_file(self, project, parsed)

    return ConfigUIHandler


def _handle_get_request(handler: BaseHTTPRequestHandler, project: Path) -> None:
    parsed = urlparse(handler.path)
    if parsed.path == "/local-file":
        handler._send_local_file(parsed)  # type: ignore[attr-defined]
        return
    sync_configs_from_project_markdown(project)
    query = parse_qs(parsed.query)
    status = _status_payload_from_query(query)
    doctor = run_doctor(project, strict_runtime=False)
    runtime = load_runtime_config(project)
    analysis = _load_analysis_config(project)
    paths = _load_paths_config(project)
    manual_requests = list_manual_requests(project, limit=8)
    ui_state = collect_config_ui_state(project)
    payload = _render_page(
        project,
        runtime,
        analysis,
        paths,
        doctor,
        status,
        manual_requests=manual_requests,
        ui_state=ui_state,
    )
    handler._send_html(payload)  # type: ignore[attr-defined]


def _handle_post_request(handler: BaseHTTPRequestHandler, project: Path) -> None:
    action = urlparse(handler.path).path or "/save-config"
    try:
        if action == "/shutdown-ui":
            payload = _render_shutdown_page(project)
            handler._send_html(payload)  # type: ignore[attr-defined]
            Thread(target=handler.server.shutdown, daemon=True).start()
            return

        form, files = _parse_form_data(handler)
        if action == "/save-config":
            _save_from_form(project, form)
            params = {"kind": "ok", "title": "配置已保存", "message": "配置已保存，并同步回 PROJECT_CONFIG.md。"}
        elif action == "/run-report":
            params = _run_report_action(project, form)
        elif action == "/run-deep-read":
            params = _run_deep_read_action(project, form, files)
        elif action == "/manual-llm-create":
            params = _run_manual_create_action(project, form)
        elif action == "/manual-llm-import":
            params = _run_manual_import_action(project, form)
        elif action == "/manual-llm-import-upload":
            params = _run_manual_import_upload_action(project, form, files)
        else:
            payload = _render_error_page(project, f"未知操作路径：{action}")
            handler._send_html(payload, status=HTTPStatus.NOT_FOUND)  # type: ignore[attr-defined]
            return
    except Exception as exc:
        payload = _render_error_page(project, str(exc))
        handler._send_html(payload, status=HTTPStatus.BAD_REQUEST)  # type: ignore[attr-defined]
        return

    handler.send_response(HTTPStatus.SEE_OTHER)
    handler.send_header("Location", "/?" + urlencode(params))
    handler.end_headers()


def _serve_local_file(handler: BaseHTTPRequestHandler, project: Path, parsed) -> None:
    raw_path = parse_qs(parsed.query).get("path", [""])[0]
    if not raw_path:
        handler._send_html(_render_error_page(project, "缺少 path 参数。"), status=HTTPStatus.BAD_REQUEST)  # type: ignore[attr-defined]
        return
    target = Path(unquote(raw_path)).expanduser().resolve()
    allowed_roots = [project.resolve(), output_root(project).resolve()]
    if not any(_is_relative_to(target, base) for base in allowed_roots):
        handler._send_html(_render_error_page(project, "只允许访问项目目录内的文件。"), status=HTTPStatus.FORBIDDEN)  # type: ignore[attr-defined]
        return
    if not target.exists() or not target.is_file():
        handler._send_html(_render_error_page(project, f"文件不存在：{target}"), status=HTTPStatus.NOT_FOUND)  # type: ignore[attr-defined]
        return
    content_type = "text/plain; charset=utf-8"
    if target.suffix.lower() == ".md":
        content_type = "text/markdown; charset=utf-8"
    elif target.suffix.lower() == ".json":
        content_type = "application/json; charset=utf-8"
    elif target.suffix.lower() == ".pdf":
        content_type = "application/pdf"
    encoded = target.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Content-Disposition", f'inline; filename="{target.name}"')
    handler.end_headers()
    handler.wfile.write(encoded)


def _save_from_form(project: Path, form: dict[str, list[str]]) -> None:
    runtime = load_runtime_config(project)
    analysis = _load_analysis_config(project)
    paths = _load_paths_config(project)

    runtime.setdefault("features", {})
    runtime.setdefault("cli_defaults", {})
    runtime.setdefault("deep_read", {})
    analysis.setdefault("article_summaries", {})
    analysis.setdefault("report", {})
    analysis.setdefault("deep_reads", {})
    analysis.setdefault("codex_local", {})
    analysis.setdefault("openai_api", {})
    analysis.setdefault("openrouter_api", {})
    analysis.setdefault("chatgpt_web_manual", {})
    analysis["article_summaries"].pop("fallback_to_rules", None)
    analysis["article_summaries"].pop("enabled", None)
    analysis["article_summaries"].pop("max_items_per_run", None)
    analysis["report"].pop("fallback_to_rules", None)
    analysis["report"].pop("enabled", None)
    analysis["report"].pop("max_papers_in_prompt", None)
    analysis["deep_reads"].pop("fallback_to_rules", None)
    analysis["deep_reads"].pop("enabled", None)
    analysis["deep_reads"].pop("max_input_chars", None)

    runtime["features"]["weekly_report_enabled"] = True

    analysis["provider"] = _text_field(form, "provider") or "codex_local"
    if analysis["provider"] not in {"codex_local", "openai_api", "openrouter_api"}:
        raise ValueError("provider 只支持：codex_local、openai_api、openrouter_api。人工中转请在“人工中转”页面执行。")
    analysis["article_summaries"]["reasoning_effort"] = _text_field(form, "article_summaries_reasoning_effort") or str(analysis["article_summaries"].get("reasoning_effort", "medium") or "medium")
    analysis["report"]["reasoning_effort"] = _text_field(form, "report_reasoning_effort") or str(analysis["report"].get("reasoning_effort", "medium") or "medium")
    analysis["deep_reads"]["reasoning_effort"] = _text_field(form, "deep_reads_reasoning_effort") or str(analysis["deep_reads"].get("reasoning_effort", "high") or "high")
    analysis["codex_local"]["model"] = _text_field(form, "codex_model") or str(analysis["codex_local"].get("model", "") or "")
    analysis["codex_local"]["executable"] = _text_field(form, "codex_executable") or str(analysis["codex_local"].get("executable", "") or "")
    analysis["codex_local"]["sandbox"] = _text_field(form, "codex_sandbox") or str(analysis["codex_local"].get("sandbox", "read-only") or "read-only")
    analysis["codex_local"]["timeout_seconds"] = _optional_int_field(form, "codex_timeout_seconds", int(analysis["codex_local"].get("timeout_seconds", 300) or 300), minimum=30)
    analysis["openai_api"]["api_key"] = _text_field(form, "openai_api_key") or str(analysis["openai_api"].get("api_key", "") or "")
    analysis["openai_api"]["api_key_env"] = _text_field(form, "openai_api_key_env") or str(analysis["openai_api"].get("api_key_env", "SCIENCEMONITOR_OPENAI_API_KEY") or "SCIENCEMONITOR_OPENAI_API_KEY")
    analysis["openai_api"]["model"] = _text_field(form, "openai_model") or str(analysis["openai_api"].get("model", "gpt-5-mini") or "gpt-5-mini")
    analysis["openai_api"]["base_url"] = _text_field(form, "openai_base_url") or str(analysis["openai_api"].get("base_url", "https://api.openai.com/v1/responses") or "https://api.openai.com/v1/responses")
    analysis["openai_api"]["timeout_seconds"] = _optional_int_field(form, "openai_timeout_seconds", int(analysis["openai_api"].get("timeout_seconds", 120) or 120), minimum=30)
    analysis["openrouter_api"]["api_key"] = _text_field(form, "openrouter_api_key") or str(analysis["openrouter_api"].get("api_key", "") or "")
    analysis["openrouter_api"]["api_key_env"] = _text_field(form, "openrouter_api_key_env") or str(analysis["openrouter_api"].get("api_key_env", "SCIENCEMONITOR_OPENROUTER_API_KEY") or "SCIENCEMONITOR_OPENROUTER_API_KEY")
    analysis["openrouter_api"]["model"] = _text_field(form, "openrouter_model") or str(analysis["openrouter_api"].get("model", "openai/gpt-5-mini") or "openai/gpt-5-mini")
    analysis["openrouter_api"]["base_url"] = _text_field(form, "openrouter_base_url") or str(analysis["openrouter_api"].get("base_url", "https://openrouter.ai/api/v1/chat/completions") or "https://openrouter.ai/api/v1/chat/completions")
    analysis["openrouter_api"]["site_url"] = _text_field(form, "openrouter_site_url") or str(analysis["openrouter_api"].get("site_url", "") or "")
    analysis["openrouter_api"]["app_name"] = _text_field(form, "openrouter_app_name") or str(analysis["openrouter_api"].get("app_name", "ScienceMonitor") or "ScienceMonitor")
    analysis["openrouter_api"]["timeout_seconds"] = _optional_int_field(form, "openrouter_timeout_seconds", int(analysis["openrouter_api"].get("timeout_seconds", 120) or 120), minimum=30)

    local_output_root = _text_field(form, "local_output_root")
    public_paths = {
        key: value
        for key, value in paths.items()
        if key not in {"local_output_root", "local_paths_config", "effective_output_root"}
    }

    runtime_config_path(project).write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (project / "config" / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path_config_path(project).write_text(json.dumps(public_paths, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_local_paths_config(project, local_output_root)
    write_project_config_markdown(project)


def _load_analysis_config(project: Path) -> dict:
    path = project / "config" / "analysis.json"
    merged = json.loads(json.dumps(DEFAULT_ANALYSIS_CONFIG))
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        _deep_update(merged, payload if isinstance(payload, dict) else {})
    return merged


def _load_paths_config(project: Path) -> dict:
    path = path_config_path(project)
    paths: dict
    if not path.exists():
        paths = {"output_root": "out"}
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        paths = payload if isinstance(payload, dict) else {"output_root": "out"}
    local_path = local_path_config_path(project)
    local_output_root = ""
    if local_path.exists():
        local_payload = json.loads(local_path.read_text(encoding="utf-8"))
        if isinstance(local_payload, dict):
            local_output_root = str(local_payload.get("output_root", "") or "")
    paths["local_output_root"] = local_output_root
    paths["local_paths_config"] = str(local_path)
    paths["effective_output_root"] = str(output_root(project))
    return paths


def _write_local_paths_config(project: Path, local_output_root: str) -> None:
    path = local_path_config_path(project)
    if not local_output_root:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"output_root": local_output_root}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _status_payload_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    return {
        "kind": query.get("kind", [""])[0],
        "title": query.get("title", [""])[0],
        "message": query.get("message", [""])[0],
        "path": query.get("path", [""])[0],
        "extra_path": query.get("extra_path", [""])[0],
    }


def _write_config_ui_state(project: Path, host: str, port: int, url: str) -> None:
    payload = {
        "pid": os.getpid(),
        "host": host,
        "port": port,
        "url": url,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    path = config_ui_state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clear_config_ui_state(project: Path) -> None:
    path = config_ui_state_path(project)
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        path.unlink(missing_ok=True)
        return
    if int(payload.get("pid", -1)) == os.getpid():
        path.unlink(missing_ok=True)


def _parse_form_data(handler: BaseHTTPRequestHandler) -> tuple[dict[str, list[str]], dict[str, cgi.FieldStorage]]:
    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
        "CONTENT_LENGTH": handler.headers.get("Content-Length", "0"),
    }
    form_data = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ=environ,
        keep_blank_values=True,
    )
    fields: dict[str, list[str]] = {}
    files: dict[str, cgi.FieldStorage] = {}
    if not form_data.list:
        return fields, files
    for item in form_data.list:
        if item.filename:
            files[item.name] = item
            continue
        fields.setdefault(item.name, []).append(str(item.value or ""))
    return fields, files


def _deep_update(target: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _optional_int_field(form: dict[str, list[str]], name: str, default: int, minimum: int = 0) -> int:
    if name not in form:
        return default
    return _int_field(form, name, minimum=minimum)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
