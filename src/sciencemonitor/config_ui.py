from __future__ import annotations

import cgi
import json
import mimetypes
import secrets
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlparse, unquote

from .analysis_providers import AUTOMATIC_ANALYSIS_PROVIDERS
from .chatgpt_web_manual import (
    list_manual_requests,
)
from .config import (
    article_index_root,
    article_summaries_root,
    chatgpt_web_manual_requests_root,
    deep_reads_pdf_root,
    deep_reads_root,
    formal_tags_markdown_path,
    local_path_config_path,
    load_runtime_config,
    manual_notes_root,
    output_root,
    path_config_path,
    pending_tags_markdown_path,
    project_root,
    reports_root,
    runtime_config_path,
    sync_configs_from_project_markdown,
    write_project_config_markdown,
)
from .config_ui_actions import (
    _int_field,
    _run_deep_read_action,
    _run_deep_read_folder_action,
    _run_manual_create_action,
    _run_manual_import_action,
    _run_manual_import_upload_action,
    _start_report_action,
    _text_field,
)
from .config_ui_page import (
    render_error_page as _render_error_page,
    render_page as _render_page,
    render_shutdown_page as _render_shutdown_page,
)
from .config_ui_page_sections import _render_token_usage
from .config_ui_result_cards import render_latest_result_content, result_file_revision
from .config_ui_runtime import (
    active_config_ui_task,
    clear_config_ui_runtime_state,
    read_config_ui_runtime_state,
    write_config_ui_runtime_state,
)
from .config_ui_support import (
    collect_config_ui_state,
)
from .doctor import run_doctor
from .llm import DEFAULT_ANALYSIS_CONFIG
from .tag_governance import ensure_tag_governance_files, promote_selected_pending_tags


MAX_CONFIG_UI_FORM_BYTES = 600 * 1024 * 1024
MAX_LOCAL_FILE_BYTES = 100 * 1024 * 1024
LOCAL_FILE_EXTENSIONS = {".md", ".json", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".txt"}


def serve_config_ui(
    root: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    allow_non_loopback: bool = False,
) -> None:
    project = root or project_root()
    if not allow_non_loopback and not _is_loopback_host(host):
        raise ValueError("config-ui 默认只允许绑定 localhost/loopback；如确需局域网访问，请显式使用 --allow-non-loopback。")
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer((host, port), _build_handler(project, token))
    base_url = f"http://{_url_host(host)}:{port}/"
    url = base_url + "?" + urlencode({"token": token})
    write_config_ui_runtime_state(project, host=host, port=port, url=url, token=token)
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
        clear_config_ui_runtime_state(project)


def _build_handler(project: Path, token: str):
    class ConfigUIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            _handle_get_request(self, project, token)

        def do_POST(self) -> None:  # noqa: N802
            _handle_post_request(self, project, token)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send_html(self, payload: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_text(self, payload: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_local_file(self, parsed) -> None:
            _serve_local_file(self, project, parsed)

    return ConfigUIHandler


def _is_loopback_host(host: str) -> bool:
    normalized = str(host or "").strip().strip("[]").lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    if not normalized:
        return False
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _url_host(host: str) -> str:
    clean = str(host or "").strip()
    if ":" in clean and not clean.startswith("["):
        return f"[{clean}]"
    return clean


def _request_has_valid_token(handler: BaseHTTPRequestHandler, parsed, expected_token: str) -> bool:
    if not expected_token:
        return True
    candidates: list[str] = []
    candidates.extend(parse_qs(parsed.query).get("token", []))
    header_token = handler.headers.get("X-ScienceMonitor-UI-Token", "")
    if header_token:
        candidates.append(header_token)
    auth = handler.headers.get("Authorization", "")
    prefix = "Bearer "
    if auth.startswith(prefix):
        candidates.append(auth[len(prefix) :].strip())
    return any(secrets.compare_digest(candidate, expected_token) for candidate in candidates if candidate)


def _handle_get_request(handler: BaseHTTPRequestHandler, project: Path, token: str) -> None:
    parsed = urlparse(handler.path)
    if parsed.path == "/healthz":
        handler._send_text("ScienceMonitor config UI OK")  # type: ignore[attr-defined]
        return
    if not _request_has_valid_token(handler, parsed, token):
        handler._send_html(_render_error_page(project, "无效或缺失的 config-ui 会话 token。"), status=HTTPStatus.FORBIDDEN)  # type: ignore[attr-defined]
        return
    if parsed.path == "/local-file":
        handler._send_local_file(parsed)  # type: ignore[attr-defined]
        return
    if parsed.path == "/ui-status":
        ui_state = collect_config_ui_state(project)
        runtime_state = read_config_ui_runtime_state(project)
        handler._send_json(  # type: ignore[attr-defined]
            {
                "report_job": ui_state.get("report_job", {}),
                "deep_read_job": ui_state.get("deep_read_job", {}),
                "active_task": ui_state.get("active_task", {}),
                "manual_pending": _manual_pending_count(project),
                "latest_results": _latest_result_descriptors(ui_state),
                "latest_report": ui_state.get("latest_report", ""),
                "latest_deep_read": ui_state.get("latest_deep_read", ""),
                "latest_manual_result": ui_state.get("latest_manual_result", ""),
                "counts": ui_state.get("counts", {}),
                "token_usage": ui_state.get("token_usage", "今天 0（0次） / 本周 0（0次） / 本月 0（0次）"),
                "token_usage_periods": ui_state.get("token_usage_periods", {}),
                "token_usage_chart": ui_state.get("token_usage_chart", {}),
                "token_usage_html": _render_token_usage(ui_state),
                "ui_url": runtime_state.get("url", ""),
            }
        )
        return
    if parsed.path == "/latest-result":
        ui_state = collect_config_ui_state(project)
        payload = _latest_result_payload(project, ui_state, parse_qs(parsed.query).get("kind", [""])[0], token)
        handler._send_json(payload)  # type: ignore[attr-defined]
        return
    sync_configs_from_project_markdown(project)
    ensure_tag_governance_files(project, refresh_pending=True)
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
        ui_token=token,
    )
    handler._send_html(payload)  # type: ignore[attr-defined]


def _handle_post_request(handler: BaseHTTPRequestHandler, project: Path, token: str) -> None:
    parsed = urlparse(handler.path)
    action = parsed.path or "/save-config"
    if not _request_has_valid_token(handler, parsed, token):
        handler._send_html(_render_error_page(project, "无效或缺失的 config-ui 会话 token。"), status=HTTPStatus.FORBIDDEN)  # type: ignore[attr-defined]
        return
    try:
        _guard_no_conflicting_ui_task(project, action)
        if action == "/shutdown-ui":
            payload = _render_shutdown_page(project)
            handler._send_html(payload)  # type: ignore[attr-defined]
            Thread(target=handler.server.shutdown, daemon=True).start()
            return

        form, files = _parse_form_data(handler)
        if action == "/save-config":
            _save_from_form(project, form)
            params = {"kind": "ok", "title": "配置已保存", "message": "配置已保存，并同步回 PROJECT_CONFIG.md。"}
        elif action == "/promote-pending-tags":
            result = promote_selected_pending_tags(project)
            count = len(result.promoted_tags)
            if count:
                params = {
                    "kind": "ok",
                    "title": "预选tag已转正",
                    "message": f"已转正 {count} 个 tag，并从预选列表中剔除。",
                    "path": str(result.formal_markdown_path),
                    "extra_path": str(result.pending_markdown_path),
                }
            else:
                params = {
                    "kind": "ok",
                    "title": "没有可转正的tag",
                    "message": "当前预选文件里没有被勾选的 tag。",
                    "path": str(result.pending_markdown_path),
                }
        elif action == "/run-report":
            params = _start_report_action(project, form)
        elif action == "/run-deep-read":
            params = _run_deep_read_action(project, form, files)
        elif action == "/run-deep-read-folder":
            params = _run_deep_read_folder_action(project, form, files)
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

    redirect_fragment = _redirect_fragment_for_action(action)
    location_params = {"token": token, **params}
    location = "/?" + urlencode(location_params)
    if redirect_fragment:
        location += f"#{redirect_fragment}"
    handler.send_response(HTTPStatus.SEE_OTHER)
    handler.send_header("Location", location)
    handler.end_headers()


def _redirect_fragment_for_action(action: str) -> str:
    mapping = {
        "/run-report": "weekly-report",
        "/run-deep-read": "deep-read",
        "/run-deep-read-folder": "deep-read",
        "/manual-llm-create": "manual-llm",
        "/manual-llm-import": "manual-llm",
        "/manual-llm-import-upload": "manual-llm",
        "/save-config": "settings",
        "/promote-pending-tags": "settings",
    }
    return mapping.get(action, "")


def _manual_pending_count(project: Path) -> int:
    return sum(1 for item in list_manual_requests(project, limit=0) if item.status == "pending")


def _latest_result_descriptors(ui_state: dict) -> dict[str, dict[str, str]]:
    mapping = {
        "weekly_report": str(ui_state.get("latest_report", "") or ""),
        "deep_read": str(ui_state.get("latest_deep_read", "") or ""),
        "manual_result": str(ui_state.get("latest_manual_result", "") or ""),
    }
    return {
        key: {
            "path": path,
            "revision": result_file_revision(path),
        }
        for key, path in mapping.items()
    }


def _latest_result_payload(project: Path, ui_state: dict, kind: str, token: str = "") -> dict[str, str]:
    config = {
        "weekly_report": ("latest_report", "当前没有周报结果。"),
        "deep_read": ("latest_deep_read", "当前没有深度解读结果。"),
        "manual_result": ("latest_manual_result", "当前没有人工中转生成结果。"),
    }
    if kind not in config:
        return {"kind": kind, "path": "", "revision": "", "html": "未知最新结果类型。"}
    state_key, empty_text = config[kind]
    path_value = str(ui_state.get(state_key, "") or "")
    return {
        "kind": kind,
        "path": path_value,
        "revision": result_file_revision(path_value),
        "html": render_latest_result_content(project, path_value, empty_text, ui_token=token),
    }


def _guard_no_conflicting_ui_task(project: Path, action: str) -> None:
    guarded_actions = {
        "/run-report",
        "/run-deep-read",
        "/run-deep-read-folder",
        "/manual-llm-create",
        "/manual-llm-import",
        "/manual-llm-import-upload",
    }
    if action not in guarded_actions:
        return
    active_task = active_config_ui_task(project)
    if not active_task:
        return
    label = str(active_task.get("label", "任务") or "任务")
    step = str(active_task.get("step", "") or "")
    suffix = f"（当前步骤：{step}）" if step else ""
    raise ValueError(f"当前已有{label}正在运行{suffix}，请等待当前任务结束后再启动新的任务。")


def _serve_local_file(handler: BaseHTTPRequestHandler, project: Path, parsed) -> None:
    raw_path = parse_qs(parsed.query).get("path", [""])[0]
    if not raw_path:
        handler._send_html(_render_error_page(project, "缺少 path 参数。"), status=HTTPStatus.BAD_REQUEST)  # type: ignore[attr-defined]
        return
    target = Path(unquote(raw_path)).expanduser().resolve()
    if not target.exists() or not target.is_file():
        handler._send_html(_render_error_page(project, f"文件不存在：{target}"), status=HTTPStatus.NOT_FOUND)  # type: ignore[attr-defined]
        return
    if not _is_allowed_local_file(project, target):
        handler._send_html(_render_error_page(project, "只允许访问受信任的输出产物或人工中转请求文件。"), status=HTTPStatus.FORBIDDEN)  # type: ignore[attr-defined]
        return
    if target.stat().st_size > MAX_LOCAL_FILE_BYTES:
        handler._send_html(_render_error_page(project, "文件过大，无法通过 config-ui 直接打开。"), status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)  # type: ignore[attr-defined]
        return
    content_type = _local_file_content_type(target)
    encoded = target.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Content-Disposition", f'inline; filename="{target.name}"')
    handler.end_headers()
    handler.wfile.write(encoded)


def _is_allowed_local_file(project: Path, target: Path) -> bool:
    if target.suffix.lower() not in LOCAL_FILE_EXTENSIONS:
        return False
    trusted_files = {
        formal_tags_markdown_path(project).resolve(),
        pending_tags_markdown_path(project).resolve(),
    }
    if target in trusted_files:
        return True
    trusted_roots = [
        reports_root(project),
        article_summaries_root(project),
        deep_reads_root(project),
        deep_reads_pdf_root(project),
        article_index_root(project),
        manual_notes_root(project),
        chatgpt_web_manual_requests_root(project),
    ]
    return any(_is_relative_to(target, root.resolve()) for root in trusted_roots)


def _local_file_content_type(target: Path) -> str:
    suffix = target.suffix.lower()
    if suffix == ".md":
        return "text/markdown; charset=utf-8"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    if suffix == ".txt":
        return "text/plain; charset=utf-8"
    guessed = mimetypes.guess_type(str(target))[0]
    return guessed or "application/octet-stream"


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
    analysis.setdefault("ollama_api", {})
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
    if analysis["provider"] not in AUTOMATIC_ANALYSIS_PROVIDERS:
        choices = "、".join(AUTOMATIC_ANALYSIS_PROVIDERS)
        raise ValueError(f"provider 只支持：{choices}。人工中转请在“人工中转”页面执行。")
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
    analysis["ollama_api"]["model"] = _text_field(form, "ollama_model") or str(analysis["ollama_api"].get("model", "gemma4:26b") or "gemma4:26b")
    analysis["ollama_api"]["base_url"] = _text_field(form, "ollama_base_url") or str(analysis["ollama_api"].get("base_url", "http://127.0.0.1:11434/api/chat") or "http://127.0.0.1:11434/api/chat")
    analysis["ollama_api"]["timeout_seconds"] = _optional_int_field(form, "ollama_timeout_seconds", int(analysis["ollama_api"].get("timeout_seconds", 900) or 900), minimum=30)
    analysis["ollama_api"]["num_ctx"] = _optional_int_field(form, "ollama_num_ctx", int(analysis["ollama_api"].get("num_ctx", 32768) or 32768), minimum=0)
    analysis["ollama_api"]["num_predict"] = _optional_int_field(form, "ollama_num_predict", int(analysis["ollama_api"].get("num_predict", 4096) or 4096), minimum=0)
    analysis["ollama_api"]["deep_read_num_predict"] = _optional_int_field(form, "ollama_deep_read_num_predict", int(analysis["ollama_api"].get("deep_read_num_predict", 8192) or 8192), minimum=0)
    analysis["ollama_api"]["deep_read_quality_mode"] = _checkbox_field(form, "ollama_deep_read_quality_mode")
    _save_ollama_keep_alive(analysis["ollama_api"], form)

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


def _parse_form_data(handler: BaseHTTPRequestHandler) -> tuple[dict[str, list[str]], dict[str, object]]:
    content_length = _parse_content_length(handler)
    if content_length > MAX_CONFIG_UI_FORM_BYTES:
        raise ValueError("表单内容过大，config-ui 已拒绝处理。")
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
    files: dict[str, object] = {}
    if not form_data.list:
        return fields, files
    for item in form_data.list:
        if item.filename:
            existing = files.get(item.name)
            if existing is None:
                files[item.name] = item
            elif isinstance(existing, list):
                existing.append(item)
            else:
                files[item.name] = [existing, item]
            continue
        fields.setdefault(item.name, []).append(str(item.value or ""))
    return fields, files


def _parse_content_length(handler: BaseHTTPRequestHandler) -> int:
    raw_value = handler.headers.get("Content-Length", "0") or "0"
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError("Content-Length 无效，config-ui 已拒绝处理。") from exc
    if value < 0:
        raise ValueError("Content-Length 无效，config-ui 已拒绝处理。")
    return value


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


def _checkbox_field(form: dict[str, list[str]], name: str) -> bool:
    return name in form


def _save_ollama_keep_alive(settings: dict, form: dict[str, list[str]]) -> None:
    if "ollama_keep_alive" not in form:
        settings.setdefault("keep_alive", 0)
        return
    raw_value = _text_field(form, "ollama_keep_alive")
    if not raw_value:
        settings.pop("keep_alive", None)
        return
    settings["keep_alive"] = _coerce_keep_alive_value(raw_value)


def _coerce_keep_alive_value(value: str) -> int | str:
    text = str(value or "").strip()
    if text.lstrip("-").isdigit():
        return int(text)
    return text


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
