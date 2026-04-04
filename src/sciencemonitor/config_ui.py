from __future__ import annotations

import cgi
import json
import os
import webbrowser
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlparse

from .article_summary_markdown import sanitize_filename
from .config import (
    config_ui_state_path,
    load_runtime_config,
    path_config_path,
    project_root,
    runtime_config_path,
    sync_configs_from_project_markdown,
    write_project_config_markdown,
)
from .config_ui_page import (
    render_error_page as _render_error_page,
    render_page as _render_page,
    render_shutdown_page as _render_shutdown_page,
)
from .deep_reads import run_deep_read
from .doctor import run_doctor
from .llm import DEFAULT_ANALYSIS_CONFIG, SUPPORTED_ANALYSIS_PROVIDERS
from .pipeline import ScienceMonitor


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
            sync_configs_from_project_markdown(project)
            query = parse_qs(urlparse(self.path).query)
            status = _status_payload_from_query(query)
            doctor = run_doctor(project)
            runtime = load_runtime_config(project)
            analysis = _load_analysis_config(project)
            paths = _load_paths_config(project)
            payload = _render_page(project, runtime, analysis, paths, doctor, status)
            self._send_html(payload)

        def do_POST(self) -> None:  # noqa: N802
            action = urlparse(self.path).path or "/save-config"
            try:
                if action == "/shutdown-ui":
                    payload = _render_shutdown_page(project)
                    self._send_html(payload)
                    Thread(target=self.server.shutdown, daemon=True).start()
                    return

                form, files = _parse_form_data(self)
                if action == "/save-config":
                    _save_from_form(project, form)
                    params = {"kind": "ok", "title": "配置已保存", "message": "配置已保存，并同步回 PROJECT_CONFIG.md。"}
                elif action == "/run-report":
                    params = _run_report_action(project, form)
                elif action == "/run-deep-read":
                    params = _run_deep_read_action(project, form, files)
                else:
                    payload = _render_error_page(project, f"未知操作路径：{action}")
                    self._send_html(payload, status=HTTPStatus.NOT_FOUND)
                    return
            except Exception as exc:
                payload = _render_error_page(project, str(exc))
                self._send_html(payload, status=HTTPStatus.BAD_REQUEST)
                return

            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/?" + urlencode(params))
            self.end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send_html(self, payload: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return ConfigUIHandler


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
    analysis["article_summaries"].pop("fallback_to_rules", None)
    analysis["report"].pop("fallback_to_rules", None)
    analysis["deep_reads"].pop("fallback_to_rules", None)

    runtime["features"]["weekly_report_enabled"] = _bool_field(form, "weekly_report_enabled")

    runtime["cli_defaults"]["daily_days_back"] = _int_field(form, "daily_days_back", minimum=1)
    runtime["cli_defaults"]["daily_max_per_source"] = _int_field(form, "daily_max_per_source", minimum=1)
    runtime["cli_defaults"]["update_days_back"] = _int_field(form, "update_days_back", minimum=1)
    runtime["cli_defaults"]["update_max_per_source"] = _int_field(form, "update_max_per_source", minimum=1)
    runtime["cli_defaults"]["update_hydrate"] = _bool_field(form, "update_hydrate")
    runtime["cli_defaults"]["report_window_days"] = _int_field(form, "report_window_days", minimum=1)
    runtime["cli_defaults"]["summaries_window_days"] = _int_field(form, "summaries_window_days", minimum=1)
    runtime["cli_defaults"]["audit_window_days"] = _int_field(form, "audit_window_days", minimum=1)
    runtime["cli_defaults"]["audit_max_per_source"] = _int_field(form, "audit_max_per_source", minimum=1)

    runtime["deep_read"]["search_full_text_when_pdf_missing"] = _bool_field(form, "search_full_text_when_pdf_missing")
    runtime["deep_read"]["pdf_page_limit"] = _int_field(form, "pdf_page_limit", minimum=1)

    analysis["provider"] = _text_field(form, "provider") or "codex_local"
    if analysis["provider"] not in SUPPORTED_ANALYSIS_PROVIDERS:
        supported = "、".join(SUPPORTED_ANALYSIS_PROVIDERS)
        raise ValueError(f"provider 只支持：{supported}")
    analysis["article_summaries"]["enabled"] = _bool_field(form, "article_summaries_enabled")
    analysis["article_summaries"]["max_items_per_run"] = _int_field(form, "article_summaries_max_items_per_run", minimum=0)
    analysis["article_summaries"]["reasoning_effort"] = _text_field(form, "article_summaries_reasoning_effort") or "medium"
    analysis["report"]["enabled"] = _bool_field(form, "report_enabled")
    analysis["report"]["max_papers_in_prompt"] = _int_field(form, "report_max_papers_in_prompt", minimum=1)
    analysis["report"]["reasoning_effort"] = _text_field(form, "report_reasoning_effort") or "medium"
    analysis["deep_reads"]["enabled"] = _bool_field(form, "deep_reads_enabled")
    analysis["deep_reads"]["max_input_chars"] = _int_field(form, "deep_reads_max_input_chars", minimum=2000)
    analysis["deep_reads"]["reasoning_effort"] = _text_field(form, "deep_reads_reasoning_effort") or "high"
    analysis["codex_local"]["model"] = _text_field(form, "codex_model")
    analysis["codex_local"]["executable"] = _text_field(form, "codex_executable")
    analysis["codex_local"]["sandbox"] = _text_field(form, "codex_sandbox") or "read-only"
    analysis["codex_local"]["timeout_seconds"] = _int_field(form, "codex_timeout_seconds", minimum=30)
    analysis["openai_api"]["api_key"] = _text_field(form, "openai_api_key")
    analysis["openai_api"]["api_key_env"] = _text_field(form, "openai_api_key_env") or "SCIENCEMONITOR_OPENAI_API_KEY"
    analysis["openai_api"]["model"] = _text_field(form, "openai_model") or "gpt-5-mini"
    analysis["openai_api"]["base_url"] = _text_field(form, "openai_base_url") or "https://api.openai.com/v1/responses"
    analysis["openai_api"]["timeout_seconds"] = _int_field(form, "openai_timeout_seconds", minimum=30)

    paths["output_root"] = _text_field(form, "output_root")
    if not paths["output_root"]:
        raise ValueError("output_root 不能为空。")

    runtime_config_path(project).write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (project / "config" / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path_config_path(project).write_text(json.dumps(paths, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    if not path.exists():
        return {"output_root": "out"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"output_root": "out"}


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


def _run_report_action(project: Path, form: dict[str, list[str]]) -> dict[str, str]:
    report_date = _date_field(form, "report_date")
    window_days = _int_field(form, "report_window_days_run", minimum=1)
    run_update = _bool_field(form, "run_update_before_report")
    max_per_source = _int_field(form, "report_max_per_source_run", minimum=1)
    update_days_back = _int_field(form, "report_update_days_back", minimum=1)
    source_ids = _source_ids_field(form, "report_source_ids")

    monitor = ScienceMonitor(project)
    try:
        if not monitor.weekly_report_enabled():
            raise ValueError("周报功能当前已关闭。请先在配置中开启“启用周报生成功能”，再生成周报。")
        if run_update:
            update_result, report_path, stats = monitor.run_daily(
                report_date=report_date,
                days_back=update_days_back,
                max_per_source=max_per_source,
                source_ids=source_ids or None,
            )
            message = (
                f"已完成更新并生成周报。候选 {update_result.fetched_count} 条，保留 {update_result.kept_count} 篇；"
                f"周报覆盖 {stats.get('paper_count', 0)} 篇论文、{stats.get('journal_count', 0)} 本期刊。"
            )
            if update_result.error_count:
                message += f" 另有 {update_result.error_count} 个来源报错，请再检查日志。"
        else:
            report_path, stats = monitor.generate_windowed_report(report_date=report_date, window_days=window_days)
            message = (
                f"已基于当前数据库重建周报，窗口 {window_days} 天；"
                f"覆盖 {stats.get('paper_count', 0)} 篇论文、{stats.get('journal_count', 0)} 本期刊。"
            )
            if source_ids:
                message += " 注意：未勾选“先更新再生成”时，限定期刊 source_ids 不生效。"
        return {
            "kind": "ok",
            "title": "周报生成完成",
            "message": message,
            "path": str(report_path),
        }
    finally:
        monitor.close()


def _run_deep_read_action(
    project: Path,
    form: dict[str, list[str]],
    files: dict[str, cgi.FieldStorage],
) -> dict[str, str]:
    uploaded_pdf = files.get("deep_read_pdf")
    uploaded_path = _save_uploaded_pdf(project, uploaded_pdf) if uploaded_pdf else None
    local_pdf_path = _text_field(form, "deep_read_pdf_path")
    pdf_path = str(uploaded_path) if uploaded_path else local_pdf_path
    doi = _text_field(form, "deep_read_doi")
    title = _text_field(form, "deep_read_title")
    journal = _text_field(form, "deep_read_journal")
    url = _text_field(form, "deep_read_url")

    if not pdf_path and not doi and not title:
        raise ValueError("请至少提供 PDF、DOI 或论文题目中的一项。")

    monitor = ScienceMonitor(project)
    try:
        result = run_deep_read(
            root=project,
            storage=monitor.storage,
            doi=doi,
            title=title,
            pdf_path=pdf_path,
            journal=journal,
            url=url,
        )
    finally:
        monitor.close()

    if not result.success:
        return {
            "kind": "error",
            "title": "深度解读失败",
            "message": result.message,
            "path": str(uploaded_path) if uploaded_path else "",
        }

    message = f"已完成深度解读，全文来源类型：{result.source_kind or 'unknown'}。"
    if not pdf_path:
        message += " 本次未提供 PDF，系统已自动尝试获取全文。"
    return {
        "kind": "ok",
        "title": "深度解读完成",
        "message": message,
        "path": str(result.output_path) if result.output_path else "",
        "extra_path": str(result.pdf_output_path) if result.pdf_output_path else "",
    }


def _save_uploaded_pdf(project: Path, file_item: cgi.FieldStorage | None) -> Path | None:
    if file_item is None or not getattr(file_item, "filename", ""):
        return None
    filename = sanitize_filename(Path(str(file_item.filename)).name) or "uploaded.pdf"
    suffix = Path(filename).suffix.lower()
    content_type = str(getattr(file_item, "type", "") or "").lower()
    if suffix != ".pdf" and content_type != "application/pdf":
        raise ValueError("当前只支持上传 PDF 文件。")

    upload_dir = project / "tmp" / "ui_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(filename).stem or "uploaded"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = upload_dir / f"{timestamp}-{stem}.pdf"
    index = 1
    while candidate.exists():
        candidate = upload_dir / f"{timestamp}-{stem}-{index}.pdf"
        index += 1

    with candidate.open("wb") as handle:
        payload = file_item.file.read()
        handle.write(payload if isinstance(payload, bytes) else bytes(payload))
    return candidate


def _date_field(form: dict[str, list[str]], name: str) -> date:
    raw = _text_field(form, name)
    if not raw:
        raise ValueError(f"{name} 不能为空。")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是 YYYY-MM-DD 格式。") from exc


def _source_ids_field(form: dict[str, list[str]], name: str) -> set[str]:
    raw = _text_field(form, name)
    return {item.strip() for item in raw.split(",") if item.strip()}


def _deep_update(target: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _bool_field(form: dict[str, list[str]], name: str) -> bool:
    return name in form


def _int_field(form: dict[str, list[str]], name: str, minimum: int = 0) -> int:
    raw = _text_field(form, name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数。") from exc
    if value < minimum:
        raise ValueError(f"{name} 必须大于等于 {minimum}。")
    return value


def _text_field(form: dict[str, list[str]], name: str) -> str:
    return str(form.get(name, [""])[0]).strip()
