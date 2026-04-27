from __future__ import annotations

import cgi
from datetime import date, datetime
from pathlib import Path

from .article_summary_markdown import sanitize_filename
from .config import chatgpt_web_manual_responses_root, load_runtime_config
from .config_ui_report_jobs import execute_report_action, start_report_action
from .config_ui_support import (
    create_manual_request_from_ui,
    import_manual_response_and_generate,
    resolve_request_id_from_upload,
)
from .deep_reads import run_deep_read
from .pipeline import ScienceMonitor


def _start_report_action(project: Path, form: dict[str, list[str]]) -> dict[str, str]:
    params = _parse_report_form(form)
    return start_report_action(project, params)


def _run_report_action(project: Path, form: dict[str, list[str]]) -> dict[str, str]:
    params = _parse_report_form(form)
    return execute_report_action(project, params)


def _parse_report_form(form: dict[str, list[str]]) -> dict[str, object]:
    return {
        "report_date": _date_field(form, "report_date"),
        "window_days": _int_field(form, "report_window_days_run", minimum=1),
        "run_update": _bool_field(form, "run_update_before_report"),
        "hydrate": _bool_field(form, "report_update_hydrate"),
        "reuse_existing_summaries": _bool_field(form, "reuse_existing_summaries"),
        "max_per_source": _int_field(form, "report_max_per_source_run", minimum=1),
        "update_days_back": _int_field(form, "report_update_days_back", minimum=1),
        "source_ids": _source_ids_field(form, "report_source_ids"),
    }


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

    runtime = load_runtime_config(project)
    runtime.setdefault("deep_read", {})
    runtime["deep_read"]["pdf_page_limit"] = _int_field(form, "deep_read_pdf_page_limit", minimum=0)

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
            runtime_override=runtime,
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


def _run_manual_import_action(project: Path, form: dict[str, list[str]]) -> dict[str, str]:
    request_id = _text_field(form, "manual_request_id")
    if not request_id:
        raise ValueError("manual request_id 不能为空。")
    response_file = _text_field(form, "manual_response_file")
    if response_file:
        response_path = Path(response_file).expanduser()
        if not response_path.is_absolute():
            response_path = chatgpt_web_manual_responses_root(project) / response_path
        result = import_manual_response_and_generate(
            project,
            request_id=request_id,
            response_text=response_path.read_text(encoding="utf-8"),
        )
    else:
        result = import_manual_response_and_generate(project, request_id=request_id)
    return {
        "kind": "ok",
        "title": result["title"],
        "message": result["message"],
        "path": result["path"],
        "extra_path": result["extra_path"],
    }


def _run_manual_create_action(project: Path, form: dict[str, list[str]]) -> dict[str, str]:
    request_kind = _text_field(form, "manual_create_kind")
    title = _text_field(form, "manual_create_title")
    doi = _text_field(form, "manual_create_doi")
    journal = _text_field(form, "manual_create_journal")
    url = _text_field(form, "manual_create_url")
    if not title and not doi:
        raise ValueError("人工中转请求至少需要论文题目或 DOI。")
    bundle = create_manual_request_from_ui(
        project,
        request_kind=request_kind,
        title=title,
        doi=doi,
        journal=journal,
        url=url,
    )
    return {
        "kind": "ok",
        "title": "人工中转请求已生成",
        "message": "请求文件已生成，请把 prompt.md 拖到 ChatGPT 网页继续处理。",
        "path": str(bundle.prompt_path),
        "extra_path": str(bundle.request_note_path),
    }


def _run_manual_import_upload_action(
    project: Path,
    form: dict[str, list[str]],
    files: dict[str, cgi.FieldStorage],
) -> dict[str, str]:
    upload = files.get("manual_response_upload")
    if upload is None or not getattr(upload, "filename", ""):
        raise ValueError("请先上传 ChatGPT 返回的响应文件。")
    response_bytes = upload.file.read()
    response_text = response_bytes.decode("utf-8") if isinstance(response_bytes, bytes) else str(response_bytes)
    request_id = resolve_request_id_from_upload(
        project,
        filename=str(upload.filename or ""),
        response_text=response_text,
        request_id_hint=_text_field(form, "manual_request_id"),
    )
    result = import_manual_response_and_generate(
        project,
        request_id=request_id,
        response_text=response_text,
    )
    return {
        "kind": "ok",
        "title": result["title"],
        "message": result["message"],
        "path": result["path"],
        "extra_path": result["extra_path"],
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
