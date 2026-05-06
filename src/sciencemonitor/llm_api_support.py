from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from urllib import request
from urllib.parse import urlparse
from urllib.error import URLError

from .http import DEFAULT_HEADERS


@dataclass(frozen=True)
class StructuredApiResponse:
    payload: dict
    usage: dict[str, int]


class StructuredOutputParseError(RuntimeError):
    def __init__(self, provider: str, detail: str, output_text: str) -> None:
        self.provider = provider
        self.detail = detail
        self.output_text = output_text
        self.output_preview = output_text[:1200]
        super().__init__(f"{provider} returned invalid structured JSON: {detail}")


def extract_chat_completion_text(payload: dict) -> str:
    choices = payload.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text = str(item.get("text", "") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def resolve_api_key(settings: dict, *, env_name: str, fallback_env_name: str) -> str:
    configured_env = str(settings.get("api_key_env", "") or env_name).strip()
    if configured_env:
        value = os.environ.get(configured_env, "").strip()
        if value:
            return value
    direct = str(settings.get("api_key", "") or "").strip()
    if direct:
        return direct
    return os.environ.get(fallback_env_name, "").strip()


def resolve_api_key_source(settings: dict, *, env_name: str, fallback_env_name: str) -> str:
    configured_env = str(settings.get("api_key_env", "") or env_name).strip()
    if configured_env and os.environ.get(configured_env, "").strip():
        return configured_env
    if str(settings.get("api_key", "") or "").strip():
        return "config"
    if os.environ.get(fallback_env_name, "").strip():
        return fallback_env_name
    return ""


def resolve_base_url(settings: dict, *, default_url: str, provider_name: str, strict: bool = True) -> str:
    base_url = str(settings.get("base_url", default_url) or default_url).strip()
    parsed = urlparse(base_url)
    if parsed.scheme == "https":
        return base_url
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}:
        return base_url
    if strict:
        raise RuntimeError(f"{provider_name}.base_url must use https unless it points to localhost.")
    return base_url


def run_openai_structured(settings: dict, prompt: str, schema: dict) -> StructuredApiResponse:
    api_key = resolve_api_key(
        settings,
        env_name="SCIENCEMONITOR_OPENAI_API_KEY",
        fallback_env_name="OPENAI_API_KEY",
    )
    if not api_key:
        raise RuntimeError(
            "openai_api provider requires an API key via config/analysis.json "
            "or environment variable SCIENCEMONITOR_OPENAI_API_KEY."
        )
    base_url = resolve_base_url(
        settings,
        default_url="https://api.openai.com/v1/responses",
        provider_name="openai_api",
    )
    payload = {
        "model": str(settings.get("model", "gpt-5-mini") or "gpt-5-mini"),
        "instructions": "你是 Space Physics 文献分析助手。只根据给定标题、摘要和元数据输出中文分析，不要编造全文细节。",
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema["name"],
                "schema": schema["schema"],
                "strict": True,
            }
        },
    }
    req = request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=int(settings.get("timeout_seconds", 120) or 120)) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    output_text = data.get("output_text", "")
    if not output_text:
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output_text = content.get("text", "")
                    break
            if output_text:
                break
    if not output_text:
        raise RuntimeError("OpenAI response did not include output_text")
    return StructuredApiResponse(
        payload=_parse_structured_output("openai_api", output_text),
        usage=_extract_openai_usage(data.get("usage", {})),
    )


def run_openrouter_structured(settings: dict, prompt: str, schema: dict) -> StructuredApiResponse:
    api_key = resolve_api_key(
        settings,
        env_name="SCIENCEMONITOR_OPENROUTER_API_KEY",
        fallback_env_name="OPENROUTER_API_KEY",
    )
    if not api_key:
        raise RuntimeError(
            "openrouter_api provider requires an API key via config/analysis.json "
            "or environment variable SCIENCEMONITOR_OPENROUTER_API_KEY."
        )
    base_url = resolve_base_url(
        settings,
        default_url="https://openrouter.ai/api/v1/chat/completions",
        provider_name="openrouter_api",
    )
    payload = {
        "model": str(settings.get("model", "openai/gpt-5-mini") or "openai/gpt-5-mini"),
        "messages": [
            {
                "role": "system",
                "content": "你是 Space Physics 文献分析助手。只根据给定标题、摘要和元数据输出中文分析，不要编造全文细节。",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema["name"],
                "strict": True,
                "schema": schema["schema"],
            },
        },
    }
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    site_url = str(settings.get("site_url", "") or "").strip()
    app_name = str(settings.get("app_name", "ScienceMonitor") or "ScienceMonitor").strip()
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    req = request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=int(settings.get("timeout_seconds", 120) or 120)) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    output_text = extract_chat_completion_text(data)
    if not output_text:
        raise RuntimeError("OpenRouter response did not include structured text content")
    return StructuredApiResponse(
        payload=_parse_structured_output("openrouter_api", output_text),
        usage=_extract_openrouter_usage(data.get("usage", {})),
    )


def run_ollama_structured(
    settings: dict,
    prompt: str,
    schema: dict,
    *,
    request_name: str = "",
) -> StructuredApiResponse:
    model = str(settings.get("model", "gemma4:26b") or "gemma4:26b").strip()
    if not model:
        raise RuntimeError("ollama_api provider requires ollama_api.model, for example gemma4:26b.")
    base_url = resolve_base_url(
        settings,
        default_url="http://127.0.0.1:11434/api/chat",
        provider_name="ollama_api",
        strict=False,
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": _ollama_system_prompt(request_name),
            },
            {"role": "user", "content": _ollama_prompt_with_schema_contract(prompt, schema)},
        ],
        "options": _ollama_options(settings),
    }
    keep_alive = _ollama_keep_alive_value(settings)
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if "think" in settings:
        payload["think"] = bool(settings.get("think"))
    req = request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **DEFAULT_HEADERS,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    timeout_seconds = int(settings.get("timeout_seconds", 900) or 900)
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        if _is_timeout_error(exc):
            raise TimeoutError(f"ollama_api request timed out after {timeout_seconds}s") from exc
        raise
    except TimeoutError as exc:
        raise TimeoutError(f"ollama_api request timed out after {timeout_seconds}s") from exc
    output_text = str((data.get("message") or {}).get("content", "") or "").strip()
    if not output_text:
        output_text = str(data.get("response", "") or "").strip()
    if not output_text:
        raw_text = json.dumps(data, ensure_ascii=False, indent=2)
        raise StructuredOutputParseError(
            "ollama_api",
            "empty structured text content",
            raw_text,
        )
    return StructuredApiResponse(
        payload=_parse_structured_output("ollama_api", output_text, schema=schema),
        usage=_extract_ollama_usage(data),
    )


def _parse_structured_output(provider: str, output_text: str, *, schema: dict | None = None) -> dict:
    candidate = _extract_json_object_candidate(output_text)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        if provider == "ollama_api":
            for repaired in _ollama_json_repair_candidates(candidate):
                try:
                    payload = json.loads(repaired)
                    break
                except json.JSONDecodeError:
                    continue
            else:
                raise StructuredOutputParseError(provider, str(exc), output_text) from exc
        else:
            raise StructuredOutputParseError(provider, str(exc), output_text) from exc
    if not isinstance(payload, dict):
        raise StructuredOutputParseError(provider, "top-level JSON value is not an object", output_text)
    payload = _repair_structured_payload_aliases(payload, schema)
    required = ((schema or {}).get("schema") or {}).get("required", [])
    missing = [str(item) for item in required if str(item) not in payload]
    if missing:
        raise StructuredOutputParseError(provider, f"missing required fields: {', '.join(missing)}", output_text)
    return payload


def _repair_structured_payload_aliases(payload: dict, schema: dict | None) -> dict:
    schema_name = str((schema or {}).get("name", "") or "")
    aliases: dict[str, tuple[str, ...]] = {
        "chinese_title": (
            "chinese_und_title",
            "chinese_cn_title",
            "chinese_paper_title",
            "中文题目",
        ),
    }
    if schema_name == "deep_read_analysis":
        aliases.update(
            {
                "one_sentence_overview": ("one_sentence", "overview", "一句话总述"),
                "relation_to_my_work": ("my_work_relation", "relation_to_current_work", "和我已有工作的关系"),
                "follow_up_questions": (
                    "follow_up_args",
                    "followup_questions",
                    "follow_up",
                    "next_questions",
                    "后续值得追踪的问题",
                ),
                "needs_manual_review": ("manual_review", "need_manual_review", "需要人工复核"),
            }
        )
    repaired = dict(payload)
    for canonical, candidates in aliases.items():
        if canonical in repaired:
            continue
        for candidate in candidates:
            if candidate not in repaired:
                continue
            value = repaired.get(candidate)
            if value is None or value == "":
                continue
            repaired[canonical] = value
            break
    return repaired


def _escape_invalid_json_backslashes(candidate: str) -> str:
    return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", candidate)


def _ollama_json_repair_candidates(candidate: str) -> list[str]:
    escaped = _escape_invalid_json_backslashes(candidate)
    without_trailing_commas = _strip_json_trailing_commas(candidate)
    escaped_without_trailing_commas = _strip_json_trailing_commas(escaped)
    candidates: list[str] = []
    for item in [candidate, escaped, without_trailing_commas, escaped_without_trailing_commas]:
        candidates.append(item)
        candidates.append(_quote_unquoted_json_object_keys(item))
    deduped: list[str] = []
    for item in candidates:
        if item != candidate and item not in deduped:
            deduped.append(item)
    return deduped


def _quote_unquoted_json_object_keys(candidate: str) -> str:
    text = str(candidate or "")
    text = re.sub(r'(?m)(^\s*|[,{]\s*)([A-Za-z_][A-Za-z0-9_]*)"\s*:', r'\1"\2":', text)
    text = re.sub(r'(?m)(^\s*|[,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', text)
    return text


def _strip_json_trailing_commas(candidate: str) -> str:
    text = str(candidate or "")
    result: list[str] = []
    in_string = False
    escape = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "]}":
                index += 1
                continue
        result.append(char)
        index += 1
    return "".join(result)


def _extract_json_object_candidate(output_text: str) -> str:
    text = str(output_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    if start < 0:
        return text
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text[start:]


def _ollama_prompt_with_schema_contract(prompt: str, schema: dict) -> str:
    return "\n".join(
        [
            str(prompt or "").strip(),
            "",
            "Ollama 本地输出格式约束：",
            "1. 只输出一个合法 JSON 对象，不要输出 markdown、代码块、解释文字或前后缀。",
            "2. 字符串必须使用双引号，不能使用 Python 字典写法，不能截断字符串。",
            "3. 字段名必须完全使用下面列出的英文键名。",
            "4. 如果信息不足，也要用空字符串或空数组填充对应字段，不要省略 required 字段。",
            "",
            "JSON 字段契约：",
            _schema_contract_text(schema),
        ]
    ).strip()


def _schema_contract_text(schema: dict) -> str:
    schema_body = (schema or {}).get("schema") or {}
    properties = schema_body.get("properties", {})
    required = {str(item) for item in schema_body.get("required", [])}
    lines = ["{"]
    for index, (key, spec) in enumerate(properties.items()):
        suffix = "," if index < len(properties) - 1 else ""
        lines.append(f'  "{key}": {_schema_value_hint(spec)}{suffix}')
    lines.append("}")
    if required:
        lines.extend(["", f"必填字段：{', '.join(sorted(required))}"])
    return "\n".join(lines)


def _schema_value_hint(spec: object) -> str:
    if not isinstance(spec, dict):
        return '""'
    value_type = spec.get("type")
    if value_type == "array":
        item_spec = spec.get("items", {})
        return f"[{_schema_value_hint(item_spec)}]"
    if value_type == "object":
        properties = spec.get("properties", {})
        if not properties:
            return "{}"
        inner = ", ".join(f'"{key}": {_schema_value_hint(value)}' for key, value in properties.items())
        return "{" + inner + "}"
    if value_type == "integer":
        return "1"
    if value_type == "number":
        return "0"
    if value_type == "boolean":
        return "false"
    enum_values = spec.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return json.dumps(str(enum_values[0]), ensure_ascii=False)
    return '""'


def check_ollama_available(settings: dict) -> bool:
    base_url = resolve_base_url(
        settings,
        default_url="http://127.0.0.1:11434/api/chat",
        provider_name="ollama_api",
        strict=False,
    )
    parsed = urlparse(base_url)
    tags_url = f"{parsed.scheme}://{parsed.netloc}/api/tags"
    try:
        req = request.Request(tags_url, headers={**DEFAULT_HEADERS, "Accept": "application/json"}, method="GET")
        with request.urlopen(req, timeout=2) as resp:
            return 200 <= int(getattr(resp, "status", 200) or 200) < 300
    except (OSError, URLError, TimeoutError):
        return False


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    return "timed out" in str(exc).lower()


def _ollama_keep_alive_value(settings: dict) -> int | str | None:
    if "keep_alive" not in settings:
        return None
    value = settings.get("keep_alive")
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.lstrip("-").isdigit():
        return int(text)
    return text


def _ollama_options(settings: dict) -> dict:
    options = dict(settings.get("options", {}) or {})
    if "temperature" not in options:
        options["temperature"] = 0
    for source_key, option_key in (("num_ctx", "num_ctx"), ("num_predict", "num_predict")):
        if option_key in options:
            continue
        value = _int_value(settings.get(source_key))
        if value > 0:
            options[option_key] = value
    return options


def _ollama_system_prompt(request_name: str) -> str:
    name = str(request_name or "").lower()
    if name.startswith("deep_read_evidence"):
        return (
            "你是 Space Physics 文献深度解读证据整理助手。必须根据给定全文或全文级长文本提取研究问题、"
            "引言空白、方法链、结果链和证据边界；必须只输出合法 JSON 对象。"
        )
    if name.startswith("deep_read"):
        return (
            "你是 Space Physics 文献深度解读助手。必须根据给定全文或全文级长文本输出中文分析，"
            "不要退化为摘要复述；必须只输出合法 JSON 对象。"
        )
    if name.startswith("article"):
        return (
            "你是 Space Physics 文献卡片助手。只根据给定标题、来源文本、期刊和元数据输出中文分析；"
            "来源文本可能只是摘要，不能假设还有全文；必须只输出合法 JSON 对象。"
        )
    if name.startswith("report"):
        return (
            "你是 Space Physics 周报分析助手。只根据给定单篇总结清单、标签和期刊信息输出中文周报分析；"
            "不要编造全文细节；必须只输出合法 JSON 对象。"
        )
    return "你是 Space Physics 文献分析助手。只根据给定材料输出中文分析；必须只输出合法 JSON 对象。"


def _extract_openai_usage(raw_usage: dict) -> dict[str, int]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = _int_value(usage.get("input_tokens"))
    output_tokens = _int_value(usage.get("output_tokens"))
    total_tokens = _int_value(usage.get("total_tokens")) or (input_tokens + output_tokens)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _extract_openrouter_usage(raw_usage: dict) -> dict[str, int]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = _int_value(usage.get("prompt_tokens"))
    output_tokens = _int_value(usage.get("completion_tokens"))
    total_tokens = _int_value(usage.get("total_tokens")) or (input_tokens + output_tokens)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _extract_ollama_usage(raw_usage: dict) -> dict[str, int]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = _int_value(usage.get("prompt_eval_count"))
    output_tokens = _int_value(usage.get("eval_count"))
    total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
