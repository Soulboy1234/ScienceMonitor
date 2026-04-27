from __future__ import annotations

AUTOMATIC_ANALYSIS_PROVIDERS = ("codex_local", "openai_api", "openrouter_api", "ollama_api")
MANUAL_ANALYSIS_PROVIDER = "chatgpt_web_manual"
SUPPORTED_ANALYSIS_PROVIDERS = AUTOMATIC_ANALYSIS_PROVIDERS + (MANUAL_ANALYSIS_PROVIDER,)

AUTOMATIC_PROVIDER_LABELS = {
    "codex_local": "Codex 本地",
    "openai_api": "OpenAI API",
    "openrouter_api": "OpenRouter API",
    "ollama_api": "Ollama 本地",
}

ALL_PROVIDER_LABELS = {
    **AUTOMATIC_PROVIDER_LABELS,
    MANUAL_ANALYSIS_PROVIDER: "人工中转",
}


def automatic_provider_choices() -> list[tuple[str, str]]:
    return [(provider, AUTOMATIC_PROVIDER_LABELS[provider]) for provider in AUTOMATIC_ANALYSIS_PROVIDERS]
