from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib import request
from urllib.parse import urlparse
from urllib.error import URLError

from .http import DEFAULT_HEADERS


@dataclass(frozen=True)
class StructuredApiResponse:
    payload: dict
    usage: dict[str, int]


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
        payload=json.loads(output_text),
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
        payload=json.loads(output_text),
        usage=_extract_openrouter_usage(data.get("usage", {})),
    )


def run_ollama_structured(settings: dict, prompt: str, schema: dict) -> StructuredApiResponse:
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
        "format": schema["schema"],
        "messages": [
            {
                "role": "system",
                "content": "你是 Space Physics 文献分析助手。只根据给定标题、摘要和元数据输出中文分析；必须只输出符合 JSON schema 的 JSON。",
            },
            {"role": "user", "content": prompt},
        ],
    }
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
    with request.urlopen(req, timeout=int(settings.get("timeout_seconds", 300) or 300)) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    output_text = str((data.get("message") or {}).get("content", "") or "").strip()
    if not output_text:
        output_text = str(data.get("response", "") or "").strip()
    if not output_text:
        raise RuntimeError("Ollama response did not include structured text content")
    return StructuredApiResponse(
        payload=json.loads(output_text),
        usage=_extract_ollama_usage(data),
    )


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
