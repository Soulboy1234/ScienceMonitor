from __future__ import annotations

import cgi
from datetime import date, datetime
from pathlib import Path

from .article_summary_markdown import sanitize_filename
from .config import chatgpt_web_manual_responses_root
from .config_ui_deep_read_jobs import start_deep_read_action, start_deep_read_folder_action
from .config_ui_report_jobs import execute_report_action, start_report_action
from .config_ui_support import (
    create_manual_request_from_ui,
    import_manual_response_and_generate,
    resolve_request_id_from_upload,
)


UPLOAD_CHUNK_BYTES = 1024 * 1024
MAX_MANUAL_RESPONSE_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SINGLE_PDF_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_FOLDER_PDF_UPLOAD_COUNT = 200
MAX_FOLDER_PDF_UPLOAD_BYTES = 500 * 1024 * 1024


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
    files: dict[str, object],
) -> dict[str, str]:
    uploaded_pdf = _first_file_item(files.get("deep_read_pdf"))
    uploaded_title = _uploaded_pdf_title(uploaded_pdf)
    uploaded_path = _save_uploaded_pdf(project, uploaded_pdf) if uploaded_pdf is not None else None
    local_pdf_path = _text_field(form, "deep_read_pdf_path")
    pdf_path = str(uploaded_path) if uploaded_path else local_pdf_path
    doi = _text_field(form, "deep_read_doi")
    title = _text_field(form, "deep_read_title")
    if not title and pdf_path:
        title = uploaded_title or Path(local_pdf_path or pdf_path).expanduser().stem
    journal = _text_field(form, "deep_read_journal")
    url = _text_field(form, "deep_read_url")

    if not pdf_path and not doi and not title:
        raise ValueError("请至少提供 PDF、DOI 或论文题目中的一项。")

    return start_deep_read_action(
        project,
        {
            "doi": doi,
            "title": title,
            "pdf_path": pdf_path,
            "uploaded_path": str(uploaded_path) if uploaded_path else "",
            "journal": journal,
            "url": url,
            "pdf_page_limit": _int_field(form, "deep_read_pdf_page_limit", minimum=0),
        },
    )


def _run_deep_read_folder_action(
    project: Path,
    form: dict[str, list[str]],
    files: dict[str, object] | None = None,
) -> dict[str, str]:
    files = files or {}
    folder_uploads = _file_items(files.get("deep_read_pdf_folder_uploads"))
    recursive = _bool_field(form, "deep_read_pdf_folder_recursive")
    uploaded_folder = _save_uploaded_pdf_folder(project, folder_uploads, recursive=recursive)
    folder_path = _text_field(form, "deep_read_pdf_folder_path")
    resolved_folder = str(uploaded_folder) if uploaded_folder else folder_path
    if not resolved_folder:
        raise ValueError("请选择 PDF 文件夹或填写要批量深度解读的 PDF 文件夹路径。")

    return start_deep_read_folder_action(
        project,
        {
            "folder_path": resolved_folder,
            "recursive": True if uploaded_folder else recursive,
            "pdf_page_limit": _int_field(form, "deep_read_folder_pdf_page_limit", minimum=0),
        },
    )


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
    response_bytes = _read_upload_bytes(upload.file, MAX_MANUAL_RESPONSE_UPLOAD_BYTES, "人工响应 JSON")
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

    try:
        with candidate.open("wb") as handle:
            _copy_upload_to_handle(file_item.file, handle, max_bytes=MAX_SINGLE_PDF_UPLOAD_BYTES, label="PDF 上传")
    except Exception:
        candidate.unlink(missing_ok=True)
        raise
    return candidate


def _save_uploaded_pdf_folder(project: Path, file_items: list[object], *, recursive: bool) -> Path | None:
    pdf_items = [
        item
        for item in file_items
        if getattr(item, "filename", "") and Path(str(item.filename)).suffix.lower() == ".pdf"
    ]
    if not pdf_items:
        return None
    if len(pdf_items) > MAX_FOLDER_PDF_UPLOAD_COUNT:
        raise ValueError(f"一次最多上传 {MAX_FOLDER_PDF_UPLOAD_COUNT} 个 PDF 文件。")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    upload_dir = project / "tmp" / "ui_folder_uploads" / timestamp
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_count = 0
    total_bytes = 0
    for item in pdf_items:
        relative = _safe_upload_relative_path(str(item.filename or "uploaded.pdf"))
        if not recursive and len(relative.parts) > 2:
            continue
        target = upload_dir.joinpath(*relative.parts[-1:] if not recursive and len(relative.parts) > 1 else relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = _unique_file_path(target)
        try:
            with target.open("wb") as handle:
                written = _copy_upload_to_handle(item.file, handle, max_bytes=MAX_SINGLE_PDF_UPLOAD_BYTES, label="PDF 文件夹上传")
        except Exception:
            target.unlink(missing_ok=True)
            raise
        total_bytes += written
        if total_bytes > MAX_FOLDER_PDF_UPLOAD_BYTES:
            target.unlink(missing_ok=True)
            raise ValueError("PDF 文件夹上传总量过大，config-ui 已拒绝处理。")
        saved_count += 1
    return upload_dir if saved_count else None


def _read_upload_bytes(file_obj, max_bytes: int, label: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file_obj.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"{label} 过大，config-ui 已拒绝处理。")
        chunks.append(chunk)
    return b"".join(chunks)


def _copy_upload_to_handle(file_obj, handle, *, max_bytes: int, label: str) -> int:
    total = 0
    while True:
        chunk = file_obj.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"{label} 过大，config-ui 已拒绝处理。")
        handle.write(chunk)
    return total


def _safe_upload_relative_path(filename: str) -> Path:
    parts = []
    for part in Path(filename).parts:
        if part in {"", ".", ".."}:
            continue
        clean = sanitize_filename(part)
        if clean:
            parts.append(clean)
    if not parts:
        parts = ["uploaded.pdf"]
    if Path(parts[-1]).suffix.lower() != ".pdf":
        parts[-1] = f"{Path(parts[-1]).stem or 'uploaded'}.pdf"
    return Path(*parts)


def _unique_file_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem or "uploaded"
    suffix = path.suffix or ".pdf"
    index = 1
    while True:
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _uploaded_pdf_title(file_item: cgi.FieldStorage | None) -> str:
    if file_item is None or not getattr(file_item, "filename", ""):
        return ""
    return sanitize_filename(Path(str(file_item.filename)).stem)


def _first_file_item(value: object) -> cgi.FieldStorage | object | None:
    if isinstance(value, list):
        return next((item for item in value if getattr(item, "filename", "")), None)
    return value if getattr(value, "filename", "") else None


def _file_items(value: object) -> list[object]:
    if isinstance(value, list):
        return [item for item in value if getattr(item, "filename", "")]
    if getattr(value, "filename", ""):
        return [value]
    return []


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
