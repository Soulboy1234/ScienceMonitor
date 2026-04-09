from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .article_summary_meta import abbreviate_journal_name, first_author_label
from .config import chatgpt_web_manual_requests_root, chatgpt_web_manual_responses_root


@dataclass(frozen=True)
class ManualRequestBundle:
    request_id: str
    request_kind: str
    title: str
    prompt_signature: str
    request_dir: Path
    prompt_path: Path
    request_note_path: Path
    response_filename: str
    response_json_path: Path
    response_raw_path: Path


@dataclass(frozen=True)
class ManualRequestStatus:
    request_id: str
    request_kind: str
    title: str
    display_label: str
    status: str
    created_at: str
    updated_at: str
    last_imported_at: str
    request_dir: Path
    response_filename: str
    response_json_path: Path


@dataclass(frozen=True)
class ManualResponseImportResult:
    request_id: str
    request_kind: str
    title: str
    response_json_path: Path
    response_raw_path: Path
    status: str


class ManualResponsePending(RuntimeError):
    def __init__(self, bundle: ManualRequestBundle) -> None:
        self.bundle = bundle
        super().__init__(render_manual_pending_message([bundle]))


def prepare_manual_request_bundle(
    root: Path,
    *,
    request_id: str,
    request_kind: str,
    title: str,
    prompt: str,
    schema: dict[str, Any],
    reasoning_effort: str,
    context: dict[str, Any] | None = None,
) -> ManualRequestBundle:
    request_dir = chatgpt_web_manual_requests_root(root) / request_id
    request_dir.mkdir(parents=True, exist_ok=True)
    prompt_signature = _prompt_signature(prompt, schema)
    context = context or {}
    existing_metadata = _load_request_metadata(request_dir / "metadata.json")
    resource_hints = context.get("resource_hints", {}) if isinstance(context.get("resource_hints", {}), dict) else {}
    request_label = str(existing_metadata.get("request_label", "") or context.get("request_label", "") or title or request_id)
    response_filename = str(
        existing_metadata.get("response_filename", "") or _build_response_filename(request_kind, request_label, request_id)
    )
    response_json_path = chatgpt_web_manual_responses_root(root) / response_filename
    response_raw_path = chatgpt_web_manual_responses_root(root) / response_filename.replace(".json", ".raw.md")
    response_json_path.parent.mkdir(parents=True, exist_ok=True)
    response_template = _build_response_template(schema.get("schema", {}))
    prompt_path = request_dir / "prompt.md"
    request_note_path = request_dir / "request.md"
    prompt_text = _build_manual_prompt(
        prompt,
        response_template,
        response_filename=response_filename,
        resource_hints=resource_hints,
        pdf_hint_path=str(context.get("pdf_hint_path", "") or ""),
    )
    prompt_path.write_text(prompt_text + "\n", encoding="utf-8")

    shutil.rmtree(request_dir / "attachments", ignore_errors=True)
    shutil.rmtree(request_dir / "context", ignore_errors=True)

    now = datetime.now().isoformat(timespec="seconds")
    metadata = {
        "request_id": request_id,
        "request_kind": request_kind,
        "title": title,
        "prompt_signature": prompt_signature,
        "schema": schema,
        "schema_name": str(schema.get("name", "") or ""),
        "reasoning_effort": reasoning_effort or "",
        "created_at": existing_metadata.get("created_at", now),
        "updated_at": now,
        "last_imported_at": existing_metadata.get("last_imported_at", ""),
        "request_label": request_label,
        "response_filename": response_filename,
        "response_json_path": str(response_json_path),
        "response_raw_path": str(response_raw_path),
        "resource_hints": resource_hints,
        "pdf_hint_path": str(context.get("pdf_hint_path", "") or ""),
    }
    metadata_path = request_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    request_note_path.write_text(
        _build_request_note(
            request_id=request_id,
            request_kind=request_kind,
            title=title,
            reasoning_effort=reasoning_effort,
            prompt_path=prompt_path,
            response_json_path=response_json_path,
            pdf_hint_path=str(context.get("pdf_hint_path", "") or ""),
        )
        + "\n",
        encoding="utf-8",
    )
    return ManualRequestBundle(
        request_id=request_id,
        request_kind=request_kind,
        title=title,
        prompt_signature=prompt_signature,
        request_dir=request_dir,
        prompt_path=prompt_path,
        request_note_path=request_note_path,
        response_filename=response_filename,
        response_json_path=response_json_path,
        response_raw_path=response_raw_path,
    )


def load_manual_response(
    root: Path,
    *,
    request_id: str,
    prompt_signature: str,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    request_dir = chatgpt_web_manual_requests_root(root) / request_id
    metadata = _load_request_metadata(request_dir / "metadata.json")
    response_path = _response_json_path(root, request_id=request_id, metadata=metadata)
    payload = _load_wrapped_response(response_path, request_id=request_id, prompt_signature=prompt_signature)
    if payload is not None:
        return payload
    if schema is None:
        return None
    raw_payload = _load_direct_response_payload(response_path, schema)
    if raw_payload is None:
        return None
    _store_wrapped_response(
        response_json_path=response_path,
        response_raw_path=_response_raw_path(root, request_id=request_id, metadata=metadata),
        metadata_path=request_dir / "metadata.json",
        metadata=metadata,
        request_id=request_id,
        payload=raw_payload,
    )
    return raw_payload


def import_manual_response(
    root: Path,
    *,
    request_id: str,
    response_text: str,
) -> ManualResponseImportResult:
    request_dir = chatgpt_web_manual_requests_root(root) / request_id
    metadata_path = request_dir / "metadata.json"
    if not metadata_path.exists():
        raise ValueError(f"未找到 request_id={request_id} 的人工中转请求。目录：{request_dir}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    schema_wrapper = metadata.get("schema", {})
    if not schema_wrapper:
        raise ValueError(f"请求 {request_id} 缺少可恢复的 schema 信息。目录：{request_dir}")
    payload = _extract_json_payload(response_text)
    if "payload" in payload and isinstance(payload["payload"], dict):
        payload = payload["payload"]
    _validate_against_schema(payload, schema_wrapper.get("schema", {}), path="$")

    response_json_path = _response_json_path(root, request_id=request_id, metadata=metadata)
    response_raw_path = _response_raw_path(root, request_id=request_id, metadata=metadata)
    _store_wrapped_response(
        response_json_path=response_json_path,
        response_raw_path=response_raw_path,
        metadata_path=metadata_path,
        metadata=metadata,
        request_id=request_id,
        payload=payload,
        raw_text=response_text,
    )
    return ManualResponseImportResult(
        request_id=request_id,
        request_kind=str(metadata.get("request_kind", "") or ""),
        title=str(metadata.get("title", "") or ""),
        response_json_path=response_json_path,
        response_raw_path=response_raw_path,
        status="ready",
    )


def import_manual_response_from_recommended_file(
    root: Path,
    *,
    request_id: str,
) -> ManualResponseImportResult:
    request_dir = chatgpt_web_manual_requests_root(root) / request_id
    metadata_path = request_dir / "metadata.json"
    if not metadata_path.exists():
        raise ValueError(f"未找到 request_id={request_id} 的人工中转请求。目录：{request_dir}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    response_json_path = _response_json_path(root, request_id=request_id, metadata=metadata)
    if not response_json_path.exists():
        raise ValueError(
            f"未找到推荐响应文件：{response_json_path}。请把 ChatGPT 网页生成/下载的 JSON 文件保存到这个路径，"
            "或使用 --response-file 指定其它文件。"
        )
    return import_manual_response(
        root,
        request_id=request_id,
        response_text=response_json_path.read_text(encoding="utf-8"),
    )


def list_manual_requests(
    root: Path,
    *,
    limit: int = 50,
    pending_only: bool = False,
) -> list[ManualRequestStatus]:
    requests_root = chatgpt_web_manual_requests_root(root)
    if not requests_root.exists():
        return []
    statuses: list[ManualRequestStatus] = []
    for request_dir in sorted(requests_root.iterdir(), reverse=True):
        if not request_dir.is_dir():
            continue
        metadata_path = request_dir / "metadata.json"
        metadata = _load_request_metadata(metadata_path)
        if not metadata:
            continue
        status = _request_status(root, metadata)
        if pending_only and status != "pending":
            continue
        statuses.append(
            ManualRequestStatus(
                request_id=str(metadata.get("request_id", "") or request_dir.name),
                request_kind=str(metadata.get("request_kind", "") or ""),
                title=str(metadata.get("title", "") or ""),
                display_label=_manual_display_label(metadata, status),
                status=status,
                created_at=str(metadata.get("created_at", "") or ""),
                updated_at=str(metadata.get("updated_at", "") or ""),
                last_imported_at=str(metadata.get("last_imported_at", "") or ""),
                request_dir=request_dir,
                response_filename=str(metadata.get("response_filename", "") or f"{request_dir.name}.json"),
                response_json_path=_response_json_path(root, request_id=request_dir.name, metadata=metadata),
            )
        )
        if limit > 0 and len(statuses) >= limit:
            break
    return statuses


def manual_status_counts(root: Path) -> dict[str, int]:
    counts = {"pending": 0, "ready": 0, "stale": 0}
    for item in list_manual_requests(root, limit=0):
        counts[item.status] = counts.get(item.status, 0) + 1
    return counts


def render_manual_pending_message(bundles: list[ManualRequestBundle]) -> str:
    manual_root = str(bundles[0].request_dir.parent.parent) if bundles else "-"
    lines = [
        f"chatgpt_web_manual 已生成 {len(bundles)} 个请求包，但尚未导入响应。",
        f"请求根目录：{manual_root}",
        "处理步骤：",
        "1. 打开每个请求目录里的 request.md 和 prompt.md。",
        "2. 把 prompt.md 作为文件上传到 ChatGPT 网页；默认不需要再上传本地辅助文件。",
        "3. 下载 ChatGPT 生成的 JSON 文件，并按 request.md 的推荐文件名放到 responses/。",
        "4. 运行 manual-llm-import 导入响应，然后重新执行原命令。",
        "",
        "待处理请求：",
    ]
    for bundle in bundles:
        lines.append(f"- {bundle.request_id} -> {bundle.request_dir} -> {bundle.response_filename}")
    example_id = bundles[0].request_id if bundles else "<request_id>"
    lines.extend(
        [
            "",
            "导入命令示例：",
            f"./scripts/run_science_monitor.sh manual-llm-import --request-id {example_id}",
        ]
    )
    return "\n".join(line for line in lines if line != "")


def render_manual_request_status(statuses: list[ManualRequestStatus]) -> str:
    if not statuses:
        return "当前没有 chatgpt_web_manual 请求。"
    lines = [f"chatgpt_web_manual 请求数：{len(statuses)}"]
    for item in statuses:
        imported = item.last_imported_at or "-"
        lines.append(
            f"- {item.display_label} imported_at={imported} response={item.response_filename} dir={item.request_dir}"
        )
    return "\n".join(lines)


def _build_request_note(
    *,
    request_id: str,
    request_kind: str,
    title: str,
    reasoning_effort: str,
    prompt_path: Path,
    response_json_path: Path,
    pdf_hint_path: str,
) -> str:
    lines = [
        "# ChatGPT Web Manual Request",
        "",
        f"- request_id: `{request_id}`",
        f"- kind: `{request_kind}`",
        f"- title: `{title}`",
        f"- reasoning_effort: `{reasoning_effort or 'default'}`",
        "",
        "## How To Use",
        "",
        "1. 把 `prompt.md` 作为文件上传到 ChatGPT 网页，不需要手动复制 prompt 内容。",
        "2. 默认不要再额外上传本目录里的其他文件；如果你手头有原始 PDF，可自行上传原始 PDF。",
        "3. 要求 ChatGPT 创建并提供一个可下载 JSON 文件，不要在聊天正文里展开完整 JSON。",
        "4. 把网页生成/下载的 JSON 文件保存为下面的推荐文件名，直接放到 `data/chatgpt_web_manual/responses/`。",
        "5. 完成后运行：",
        f"   `./scripts/run_science_monitor.sh manual-llm-import --request-id {request_id}`",
        "6. 如果网页端仍只返回正文 JSON，可把那段 JSON 保存成推荐文件名，或用 `--response-file` 指定文件作为备用导入方式。",
        "7. 导入成功后，重新执行原命令。",
        "",
        "## Files",
        "",
        f"- prompt: `{prompt_path.name}`",
        f"- recommended response file: `{response_json_path.name}`",
    ]
    if pdf_hint_path:
        lines.append(f"- optional local pdf hint: `{pdf_hint_path}`")
    return "\n".join(lines)


def _build_manual_prompt(
    prompt: str,
    response_template: dict[str, Any],
    *,
    response_filename: str,
    resource_hints: dict[str, Any],
    pdf_hint_path: str,
) -> str:
    resource_lines = ["可用定位信息："]
    for key in ("title", "doi", "url", "journal", "published_date", "authors", "topic_labels", "report_date", "paper_count", "paper_titles"):
        value = str(resource_hints.get(key, "") or "").strip()
        if value:
            resource_lines.append(f"- {key}: {value}")
    if pdf_hint_path:
        resource_lines.append(f"- local_pdf_hint: {pdf_hint_path}")
    return "\n".join(
        [
            "你现在是 ScienceMonitor 的人工中转分析助手。",
            "请先自行用 DOI、网页、题目等线索检索论文或资料；如果本轮用户另外上传了 PDF，请优先使用 PDF。",
            "最终交付物必须严格满足下面要求：",
            f"1. 创建一个可下载 JSON 文件，文件名必须是 `{response_filename}`。",
            "2. 不要在聊天正文里展开完整 JSON；聊天正文只需简短说明已生成该文件。",
            "3. JSON 文件内容必须是一个合法 JSON 对象，键名必须与模板完全一致，不要新增字段，不要删字段。",
            "4. 某些信息拿不到时，也要保留字段，只在值里如实写“未获取到可靠信息”或类似说明。",
            "",
            *resource_lines,
            "",
            "请严格按这个 JSON 模板返回：",
            json.dumps(response_template, ensure_ascii=False, indent=2),
            "",
            "任务说明：",
            prompt.strip(),
            "",
            f"最后再提醒一次：请生成可下载文件 `{response_filename}`，不要在聊天正文里展开完整 JSON。",
        ]
    )


def _sanitize_filename(value: str) -> str:
    clean = re.sub(r"[^\w.\-]+", "_", str(value or "").strip(), flags=re.UNICODE).strip("._")
    return clean or "file.txt"


def _build_response_filename(request_kind: str, request_label: str, request_id: str) -> str:
    label = _sanitize_filename(request_label).replace(".", "_")
    short_request = _sanitize_filename(request_id)[:18]
    kind = _sanitize_filename(request_kind)
    return f"ScienceMonitor_{label}_{kind}_{short_request}.json"


def _prompt_signature(prompt: str, schema: dict[str, Any]) -> str:
    basis = json.dumps({"prompt": prompt, "schema": schema}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def _load_request_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _response_json_path(root: Path, *, request_id: str, metadata: dict[str, Any]) -> Path:
    filename = str(metadata.get("response_filename", "") or f"{request_id}.json")
    return chatgpt_web_manual_responses_root(root) / filename


def _response_raw_path(root: Path, *, request_id: str, metadata: dict[str, Any]) -> Path:
    filename = str(metadata.get("response_filename", "") or f"{request_id}.json")
    return chatgpt_web_manual_responses_root(root) / filename.replace(".json", ".raw.md")


def _load_wrapped_response(response_path: Path, *, request_id: str, prompt_signature: str) -> dict[str, Any] | None:
    if not response_path.exists():
        return None
    try:
        payload = json.loads(response_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if str(payload.get("request_id", "") or "") != request_id:
        return None
    if str(payload.get("prompt_signature", "") or "") != prompt_signature:
        return None
    structured = payload.get("payload")
    return structured if isinstance(structured, dict) else None


def _load_direct_response_payload(response_path: Path, schema_wrapper: dict[str, Any]) -> dict[str, Any] | None:
    if not response_path.exists():
        return None
    try:
        payload = json.loads(response_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if "payload" in payload and "request_id" in payload:
        return None
    try:
        _validate_against_schema(payload, schema_wrapper.get("schema", {}), path="$")
    except Exception:
        return None
    return payload


def _store_wrapped_response(
    *,
    response_json_path: Path,
    response_raw_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
    request_id: str,
    payload: dict[str, Any],
    raw_text: str | None = None,
) -> None:
    response_json_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    response_json_path.write_text(
        json.dumps(
            {
                "request_id": request_id,
                "request_kind": metadata.get("request_kind", ""),
                "title": metadata.get("title", ""),
                "imported_at": now,
                "prompt_signature": metadata.get("prompt_signature", ""),
                "payload": payload,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if raw_text is not None:
        response_raw_path.write_text(raw_text.rstrip() + "\n", encoding="utf-8")
    metadata["last_imported_at"] = now
    metadata["updated_at"] = now
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _request_status(root: Path, metadata: dict[str, Any]) -> str:
    request_id = str(metadata.get("request_id", "") or "")
    if not request_id:
        return "pending"
    response_path = _response_json_path(root, request_id=request_id, metadata=metadata)
    payload = _load_wrapped_response(
        response_path,
        request_id=request_id,
        prompt_signature=str(metadata.get("prompt_signature", "") or ""),
    )
    if payload is not None:
        return "ready"
    if response_path.exists():
        direct = _load_direct_response_payload(response_path, metadata.get("schema", {}))
        if direct is not None:
            return "ready"
        return "stale"
    return "pending"


def _manual_display_label(metadata: dict[str, Any], status: str) -> str:
    resource_hints = metadata.get("resource_hints", {})
    if not isinstance(resource_hints, dict):
        resource_hints = {}
    authors = str(resource_hints.get("authors", "") or "")
    published_date = str(resource_hints.get("published_date", "") or "")
    journal = str(resource_hints.get("journal", "") or "")
    title = str(resource_hints.get("title", "") or metadata.get("title", "") or "-")
    first_author = first_author_label(authors)
    year = published_date[:4] if len(published_date) >= 4 else "----"
    journal_short = abbreviate_journal_name(journal or "Unknown")
    status_text = {
        "pending": "待导入",
        "ready": "已就绪",
        "stale": "待修复",
    }.get(status, status)
    return f"【{status_text}】{first_author}（{year}）- {journal_short} - {title}"


def _extract_json_payload(text: str) -> dict[str, Any]:
    source = str(text or "").strip()
    if not source:
        raise ValueError("响应内容为空，无法导入。")
    direct = _try_parse_json_object(source)
    if direct is not None:
        return direct

    fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", source, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced_blocks:
        parsed = _try_parse_json_object(block.strip())
        if parsed is not None:
            return parsed

    decoder = json.JSONDecoder()
    for index, char in enumerate(source):
        if char != "{":
            continue
        try:
            candidate, end = decoder.raw_decode(source[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            tail = source[index + end :].strip()
            if not tail or tail.startswith("```"):
                return candidate
    raise ValueError("没有在响应中解析到合法 JSON 对象。请复制 ChatGPT 的完整 JSON 回复再导入。")


def _try_parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _validate_against_schema(value: Any, schema: dict[str, Any], *, path: str) -> None:
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} 必须是对象。")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ValueError(f"{path}.{key} 缺失。")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value.keys()) - set(properties.keys()))
            if extras:
                raise ValueError(f"{path} 包含未允许字段：{', '.join(extras)}")
        for key, item in value.items():
            if key in properties:
                _validate_against_schema(item, properties[key], path=f"{path}.{key}")
        return

    if schema_type == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} 必须是数组。")
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(value) < int(min_items):
            raise ValueError(f"{path} 至少需要 {min_items} 项。")
        if max_items is not None and len(value) > int(max_items):
            raise ValueError(f"{path} 最多允许 {max_items} 项。")
        item_schema = schema.get("items", {})
        for index, item in enumerate(value):
            _validate_against_schema(item, item_schema, path=f"{path}[{index}]")
        return

    if schema_type == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path} 必须是字符串。")
        enum = schema.get("enum")
        if enum is not None and value not in enum:
            raise ValueError(f"{path} 必须是以下值之一：{', '.join(str(item) for item in enum)}")
        return

    if schema_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{path} 必须是数值。")
        return

    if schema_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{path} 必须是整数。")
        return

    if schema_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{path} 必须是布尔值。")
        return


def _build_response_template(schema: dict[str, Any]) -> dict[str, Any]:
    schema_type = schema.get("type")
    if schema_type == "object":
        properties = schema.get("properties", {})
        return {
            key: _build_response_template(properties[key])
            for key in schema.get("required", properties.keys())
            if key in properties
        }
    if schema_type == "array":
        item_schema = schema.get("items", {})
        min_items = max(1, int(schema.get("minItems", 1) or 1))
        return [_build_response_template(item_schema) for _ in range(min_items)]
    if schema_type == "string":
        enum = schema.get("enum")
        if enum:
            return str(enum[0])
        return "请替换"
    if schema_type == "number":
        return 0
    if schema_type == "integer":
        return 0
    if schema_type == "boolean":
        return False
    return ""
